"""
Filesystem context persistence helpers.

Provides a lightweight store that captures shell-derived snapshots and
file-activity events so agents can retrieve accurate workspace metadata
without bloating prompts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class FilesystemContextStore:
    """SQLite + JSONL backed persistence for filesystem context snapshots."""

    def __init__(
        self,
        db_path: Union[str, Path] = None,
        jsonl_dir: Union[str, Path] = None,
    ):
        default_db = Path(os.getenv("FS_CONTEXT_DB_PATH", "logs/session_logs.db"))
        default_jsonl = Path(os.getenv("FS_CONTEXT_JSONL_DIR", "logs/fs_context"))
        self.db_path = Path(db_path) if db_path else default_db
        self.jsonl_dir = Path(jsonl_dir) if jsonl_dir else default_jsonl
        self.jsonl_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self):
        schema = """
        CREATE TABLE IF NOT EXISTS filesystem_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            shell_cwd TEXT,
            working_dir TEXT,
            workspace_hint TEXT,
            sandbox_root TEXT,
            command TEXT,
            command_preview TEXT,
            exit_code INTEGER,
            metadata TEXT
        );

        CREATE TABLE IF NOT EXISTS filesystem_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            operation TEXT NOT NULL,
            requested_path TEXT NOT NULL,
            absolute_path TEXT,
            relative_path TEXT,
            location TEXT,
            source TEXT,
            metadata TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_fs_snapshots_session_id
            ON filesystem_snapshots(session_id, id DESC);

        CREATE INDEX IF NOT EXISTS idx_fs_events_session_id
            ON filesystem_events(session_id, id DESC);
        """
        with self._lock:
            self._conn.executescript(schema)
            self._conn.commit()

    def record_snapshot(self, session_id: Optional[str], payload: Dict[str, Any]) -> None:
        """Persist a filesystem snapshot for the active session."""
        if not session_id:
            return
        created_at = _utcnow()
        metadata = payload.get("metadata") or {}
        record = (
            str(session_id),
            created_at,
            payload.get("shell_cwd"),
            payload.get("working_dir"),
            payload.get("workspace_hint"),
            payload.get("sandbox_root"),
            payload.get("command"),
            payload.get("command_preview"),
            payload.get("exit_code"),
            json.dumps(metadata, ensure_ascii=False),
        )
        sql = """
        INSERT INTO filesystem_snapshots (
            session_id, created_at, shell_cwd, working_dir, workspace_hint,
            sandbox_root, command, command_preview, exit_code, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._lock:
            self._conn.execute(sql, record)
            self._conn.commit()
        self._append_jsonl(session_id, {"type": "snapshot", **payload, "created_at": created_at})

    def record_file_event(self, session_id: Optional[str], event: Dict[str, Any]) -> None:
        """Persist a file read/write event."""
        if not session_id:
            return
        created_at = event.get("timestamp") or _utcnow()
        payload = (
            str(session_id),
            created_at,
            event.get("operation"),
            event.get("requested_path"),
            event.get("absolute_path"),
            event.get("relative_path"),
            event.get("location"),
            event.get("source"),
            json.dumps({k: v for k, v in event.items() if k not in {
                "operation",
                "requested_path",
                "absolute_path",
                "relative_path",
                "location",
                "source",
            }}, ensure_ascii=False),
        )
        sql = """
        INSERT INTO filesystem_events (
            session_id, created_at, operation, requested_path, absolute_path,
            relative_path, location, source, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._lock:
            self._conn.execute(sql, payload)
            self._conn.commit()
        enriched = dict(event)
        enriched["created_at"] = created_at
        enriched["type"] = "file_event"
        self._append_jsonl(session_id, enriched)

    def get_latest_snapshot(self, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Return the most recent snapshot for the given session."""
        if not session_id:
            return None
        sql = """
        SELECT created_at, shell_cwd, working_dir, workspace_hint, sandbox_root,
               command, command_preview, exit_code, metadata
        FROM filesystem_snapshots
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT 1
        """
        with self._lock:
            row = self._conn.execute(sql, (str(session_id),)).fetchone()
        if not row:
            return None
        metadata = json.loads(row[8]) if row[8] else {}
        return {
            "created_at": row[0],
            "shell_cwd": row[1],
            "working_dir": row[2],
            "workspace_hint": row[3],
            "sandbox_root": row[4],
            "command": row[5],
            "command_preview": row[6],
            "exit_code": row[7],
            "metadata": metadata,
        }

    def get_recent_events(self, session_id: Optional[str], limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent file events for the session."""
        if not session_id:
            return []
        limit = max(1, min(limit, 100))
        sql = """
        SELECT created_at, operation, requested_path, absolute_path,
               relative_path, location, source, metadata
        FROM filesystem_events
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """
        with self._lock:
            rows = self._conn.execute(sql, (str(session_id), limit)).fetchall()
        events: List[Dict[str, Any]] = []
        for row in rows:
            metadata = json.loads(row[7]) if row[7] else {}
            events.append({
                "created_at": row[0],
                "operation": row[1],
                "requested_path": row[2],
                "absolute_path": row[3],
                "relative_path": row[4],
                "location": row[5],
                "source": row[6],
                "metadata": metadata,
            })
        events.reverse()
        return events

    def _append_jsonl(self, session_id: str, payload: Dict[str, Any]) -> None:
        """Write the payload to the per-session JSONL mirror."""
        try:
            path = self.jsonl_dir / f"{session_id}.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            # Fail silently; JSONL is best-effort
            return


_FS_STORE: Optional[FilesystemContextStore] = None


def get_fs_context_store() -> FilesystemContextStore:
    """Return the shared FilesystemContextStore instance."""
    global _FS_STORE
    if _FS_STORE is None:
        _FS_STORE = FilesystemContextStore()
    return _FS_STORE


__all__ = ["FilesystemContextStore", "get_fs_context_store"]
