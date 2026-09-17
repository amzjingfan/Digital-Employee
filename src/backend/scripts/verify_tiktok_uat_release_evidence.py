"""Verify production-like config and signed TikTok UAT release evidence."""

from __future__ import annotations

import argparse
import json

from app.config import get_settings
from app.tiktok.release_evidence import (
    release_evidence_filename,
    verify_tiktok_release_evidence,
    verify_tiktok_runtime_security_config,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify TikTok UAT release evidence")
    parser.add_argument("--tenant-id", required=True)
    args = parser.parse_args()

    settings = get_settings()
    runtime_gate = verify_tiktok_runtime_security_config(settings, args.tenant_id)
    evidence = verify_tiktok_release_evidence(settings, args.tenant_id)
    gates = [runtime_gate, *evidence.gates]
    result = {
        "ok": all(gate.status == "passed" for gate in gates),
        "gate": "tiktok_uat_release_evidence",
        "evidence_filename": release_evidence_filename(args.tenant_id),
        "error_code": evidence.error_code,
        "gates": [
            {
                "key": gate.key,
                "status": gate.status,
                "detail": gate.detail,
            }
            for gate in gates
        ],
    }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
