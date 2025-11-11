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


def test_memory_block_compacts_tool_results():
    cfg = EventRetrieverConfig(max_events=5, max_chars=500)
    retriever = EventRetriever(cfg)

    events = [
        {
            "type": "tool_result",
            "timestamp": "2025-11-10T22:10:39.544729+00:00",
            "tool": "run_command",
            "success": True,
            "exit_code": 0,
            "artifact_summary": "find . -name \"*.txt\" -type f | wc -l",
            "output_preview": "14 " + ("x" * 400),
            "_seq": 1,
        }
    ]

    block = retriever.format_memory_block(events)
    assert block is not None
    payload = json.loads(block.splitlines()[-1])
    assert payload["tool"] == "run_command"
    assert payload["success"] is True
    assert len(payload["output_preview"]) <= retriever.TOOL_OUTPUT_PREVIEW_LIMIT
    assert payload["output_preview"].startswith("find . -name")
    assert payload["artifact_summary"].startswith("find . -name")
    assert "exit_code" in payload
    assert "output_preview" in payload


def test_memory_block_includes_call_id():
    cfg = EventRetrieverConfig(max_events=5, max_chars=500)
    retriever = EventRetriever(cfg)

    events = [
        {
            "type": "tool_call",
            "timestamp": "2025-11-10T22:00:00Z",
            "tool": "read_file",
            "tool_call_id": "call-42",
            "_seq": 0,
        },
        {
            "type": "tool_result",
            "timestamp": "2025-11-10T22:00:01Z",
            "tool": "read_file",
            "tool_call_id": "call-42",
            "success": True,
            "output_preview": "data",
            "_seq": 1,
        }
    ]

    block = retriever.format_memory_block(events)
    assert block is not None
    payloads = [json.loads(line) for line in block.splitlines()[2:]]
    assert any(payload.get("tool_call_id") == "call-42" for payload in payloads)


def test_memory_block_compacts_user_messages():
    cfg = EventRetrieverConfig(max_events=5, max_chars=500)
    retriever = EventRetriever(cfg)

    events = [
        {
            "type": "user_message",
            "timestamp": "2025-11-10T20:15:13.001681+00:00",
            "content_preview": "remember my CV? " * 40,
            "length": 999,
            "_seq": 0,
        }
    ]

    block = retriever.format_memory_block(events)
    assert block is not None
    payload = json.loads(block.splitlines()[-1])
    assert "length" not in payload
    assert payload["type"] == "user_message"
    assert len(payload["content_preview"]) <= retriever.MESSAGE_PREVIEW_LIMIT
    assert payload["content_preview"].startswith("remember my CV?")
