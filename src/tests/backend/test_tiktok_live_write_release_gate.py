from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.tiktok.release_gate import verify_tiktok_live_write_disabled


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _copy_gate_surface(tmp_path: Path) -> Path:
    source = _repository_root()
    target = tmp_path / "source"
    api_dir = target / "backend" / "app" / "api"
    tiktok_dir = target / "backend" / "app" / "tiktok"
    skills_dir = target / "skills"
    api_dir.mkdir(parents=True)
    shutil.copy2(source / "backend" / "app" / "api" / "tiktok.py", api_dir / "tiktok.py")
    shutil.copytree(source / "backend" / "app" / "tiktok", tiktok_dir)
    registry = json.loads(
        (source / "skills" / "joukir-tiktok-pack" / "registry.json").read_text(
            encoding="utf-8"
        )
    )
    shutil.copytree(
        source / "skills" / "joukir-tiktok-pack",
        skills_dir / "joukir-tiktok-pack",
    )
    for entry in registry["skills"]:
        skill_id = entry["skill_id"]
        shutil.copytree(source / "skills" / skill_id, skills_dir / skill_id)
    return target


def test_live_write_release_gate_passes_current_frozen_surface() -> None:
    result = verify_tiktok_live_write_disabled(_repository_root())

    assert result == {
        "ok": True,
        "gate": "tiktok_live_write_disabled",
        "route_count": 30,
        "skill_count": 12,
        "python_file_count": 14,
        "issues": [],
    }


def test_live_write_release_gate_blocks_unreviewed_route(tmp_path: Path) -> None:
    root = _copy_gate_surface(tmp_path)
    api_path = root / "backend" / "app" / "api" / "tiktok.py"
    api_path.write_text(
        api_path.read_text(encoding="utf-8")
        + '\n@router.post("/ads/budget")\ndef mutate_budget():\n    return None\n',
        encoding="utf-8",
    )

    result = verify_tiktok_live_write_disabled(root)

    assert result["ok"] is False
    assert "unreviewed_tiktok_route:POST /ads/budget" in result["issues"]


def test_live_write_release_gate_blocks_outbound_http_mutation(tmp_path: Path) -> None:
    root = _copy_gate_surface(tmp_path)
    official_path = root / "backend" / "app" / "tiktok" / "official.py"
    official_path.write_text(
        official_path.read_text(encoding="utf-8")
        + "\ndef unsafe_write():\n"
        + "    with httpx.Client() as client:\n"
        + '        client.post("https://example.invalid/write")\n',
        encoding="utf-8",
    )

    result = verify_tiktok_live_write_disabled(root)

    assert result["ok"] is False
    assert any(issue.startswith("outbound_http_mutation:") for issue in result["issues"])


def test_live_write_release_gate_blocks_skill_write_declaration(tmp_path: Path) -> None:
    root = _copy_gate_surface(tmp_path)
    manifest_path = root / "skills" / "joukir-live-plan" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["external_write"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = verify_tiktok_live_write_disabled(root)

    assert result["ok"] is False
    assert "skill_external_write_not_false:joukir-live-plan" in result["issues"]
