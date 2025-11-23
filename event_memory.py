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
        base_dir: Union[str, Path] = "logs/events",
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

    TOOL_OUTPUT_PREVIEW_LIMIT = 160
    TOOL_ARGS_PREVIEW_LIMIT = 160
    MESSAGE_PREVIEW_LIMIT = 220

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
            payload = self._compact_event_for_memory(event)
            if not payload:
                continue
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

    @staticmethod
    def _truncate_text(value: Optional[str], limit: int) -> Optional[str]:
        if not value:
            return None
        text = str(value)
        if len(text) <= limit:
            return text
        ellipsis = "..." if limit >= 3 else ""
        slice_len = max(limit - len(ellipsis), 0)
        return text[:slice_len] + ellipsis

    def _compact_event_for_memory(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Strip bulky fields so Agent Memory stays lightweight."""
        event_type = event.get("type") or "unknown"
        compact: Dict[str, Any] = {
            "type": event_type,
            "timestamp": event.get("timestamp"),
        }

        if event_type == "tool_result":
            compact["tool"] = event.get("tool")
            compact["success"] = event.get("success", True)
            if event.get("exit_code") is not None:
                compact["exit_code"] = event.get("exit_code")
            if event.get("artifact_summary"):
                compact["artifact_summary"] = event.get("artifact_summary")
            if event.get("artifact_path"):
                compact["artifact_path"] = event.get("artifact_path")
            if event.get("tool_call_id"):
                compact["tool_call_id"] = event.get("tool_call_id")
            preview = (
                event.get("artifact_summary")
                or event.get("output_preview")
            )
            preview = self._truncate_text(preview, self.TOOL_OUTPUT_PREVIEW_LIMIT)
            if preview:
                compact["output_preview"] = preview
        elif event_type == "tool_call":
            compact["tool"] = event.get("tool")
            args_preview = self._truncate_text(
                event.get("args_preview"),
                self.TOOL_ARGS_PREVIEW_LIMIT,
            )
            if args_preview:
                compact["args_preview"] = args_preview
            if event.get("tool_call_id"):
                compact["tool_call_id"] = event.get("tool_call_id")
        elif event_type in ("user_message", "assistant_response"):
            preview = self._truncate_text(
                event.get("content_preview"),
                self.MESSAGE_PREVIEW_LIMIT,
            )
            if preview:
                key = "content_preview"
                compact[key] = preview
        elif event_type == "error":
            compact["source"] = event.get("source")
            err = self._truncate_text(event.get("error"), self.MESSAGE_PREVIEW_LIMIT)
            if err:
                compact["error"] = err
        elif event_type == "summary":
            summary = self._truncate_text(
                event.get("summary") or event.get("note"),
                self.MESSAGE_PREVIEW_LIMIT,
            )
            if summary:
                compact["summary"] = summary
        else:
            fallback = self._truncate_text(
                event.get("content_preview")
                or event.get("summary")
                or event.get("output_preview"),
                self.MESSAGE_PREVIEW_LIMIT,
            )
            if fallback:
                compact["summary"] = fallback

        # Remove empty/None values to keep payload tight
        return {k: v for k, v in compact.items() if v not in (None, "")}


def summarize_event_log(session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Helper for get_context to read summary without full EventLog wiring."""
    if not session_id:
        return None
    log = EventLog(session_id)
    if not log.path.exists():
        return None
    return log.summarize()
