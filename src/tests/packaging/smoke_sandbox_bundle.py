"""Verify the final copied Node + SRT bundle before packaging."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_fetch_module():
    script = Path(__file__).resolve().parents[2] / "packaging" / "fetch_sandbox_runtime.py"
    spec = importlib.util.spec_from_file_location("joukir_fetch_sandbox_runtime", script)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Unable to load sandbox runtime helper: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fetch = _load_fetch_module()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    node = runtime / "bin" / ("node.exe" if sys.platform == "win32" else "node")
    cli = runtime / "node_modules/@anthropic-ai/sandbox-runtime/dist/cli.js"
    if not node.is_file() or not cli.is_file():
        raise SystemExit("Final sandbox bundle is missing Node or the SRT CLI.")
    fetch._verify_srt_integrity(runtime)
    fetch._apply_allow_all_domains_patch(runtime)
    completed = subprocess.run(
        [str(node), str(cli), "--version"],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SystemExit(
            "Final sandbox bundle CLI probe failed: "
            + (completed.stderr or completed.stdout).strip()
        )
    print(f"Sandbox bundle verified at {runtime}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
