import json
from pathlib import Path

from event_memory import EventLog, EventRetriever, EventRetrieverConfig


def test_event_log_capture(tmp_path):
    log = EventLog("session-test", base_dir=tmp_path)
    log.append("user_message", {"content_preview": "hello"})
    log.append("tool_call", {"tool": "run_command"})

    events = log.read_recent()
    assert len(events) == 2
    assert events[0]["type"] == "user_message"
    assert events[1]["type"] == "tool_call"

    summary = log.summarize()
    assert summary["total_events"] == 2
    assert summary["tool_calls"] == 1
    assert summary["event_log_path"].endswith("session-test.jsonl")


def test_event_retriever_prioritizes_errors():
    cfg = EventRetrieverConfig(max_events=5, error_limit=2, tool_result_limit=2, support_limit=1)
    retriever = EventRetriever(cfg)

    events = [
        {"type": "tool_result", "success": True, "_seq": 0},
        {"type": "tool_result", "success": False, "_seq": 1},
        {"type": "tool_call", "_seq": 2},
        {"type": "error", "_seq": 3},
        {"type": "tool_result", "success": True, "_seq": 4},
    ]

    prioritized = retriever.retrieve(events)
    error_count = sum(1 for e in prioritized if retriever._is_error(e))
    assert error_count == 2  # includes explicit error + failing tool_result
    assert any(e["type"] == "tool_call" for e in prioritized)


def test_memory_block_respects_char_limit(tmp_path):
    cfg = EventRetrieverConfig(max_events=50, max_chars=120)
    retriever = EventRetriever(cfg)

    events = []
    for i in range(10):
        events.append({"type": "summary", "note": "x" * 40, "_seq": i})

    block = retriever.format_memory_block(events)
    assert block is not None
    lines = block.splitlines()
    payload = lines[2:]  # first two lines are the header/rule text
    payload_chars = sum(len(line) for line in payload)
    assert payload_chars <= cfg.max_chars
