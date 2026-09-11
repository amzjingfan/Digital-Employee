from __future__ import annotations

from app.tiktok.mock_replay import run_tiktok_mock_sop_exception_matrix


def test_five_tiktok_sops_have_complete_exception_matrix() -> None:
    report = run_tiktok_mock_sop_exception_matrix()

    assert report["status"] == "passed"
    assert report["sop_count"] == 5
    assert report["scenario_count"] == 6
    assert report["total_count"] == 30
    assert report["passed_count"] == 30
    assert report["failed_count"] == 0
    assert report["external_writes"] is False
    assert {item["sop_id"] for item in report["items"]} == {
        "TT-SOP-002",
        "TT-SOP-003",
        "TT-SOP-004",
        "TT-SOP-007",
        "TT-SOP-009",
    }
    assert {item["scenario"] for item in report["items"]} == {
        "missing_knowledge",
        "authorization_conflict",
        "connector_timeout",
        "duplicate_replay",
        "revoked_scope",
        "manual_handoff",
    }
    assert all(item["status"] == "passed" for item in report["items"])
    assert all(item["external_writes"] is False for item in report["items"])


def test_exception_matrix_is_deterministic_and_redacted() -> None:
    first = run_tiktok_mock_sop_exception_matrix()
    second = run_tiktok_mock_sop_exception_matrix()

    assert first == second
    rendered = str(first)
    assert "access_token" not in rendered
    assert "refresh_token" not in rendered
    assert "client_secret" not in rendered
