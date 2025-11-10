import json
from pathlib import Path

from history_store import HistoryStore, _set_history_store_for_tests
from tools import HistorySchemaTool


def setup_history_db(tmp_path: Path):
    db_path = tmp_path / "history.db"
    store = HistoryStore(db_path)
    store.record_event(
        "111",
        {
            "type": "user_message",
            "timestamp": "2025-11-10T00:00:00Z",
            "summary": "Dummy entry",
            "detail_json": "{}",
        },
    )
    return store


def test_history_schema_list_tables(tmp_path: Path):
    store = setup_history_db(tmp_path)
    _set_history_store_for_tests(store)
    try:
        tool = HistorySchemaTool()
        payload = json.loads(tool.execute())
        assert "events" in payload["tables"]
        assert "agent_memories" in payload["tables"]
    finally:
        _set_history_store_for_tests(None)


def test_history_schema_describe_table(tmp_path: Path):
    store = setup_history_db(tmp_path)
    _set_history_store_for_tests(store)
    try:
        tool = HistorySchemaTool()
        payload = json.loads(tool.execute(action="describe_table", table="events"))
        column_names = [col["name"] for col in payload["columns"]]
        assert "session_id" in column_names
        assert "detail_json" in column_names
    finally:
        _set_history_store_for_tests(None)
