from __future__ import annotations

from app.tiktok.mock_replay import run_tiktok_mock_sop_replays


def test_five_tiktok_mock_sop_replays_cover_the_operational_chain() -> None:
    report = run_tiktok_mock_sop_replays()

    assert report["status"] == "passed"
    assert report["passed_count"] == 5
    assert len(report["items"]) == 5
    assert [item["sop_id"] for item in report["items"]] == [
        "TT-SOP-002",
        "TT-SOP-003",
        "TT-SOP-004",
        "TT-SOP-007",
        "TT-SOP-009",
    ]
    assert report["items"][1]["business_role"] == "operations_supervisor"
    assert report["items"][2]["business_role"] == "advertising_inspection_specialist"
    for item in report["items"]:
        assert item["status"] == "passed"
        assert item["execution_mode"] == "mock_replay"
        assert item["task_id"].startswith("mocktask_")
        assert item["trace_id"].startswith("mocktrace_")
        assert item["evidence_count"] >= 1
        assert item["follow_up"]["created"] is True
        assert {check["key"] for check in item["checks"]} == {
            "task_created",
            "knowledge_retrieved",
            "tool_called",
            "trace_recorded",
            "evidence_recorded",
            "follow_up_created",
        }


def test_tiktok_mock_replay_ids_are_deterministic_and_redacted() -> None:
    first = run_tiktok_mock_sop_replays()
    second = run_tiktok_mock_sop_replays()

    assert first == second
    assert "access_token" not in str(first)
    assert "client_secret" not in str(first)
    assert all(item["tool_result"]["external_write"] is False for item in first["items"])
