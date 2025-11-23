"""
Lightweight SQL execution guard for the history database.

Enables MiniAgent (and tools) to run parameterized SELECT/INSERT/UPDATE
statements against `logs/history/history.db` while blocking destructive
verbs like DELETE/DROP. This unlocks richer recall and memory writing
without exposing raw sqlite3 cursors to the LLM.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


class HistorySQLExecutionError(Exception):
    """Raised when a guarded SQL command is invalid or fails."""


class HistorySQLExecutor:
    """Thread-safe, parameterized SQL executor with guard rails."""

    _ALLOWED_PREFIXES = ("select", "with", "insert", "update")
    _WRITE_OPERATIONS = {"insert", "update"}
    _BLOCKED_KEYWORDS = {
        " delete ",
        " drop ",
        " alter ",
        " truncate ",
        " vacuum ",
        " detach ",
        " attach ",
        " pragma ",
        " replace ",
    }

    def __init__(self, db_path: Union[str, Path] = None):
        default_path = Path(os.getenv("HISTORY_DB_PATH", "logs/history/history.db"))
        self.db_path = Path(db_path) if db_path else default_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._configure()

    def _configure(self):
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA journal_mode = WAL;")

    def close(self):
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # Schema helpers (internal-use)
    # ------------------------------------------------------------------

    def list_tables(self) -> List[str]:
        """Return sorted table names in the history database."""
        sql = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        with self._lock:
            rows = self._conn.execute(sql).fetchall()
        return [row[0] for row in rows]

    def describe_table(self, table_name: str) -> List[Dict[str, Any]]:
        """Return PRAGMA table_info-style metadata for the given table."""
        if not table_name:
            raise HistorySQLExecutionError("table name is required")
        sql = f"PRAGMA table_info({table_name})"
        with self._lock:
            try:
                rows = self._conn.execute(sql).fetchall()
            except sqlite3.DatabaseError as exc:
                raise HistorySQLExecutionError(f"Failed to describe table '{table_name}': {exc}") from exc
        if not rows:
            raise HistorySQLExecutionError(f"Table '{table_name}' does not exist")
        columns = []
        for row in rows:
            columns.append(
                {
                    "cid": row[0],
                    "name": row[1],
                    "type": row[2],
                    "notnull": bool(row[3]),
                    "default_value": row[4],
                    "primary_key": bool(row[5]),
                }
            )
        return columns

    @staticmethod
    def _clean_statement(statement: str) -> str:
        if not statement or not statement.strip():
            raise HistorySQLExecutionError("SQL statement is required.")
        cleaned = statement.strip()
        # Drop trailing semicolons but disallow embedded multiples.
        while cleaned.endswith(";"):
            cleaned = cleaned[:-1].strip()
        if ";" in cleaned:
            raise HistorySQLExecutionError("Only a single statement is allowed (omit inner semicolons).")
        return cleaned

    @classmethod
    def _detect_operation(cls, statement: str) -> str:
        lowered = statement.lstrip().split(None, 1)[0].lower()
        if lowered not in cls._ALLOWED_PREFIXES:
            allowed = ", ".join(cls._ALLOWED_PREFIXES)
            raise HistorySQLExecutionError(f"Only {allowed} statements are allowed (got '{lowered}').")
        if lowered == "with":
            return "select"
        return lowered

    def _guard_keywords(self, statement: str):
        padded = f" {statement.lower()} "
        for keyword in self._BLOCKED_KEYWORDS:
            if keyword in padded:
                raise HistorySQLExecutionError(f"Keyword '{keyword.strip()}' is not permitted in history SQL.")

    @staticmethod
    def _normalize_params(params: Optional[Union[Sequence[Any], Dict[str, Any]]]) -> Union[Sequence[Any], Dict[str, Any]]:
        if params is None:
            return []
        if isinstance(params, dict):
            return params
        if isinstance(params, (list, tuple)):
            return list(params)
        raise HistorySQLExecutionError("Params must be a list/tuple or a dict of named parameters.")

    @staticmethod
    def _normalize_max_rows(max_rows: Optional[int]) -> int:
        if max_rows is None:
            return 50
        if not isinstance(max_rows, int):
            raise HistorySQLExecutionError("max_rows must be an integer.")
        return max(1, min(max_rows, 200))

    def _fetch_rows(
        self,
        cursor: sqlite3.Cursor,
        columns: Sequence[str],
        max_rows: int,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        rows: List[Dict[str, Any]] = []
        truncated = False
        limit = max_rows + 1
        fetched = cursor.fetchmany(limit)
        if len(fetched) > max_rows:
            truncated = True
            fetched = fetched[:max_rows]
        for row in fetched:
            row_dict = {col: row[idx] for idx, col in enumerate(columns)}
            rows.append(row_dict)
        return rows, truncated

    def execute(
        self,
        statement: str,
        params: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
        max_rows: Optional[int] = None,
    ) -> Dict[str, Any]:
        cleaned = self._clean_statement(statement)
        operation = self._detect_operation(cleaned)
        self._guard_keywords(cleaned)
        bound_params = self._normalize_params(params)
        row_cap = self._normalize_max_rows(max_rows)

        started = time.perf_counter()
        with self._lock:
            try:
                cursor = self._conn.execute(cleaned, bound_params)
            except sqlite3.DatabaseError as exc:
                raise HistorySQLExecutionError(f"SQLite error: {exc}") from exc
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows: List[Dict[str, Any]] = []
            truncated = False
            if operation == "select" and columns:
                rows, truncated = self._fetch_rows(cursor, columns, row_cap)
            if operation in self._WRITE_OPERATIONS:
                self._conn.commit()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response: Dict[str, Any] = {
            "statement": cleaned,
            "operation": operation,
            "execution_ms": elapsed_ms,
            "rows_returned": len(rows),
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
        }
        if operation in self._WRITE_OPERATIONS:
            response["rowcount"] = cursor.rowcount if cursor.rowcount >= 0 else None
            response["last_insert_rowid"] = (
                self._conn.execute("SELECT last_insert_rowid();").fetchone()[0]
                if operation == "insert"
                else None
            )
        return response


_EXECUTOR: Optional[HistorySQLExecutor] = None


def get_history_sql_executor() -> HistorySQLExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = HistorySQLExecutor()
    return _EXECUTOR


def _reset_history_sql_executor_for_tests():
    global _EXECUTOR
    if _EXECUTOR is not None:
        try:
            _EXECUTOR.close()
        except Exception:
            pass
        _EXECUTOR = None


__all__ = [
    "HistorySQLExecutor",
    "HistorySQLExecutionError",
    "get_history_sql_executor",
    "_reset_history_sql_executor_for_tests",
]
