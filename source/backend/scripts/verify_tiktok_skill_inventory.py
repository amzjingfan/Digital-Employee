"""Verify the Joukir TikTok Skill source and license inventory.

This is intentionally filesystem-only. It does not import application code,
contact external services, or treat a seed review as production approval.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXPECTED_FILES = (
    "SKILL.md",
    "manifest.json",
    "schemas/input.json",
    "schemas/output.json",
    "references/README.md",
    "evals/cases.json",
    "LICENSES.md",
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def verify_skill_inventory(repo_root: Path) -> dict[str, Any]:
    skills_root = repo_root / "skills"
    pack_root = skills_root / "joukir-tiktok-pack"
    registry = _load_json(pack_root / "registry.json")
    inventory = _load_json(pack_root / "inventory.json")

    if registry.get("pack_id") != "joukir-tiktok-pack":
        raise ValueError("registry pack_id must be joukir-tiktok-pack")
    if inventory.get("pack_id") != registry["pack_id"]:
        raise ValueError("inventory pack_id does not match registry")
    if inventory.get("clipcat_hard_dependency") is not False:
        raise ValueError("Clipcat must not be a hard dependency")

    registry_items = registry.get("skills")
    inventory_items = inventory.get("skills")
    if not isinstance(registry_items, list) or not isinstance(inventory_items, list):
        raise TypeError("registry and inventory must contain skills arrays")
    registry_ids = [item.get("skill_id") for item in registry_items]
    inventory_ids = [item.get("skill_id") for item in inventory_items]
    if len(registry_ids) != 12 or len(set(registry_ids)) != 12:
        raise ValueError("registry must contain exactly 12 unique skills")
    if inventory_ids != sorted(inventory_ids):
        raise ValueError("inventory skills must be sorted by skill_id")
    if set(registry_ids) != set(inventory_ids):
        raise ValueError("registry and inventory skill ids differ")

    for item in inventory_items:
        skill_id = item.get("skill_id")
        if not isinstance(skill_id, str) or not skill_id.startswith("joukir-"):
            raise ValueError(f"invalid skill_id: {skill_id!r}")
        if item.get("source") != f"internal://joukir/skills/{skill_id}":
            raise ValueError(f"invalid source for {skill_id}")
        if item.get("license") != "Joukir-internal-methods":
            raise ValueError(f"invalid license for {skill_id}")
        if item.get("third_party_code") is not False or item.get("third_party_prompt") is not False:
            raise ValueError(f"third-party content must be false for {skill_id}")
        if item.get("dependencies") != []:
            raise ValueError(f"unexpected Skill dependencies for {skill_id}")

        skill_root = skills_root / skill_id
        missing = [name for name in EXPECTED_FILES if not (skill_root / name).is_file()]
        if missing:
            raise ValueError(f"{skill_id} missing files: {', '.join(missing)}")
        manifest = _load_json(skill_root / "manifest.json")
        if manifest.get("skill_id") != skill_id:
            raise ValueError(f"manifest skill_id mismatch for {skill_id}")
        if manifest.get("license_policy") != "local-methods-only":
            raise ValueError(f"manifest license policy mismatch for {skill_id}")
        if manifest.get("external_write") is not False:
            raise ValueError(f"external_write must be false for {skill_id}")
        if manifest.get("review_status") != "approved_seed":
            raise ValueError(f"unexpected review status for {skill_id}")

        for path in skill_root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".md", ".json", ".yaml", ".yml"}:
                text = path.read_text(encoding="utf-8")
                if "clipcat" in text.lower():
                    raise ValueError(f"Clipcat reference found in {path}")

    return {
        "ok": True,
        "pack_id": registry["pack_id"],
        "skill_count": len(registry_ids),
        "review_status": "approved_seed",
        "external_write": False,
        "clipcat_hard_dependency": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="StaffDeck repository root (defaults to the current checkout)",
    )
    args = parser.parse_args()
    try:
        result = verify_skill_inventory(args.repo_root.resolve())
    except (TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
