"""
Persistent, searchable history store for AI Terminal.

Provides:
- HistoryStore: resilient SQLite-backed event archive
- get_history_store(): shared singleton accessor for agent/tools
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoryStoreError(Exception):
    """Generic failure while interacting with the history store."""


class HistoryStore:
    """
    SQLite-backed archive of tool interactions.

    Responsibilities:
    - Initialize directory/DB automatically
    - Run integrity check; recreate database if corrupt/missing
    - Record normalized events
    - Serve keyword/time filtered searches
    """

    def __init__(self, db_path: Optional[str | Path] = None):
        default_path = Path(
            os.getenv("HISTORY_DB_PATH", "logs/history/history.db")
        )
        self.db_path = Path(db_path) if db_path else default_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._configure()

    def _configure(self):
        try:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._ensure_schema()
            self._ensure_integrity()
        except sqlite3.DatabaseError as exc:
            self._recover_corrupt_db(exc)

    def _ensure_schema(self):
        schema_sql = """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            tool TEXT,
            action TEXT,
            summary TEXT,
            detail_json TEXT NOT NULL,
            artifact_path TEXT,
            keywords TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_events_session_time
            ON events(session_id, timestamp);

        CREATE INDEX IF NOT EXISTS idx_events_type_time
            ON events(event_type, timestamp DESC);
        """
        self._conn.executescript(schema_sql)

    def _ensure_integrity(self):
        result = self._conn.execute("PRAGMA quick_check;").fetchone()
        if not result or result[0] != "ok":
            raise sqlite3.DatabaseError(f"Integrity check failed: {result!r}")

    def _recover_corrupt_db(self, exc: Exception):
        self._conn.close()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = self.db_path.with_suffix(f".corrupt-{timestamp}")
        try:
            shutil.move(self.db_path, backup)
        except FileNotFoundError:
            pass
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._ensure_schema()

    @staticmethod
    def _summarize_event(event: Dict[str, Any]) -> Optional[str]:
        for key in ("artifact_summary", "output_preview", "content_preview", "error"):
            value = event.get(key)
            if value:
                return str(value)
        if event.get("success") is False and event.get("tool"):
            return f"{event['tool']} reported failure"
        return None

    @staticmethod
    def _build_keywords(event: Dict[str, Any]) -> str:
        parts: List[str] = []
        for key in ("type", "tool", "source", "category"):
            value = event.get(key)
            if value:
                parts.append(str(value).lower())
        if event.get("tool_call_id"):
            parts.append(str(event["tool_call_id"]))
        return " ".join(parts)

    def record_event(self, session_id: str, event: Dict[str, Any]):
        """Persist a normalized copy of the event."""
        if not session_id:
            return
        detail_json = json.dumps(event, ensure_ascii=False)
        summary = self._summarize_event(event)
        keywords = self._build_keywords(event)
        payload = (
            session_id,
            event.get("timestamp") or _utcnow_iso(),
            event.get("type", "unknown"),
            event.get("tool"),
            event.get("tool_call_id") or event.get("source"),
            summary,
            detail_json,
            event.get("artifact_path"),
            keywords,
        )
        sql = """
        INSERT INTO events (
            session_id, timestamp, event_type, tool, action,
            summary, detail_json, artifact_path, keywords
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self._lock:
                self._conn.execute(sql, payload)
                self._conn.commit()
        except sqlite3.DatabaseError as exc:
            raise HistoryStoreError(f"Failed to record event: {exc}") from exc

    def search(
        self,
        *,
        query: Optional[str] = None,
        session_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        tool: Optional[str] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Query stored events with optional filters."""
        limit = max(1, min(limit, 25))
        filters: List[str] = []
        params: List[Any] = []

        if session_id:
            filters.append("session_id = ?")
            params.append(str(session_id))
        if tool:
            filters.append("tool = ?")
            params.append(tool)
        if since:
            filters.append("timestamp >= ?")
            params.append(since)
        if until:
            filters.append("timestamp <= ?")
            params.append(until)
        if query:
            like = f"%{query.lower()}%"
            filters.append("(lower(summary) LIKE ? OR lower(detail_json) LIKE ? OR lower(keywords) LIKE ?)")
            params.extend([like, like, like])

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        base_query = f"""
        SELECT id, session_id, timestamp, event_type, tool, summary,
               detail_json, artifact_path
        FROM events
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ?
        """
        query_params: Sequence[Any] = [*params, limit]

        with self._lock:
            rows = self._conn.execute(base_query, query_params).fetchall()
            count_sql = f"SELECT COUNT(1) FROM events {where_clause}"
            total = self._conn.execute(count_sql, params).fetchone()[0]

        matches: List[Dict[str, Any]] = []
        for row in rows:
            detail_obj: Any
            try:
                detail_obj = json.loads(row["detail_json"])
            except json.JSONDecodeError:
                detail_obj = row["detail_json"]
            matches.append(
                {
                    "session_id": row["session_id"],
                    "timestamp": row["timestamp"],
                    "event_type": row["event_type"],
                    "tool": row["tool"],
                    "summary": row["summary"],
                    "detail_preview": self._preview_detail(detail_obj),
                    "artifact_path": row["artifact_path"],
                    "source_ref": {
                        "type": "history_db",
                        "event_id": row["id"],
                        "session_log": f"logs/events/{row['session_id']}.jsonl",
                    },
                }
            )

        return {
            "matches": matches,
            "stats": {
                "returned": len(matches),
                "limit": limit,
                "total_available": total,
            },
        }

    @staticmethod
    def _preview_detail(detail_obj: Any, limit: int = 500) -> str:
        if isinstance(detail_obj, dict):
            for key in (
                "artifact_summary",
                "output_preview",
                "content_preview",
                "error",
                "args_preview",
            ):
                value = detail_obj.get(key)
                if value:
                    return HistoryStore._trim(str(value), limit)
            return HistoryStore._trim(json.dumps(detail_obj, ensure_ascii=False), limit)
        if isinstance(detail_obj, str):
            return HistoryStore._trim(detail_obj, limit)
        return HistoryStore._trim(str(detail_obj), limit)

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."


_GLOBAL_HISTORY_STORE: Optional[HistoryStore] = None


def get_history_store() -> HistoryStore:
    global _GLOBAL_HISTORY_STORE
    if _GLOBAL_HISTORY_STORE is None:
        _GLOBAL_HISTORY_STORE = HistoryStore()
    return _GLOBAL_HISTORY_STORE


def _set_history_store_for_tests(store: Optional[HistoryStore]):
    """
    Test-only helper to replace the global store.
    Avoid using this outside unit tests.
    """
    global _GLOBAL_HISTORY_STORE
    _GLOBAL_HISTORY_STORE = store
