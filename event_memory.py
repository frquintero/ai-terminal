"""
Event-driven memory utilities for MiniAgent.

Provides:
- EventLog: append-only JSONL log per session
- EventRetriever: priority-aware selection of past events for prompts
- Memory formatting helpers
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


class EventLog:
    """
    Append-only JSONL log for session events.

    Each call to `append` stores a JSON object with at least:
    {
        "type": "...",
        "timestamp": "..."
        ...payload...
    }
    """

    def __init__(
        self,
        session_id: str,
        base_dir: str | Path = "logs/events",
        retention_days: int = 7,
    ):
        self.session_id = session_id
        self.base_dir = Path(base_dir)
        _ensure_dir(self.base_dir)
        self.path = self.base_dir / f"{session_id}.jsonl"
        self.retention_days = max(retention_days, 1)

    def append(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Append an event to the JSONL file and return the stored object."""
        entry: Dict[str, Any] = {
            "type": event_type,
            "timestamp": _utcnow().isoformat(),
        }
        if payload:
            entry.update(payload)

        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def read_recent(self, max_events: Optional[int] = None) -> List[Dict[str, Any]]:
        """Read events from disk (optionally limited to last N)."""
        if not self.path.exists():
            return []

        events: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event["_seq"] = line_no
                events.append(event)

        if max_events is not None and len(events) > max_events:
            events = events[-max_events:]
        return events

    def summarize(self, window: int = 200) -> Dict[str, Any]:
        """Return summary stats for get_context."""
        recent = self.read_recent(window)
        errors = sum(
            1
            for e in recent
            if e.get("type") == "error" or (e.get("type") == "tool_result" and not e.get("success", True))
        )
        tool_calls = sum(1 for e in recent if e.get("type") == "tool_call")
        artifacts = sum(1 for e in recent if e.get("artifact_path"))
        return {
            "total_events": len(recent),
            "errors": errors,
            "tool_calls": tool_calls,
            "artifacts_created": artifacts,
            "event_log_path": str(self.path),
        }

    def cleanup_old_logs(self):
        """Delete event logs older than retention period."""
        cutoff = _utcnow() - timedelta(days=self.retention_days)
        for log_path in self.base_dir.glob("*.jsonl"):
            try:
                mtime = datetime.fromtimestamp(log_path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime < cutoff:
                try:
                    log_path.unlink()
                except OSError:
                    pass


@dataclass
class EventRetrieverConfig:
    max_events: int = 40
    max_chars: int = 6000
    error_limit: int = 5
    tool_result_limit: int = 15
    summary_limit: int = 5
    support_limit: int = 10


class EventRetriever:
    """Priority-aware selection of historical events for prompt injection."""

    def __init__(self, config: Optional[EventRetrieverConfig] = None):
        self.config = config or EventRetrieverConfig()

    @staticmethod
    def _is_error(event: Dict[str, Any]) -> bool:
        if event.get("type") == "error":
            return True
        if event.get("type") == "tool_result":
            return not event.get("success", True)
        return False

    def retrieve(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return prioritized events honoring configured caps."""
        if not events:
            return []

        errors: List[Dict[str, Any]] = []
        tool_results: List[Dict[str, Any]] = []
        summaries: List[Dict[str, Any]] = []
        supporting: List[Dict[str, Any]] = []

        for event in reversed(events):
            if self._is_error(event):
                if len(errors) < self.config.error_limit:
                    errors.append(event)
                continue
            if event.get("type") == "tool_result":
                if len(tool_results) < self.config.tool_result_limit:
                    tool_results.append(event)
                continue
            if event.get("type") == "summary":
                if len(summaries) < self.config.summary_limit:
                    summaries.append(event)
                continue
            if len(supporting) < self.config.support_limit:
                supporting.append(event)

            total = len(errors) + len(tool_results) + len(summaries) + len(supporting)
            if total >= self.config.max_events:
                break

        combined = []
        for bucket in (errors, tool_results, summaries, supporting):
            for event in reversed(bucket):
                combined.append(event)

        # Ensure overall cap and chronological order
        combined = sorted(combined, key=lambda e: e.get("_seq", 0))
        if len(combined) > self.config.max_events:
            combined = combined[-self.config.max_events :]
        return combined

    def format_memory_block(self, events: List[Dict[str, Any]]) -> Optional[str]:
        """Format events as JSONL lines within a system message."""
        if not events:
            return None

        lines: List[str] = []
        total_chars = 0
        for event in events:
            payload = dict(event)
            payload.pop("_seq", None)
            line = json.dumps(payload, ensure_ascii=False)
            total_chars += len(line) + 1
            if total_chars > self.config.max_chars:
                break
            lines.append(line)

        if not lines:
            return None

        header = (
            "Agent Memory (recent high-signal events):\n"
            "Rules: Reference artifact_summary directly. Only call read_file on artifact_path when the user "
            "explicitly needs the underlying data."
        )
        return header + "\n" + "\n".join(lines)


def summarize_event_log(session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Helper for get_context to read summary without full EventLog wiring."""
    if not session_id:
        return None
    log = EventLog(session_id)
    if not log.path.exists():
        return None
    return log.summarize()
