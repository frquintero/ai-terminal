import json

import pytest

from history_sql import _reset_history_sql_executor_for_tests
from history_store import HistoryStore
import tools


@pytest.fixture
def history_db(tmp_path, monkeypatch):
    db_path = tmp_path / "history.db"
    monkeypatch.setenv("HISTORY_DB_PATH", str(db_path))
    _reset_history_sql_executor_for_tests()
    store = HistoryStore(db_path=str(db_path))
    yield store
    if hasattr(store, "_conn"):
        store._conn.close()
    _reset_history_sql_executor_for_tests()


def test_history_sql_select_returns_event(history_db):
    history_db.record_event(
        "176",
        {
            "type": "summary",
            "timestamp": "2025-11-10T12:00:00Z",
            "content_preview": "Andrés Quintero is my son.",
            "tool": "history_sql_test",
        },
    )
    tool = tools.TOOLS["history_sql"]
    response = tool.execute(
        statement="SELECT detail_json FROM events WHERE session_id = ? ORDER BY id DESC",
        params=["176"],
        max_rows=5,
    )
    payload = json.loads(response)
    assert payload["operation"] == "select"
    assert payload["rows_returned"] == 1
    detail = json.loads(payload["rows"][0]["detail_json"])
    assert detail["content_preview"] == "Andrés Quintero is my son."


def test_history_sql_insert_agent_memory(history_db):
    tool = tools.TOOLS["history_sql"]
    insert_payload = json.loads(
        tool.execute(
            statement="INSERT INTO agent_memories(session_id, topic, content, tags) VALUES (?, ?, ?, ?)",
            params=["176", "family", "Andrés Quintero is my son.", "test"],
        )
    )
    assert insert_payload["operation"] == "insert"
    assert insert_payload["last_insert_rowid"]

    rows_payload = json.loads(
        tool.execute(
            statement="SELECT topic, content FROM agent_memories WHERE session_id = :sid",
            named_params={"sid": "176"},
            max_rows=5,
        )
    )
    assert rows_payload["rows_returned"] == 1
    assert rows_payload["rows"][0]["topic"] == "family"


def test_history_sql_blocks_delete(history_db):
    tool = tools.TOOLS["history_sql"]
    result = tool.execute(statement="DELETE FROM events")
    assert result.startswith("History SQL error:")


def test_history_sql_rejects_conflicting_params(history_db):
    tool = tools.TOOLS["history_sql"]
    result = tool.execute(
        statement="SELECT 1",
        params=[1],
        named_params={"value": 1},
    )
    assert "Provide either positional params or named_params" in result
