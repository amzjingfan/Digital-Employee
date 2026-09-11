import importlib
import importlib.util
from pathlib import Path

# 渠道(微信/企微)打包必需依赖:PyInstaller hiddenimports 防回归删漏
REQUIRED_MODULES = ("aibot", "websockets", "aiohttp", "pyee", "dotenv", "cryptography")


def _load_test_layout_guard():
    script = Path(__file__).resolve().parents[1] / "check_test_layout.py"
    spec = importlib.util.spec_from_file_location("joukir_test_layout_guard", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_packaging_dependencies_importable() -> None:
    for module in REQUIRED_MODULES:
        importlib.import_module(module)


def test_test_layout_accepts_only_collected_frontend_test_suffixes(
    monkeypatch,
    capsys,
) -> None:
    guard = _load_test_layout_guard()
    monkeypatch.setattr(
        guard,
        "_tracked_paths",
        lambda: [
            "tests/frontend/example.test.ts",
            "tests/frontend/example.test.tsx",
        ],
    )

    assert guard.main() == 0
    assert "Test layout violations" not in capsys.readouterr().out


def test_test_layout_rejects_uncollected_frontend_test_suffixes(
    monkeypatch,
    capsys,
) -> None:
    guard = _load_test_layout_guard()
    unsupported = [
        *(
            f"tests/frontend/example.spec.{suffix}"
            for suffix in ("js", "jsx", "ts", "tsx", "mjs", "mts", "cjs", "cts")
        ),
        *(
            f"tests/frontend/example.test.{suffix}"
            for suffix in ("js", "jsx", "mjs", "mts", "cjs", "cts")
        ),
    ]
    monkeypatch.setattr(guard, "_tracked_paths", lambda: unsupported)

    assert guard.main() == 1
    output = capsys.readouterr().out
    for path in unsupported:
        assert path in output


def test_pyinstaller_spec_keeps_channel_hiddenimports() -> None:
    spec_path = Path(__file__).resolve().parents[2] / "packaging" / "ultrarag.spec"
    content = spec_path.read_text(encoding="utf-8")
    for module in REQUIRED_MODULES:
        assert f'"{module}"' in content, f"packaging/ultrarag.spec 缺少 hiddenimport: {module}"


def test_macos_bundle_keeps_webkit_packaging_support() -> None:
    root = Path(__file__).resolve().parents[2]
    spec = (root / "packaging" / "ultrarag.spec").read_text(encoding="utf-8")
    build_script = (root / "packaging" / "build_macos.sh").read_text(encoding="utf-8")
    pyproject = (root / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    assert '"WebKit"' in spec
    assert "pyobjc-framework-WebKit" in build_script
    assert "pyobjc-framework-WebKit" in pyproject


def test_pyinstaller_bundle_contains_the_build_version_resource() -> None:
    spec_path = Path(__file__).resolve().parents[2] / "packaging" / "ultrarag.spec"
    content = spec_path.read_text(encoding="utf-8")
    assert 'staffdeck-version.txt' in content
    assert '(str(VERSION_FILE), ".")' in content


def test_pyinstaller_bundle_contains_lark_sdk_metadata() -> None:
    spec_path = Path(__file__).resolve().parents[2] / "packaging" / "ultrarag.spec"
    content = spec_path.read_text(encoding="utf-8")
    assert 'copy_metadata("lark-channel-sdk")' in content


def test_release_builds_run_packaged_lark_sdk_smoke() -> None:
    packaging_dir = Path(__file__).resolve().parents[2] / "packaging"
    for script_name in ("build_macos.sh", "build_linux.sh", "build_windows.ps1"):
        content = (packaging_dir / script_name).read_text(encoding="utf-8")
        assert "--packaging-smoke" in content, f"{script_name} 未校验冻结产物中的 Lark SDK"


def test_windows_release_supports_external_signer_and_fails_closed() -> None:
    root = Path(__file__).resolve().parents[2]
    build = (root / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")
    signer = (root / "packaging" / "sign_windows.ps1").read_text(encoding="utf-8")

    assert "WINDOWS_SIGNER_SCRIPT" in build
    assert "UNSIGNED" in build
    assert 'Get-AuthenticodeSignature -FilePath $target' in signer
    assert '$signature.Status -ne "Valid"' in signer
    for extension in ('".exe"', '".dll"', '".pyd"', '".node"'):
        assert extension in build
