from pathlib import Path

from history_store import HistoryStore


def record_sample_events(store: HistoryStore):
    store.record_event(
        "171",
        {
            "type": "tool_call",
            "timestamp": "2025-11-09T14:00:00Z",
            "tool": "http_request",
            "args_preview": "{\"url\": \"https://api.example.com/moon\"}",
            "tool_call_id": "call-123",
        },
    )
    store.record_event(
        "171",
        {
            "type": "tool_result",
            "timestamp": "2025-11-09T14:00:05Z",
            "tool": "http_request",
            "success": True,
            "output_preview": "phase=waning gibbous",
            "artifact_summary": "Moon API (200)",
        },
    )
    store.record_event(
        "172",
        {
            "type": "tool_result",
            "timestamp": "2025-11-10T10:12:00Z",
            "tool": "run_command",
            "success": True,
            "output_preview": "deploy complete",
        },
    )


def test_history_store_records_and_filters(tmp_path: Path):
    db_path = tmp_path / "history.db"
    store = HistoryStore(db_path)
    record_sample_events(store)

    result = store.search(query="moon", limit=5)
    assert result["stats"]["returned"] >= 1
    match = next((m for m in result["matches"] if m["tool"] == "http_request"), None)
    assert match is not None, "Expected http_request entry in search results"
    assert match["tool"] == "http_request"
    assert match["summary"] == "Moon API (200)"

    session_only = store.search(session_id="172")
    assert session_only["stats"]["returned"] == 1
    assert session_only["matches"][0]["tool"] == "run_command"
