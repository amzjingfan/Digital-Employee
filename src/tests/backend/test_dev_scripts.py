from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_supervisor_uses_platform_specific_executables() -> None:
    supervisor = _load_script("dev_supervisor")

    assert supervisor._backend_python("win32") == ROOT_DIR / "backend/.venv/Scripts/python.exe"
    assert supervisor._backend_python("linux") == ROOT_DIR / "backend/.venv/bin/python"
    assert supervisor._vite_executable("win32") == ROOT_DIR / "frontend-enterprise/node_modules/.bin/vite.cmd"
    assert supervisor._vite_executable("darwin") == ROOT_DIR / "frontend-enterprise/node_modules/.bin/vite"


def test_supervisor_bypasses_system_proxy_for_loopback_dependencies(monkeypatch) -> None:
    monkeypatch.setenv("NO_PROXY", "internal.example")
    supervisor = _load_script("dev_supervisor")

    app_service = supervisor.build_services()[0]

    expected = "internal.example,localhost,127.0.0.1,::1"
    assert app_service.env["NO_PROXY"] == expected
    assert app_service.env["no_proxy"] == expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process creation flags")
def test_supervisor_starts_windows_service_without_console_window(monkeypatch, tmp_path) -> None:
    supervisor = _load_script("dev_supervisor")
    monkeypatch.setattr(supervisor, "RUN_DIR", tmp_path / "run")
    monkeypatch.setattr(supervisor, "LOG_DIR", tmp_path / "logs")
    creationflags = None

    def fake_popen(_command, **kwargs):
        nonlocal creationflags
        creationflags = kwargs["creationflags"]
        kwargs["stdout"].close()
        kwargs["stderr"].close()
        return SimpleNamespace(pid=12345)

    monkeypatch.setattr(supervisor.subprocess, "Popen", fake_popen)
    service = supervisor.Service(name="app", cwd=tmp_path, command=[sys.executable])

    service.start()

    assert creationflags is not None
    assert creationflags & subprocess.CREATE_NO_WINDOW


def test_pid_alive_recognizes_current_process() -> None:
    process_utils = _load_script("process_utils")

    assert process_utils.pid_alive(os.getpid())


def test_dev_cli_uses_next_port_in_packaged_app_range(monkeypatch) -> None:
    dev = _load_script("dev")
    monkeypatch.delenv("ULTRARAG_PORT_RANGE_START", raising=False)
    monkeypatch.delenv("ULTRARAG_PORT_RANGE_END", raising=False)
    monkeypatch.setattr(dev, "_port_available", lambda _host, port: port != 5173)

    assert dev._select_available_port("127.0.0.1", 5173) == 5174


def test_dev_cli_honors_packaged_app_port_range(monkeypatch) -> None:
    dev = _load_script("dev")
    monkeypatch.setenv("ULTRARAG_PORT_RANGE_START", "6200")
    monkeypatch.setenv("ULTRARAG_PORT_RANGE_END", "6202")
    monkeypatch.setattr(dev, "_port_available", lambda _host, port: port == 6202)

    assert dev._select_available_port("127.0.0.1", 6200) == 6202


def test_dev_cli_keeps_complete_frontend_dependencies(monkeypatch) -> None:
    dev = _load_script("dev")
    calls: list[list[str]] = []
    monkeypatch.setattr(dev, "_npm_executable", lambda: "npm")

    def run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(dev.subprocess, "run", run)

    dev._ensure_frontend_dependencies()

    assert len(calls) == 1
    assert calls[0][-3:] == ["ls", "--depth=0", "--json"]


def test_dev_cli_refreshes_incomplete_frontend_dependencies(monkeypatch) -> None:
    dev = _load_script("dev")
    calls: list[list[str]] = []
    monkeypatch.setattr(dev, "_npm_executable", lambda: "npm")

    def run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1 if "ls" in command else 0)

    monkeypatch.setattr(dev.subprocess, "run", run)

    dev._ensure_frontend_dependencies()

    assert len(calls) == 2
    assert calls[1][-3:] == ["ci", "--no-audit", "--no-fund"]


def test_dev_cli_prints_existing_health_endpoint_instead_of_disabled_docs(
    monkeypatch,
    capsys,
) -> None:
    class Supervisor:
        APP_HOST = "127.0.0.1"
        APP_PORT = 5173
        BACKEND_HOST = "127.0.0.1"
        BACKEND_PORT = 8000
        ENTERPRISE_HOST = "127.0.0.1"
        ENTERPRISE_PORT = 5173
        validate_prerequisites = staticmethod(lambda: None)
        build_services = staticmethod(list)
        url_host = staticmethod(lambda host: host)

    for single_port, health_url in (
        (True, "http://127.0.0.1:5173/api/health"),
        (False, "http://127.0.0.1:8000/api/health"),
    ):
        dev = _load_script("dev")
        supervisor = Supervisor()
        supervisor.SINGLE_PORT = single_port
        monkeypatch.setenv("FORCE_PORTS", "1")
        monkeypatch.setattr(dev, "_load_supervisor", lambda current=supervisor: current)
        monkeypatch.setattr(dev, "_ensure_frontend_dependencies", lambda: None)
        monkeypatch.setattr(dev, "_ensure_sandbox_runtime", lambda: None)
        monkeypatch.setattr(dev, "stop_services", lambda verbose=False: None)
        monkeypatch.setattr(dev, "_ensure_port_available", lambda *_args: None)
        monkeypatch.setattr(dev, "_build_frontend", lambda: None)
        monkeypatch.setattr(dev, "_start_detached", lambda _supervisor: 1234)
        monkeypatch.setattr(dev, "_wait_for_url", lambda *_args: None)

        assert dev.command_up(True) == 0
        output = capsys.readouterr().out
        assert health_url in output
        assert "/docs" not in output


def test_supervisor_does_not_restart_during_startup_grace(monkeypatch) -> None:
    supervisor = _load_script("dev_supervisor")

    class RunningProcess:
        def poll(self):
            return None

    service = supervisor.Service(name="app", cwd=ROOT_DIR, command=["unused"])
    service.health_url = "http://127.0.0.1:5173/api/health"
    service.process = RunningProcess()
    service.startup_deadline = 100.0
    monkeypatch.setattr(supervisor.time, "monotonic", lambda: 50.0)
    monkeypatch.setattr(service, "healthy", lambda: False)

    service.poll()

    assert service.unhealthy_count == 0
    assert service.restart_count == 0


def test_shell_wrappers_delegate_to_cross_platform_cli() -> None:
    for command in ("up", "down", "status"):
        script = (SCRIPTS_DIR / f"dev_{command}.sh").read_text(encoding="utf-8")
        assert '$ROOT_DIR/backend/.venv/bin/python' in script
        assert 'scripts/dev.py" ' + command in script


def test_powershell_wrappers_delegate_to_cross_platform_cli() -> None:
    for command in ("up", "down", "status"):
        script = (SCRIPTS_DIR / f"dev_{command}.ps1").read_text(encoding="utf-8")
        assert f'"$PSScriptRoot\\dev.ps1" {command}' in script


def test_powershell_launcher_accepts_newer_python_3_versions() -> None:
    script = (SCRIPTS_DIR / "dev.ps1").read_text(encoding="utf-8")

    assert 'Prefix = @("-3.11")' in script
    assert 'Prefix = @("-3")' in script
