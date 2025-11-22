#!/usr/bin/env python3
"""
Test enhanced get_context functionality.

Validates that get_context returns all expected fields:
- Backward compatible: working_dir, shell_cwd, recent_writes
- New: session, tool_history, available_tools, recent_errors, configuration, repository, capabilities, activity
"""

import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import GetContextTool, _SESSION_STATE, TOOLS, _RECENT_FILE_EVENTS

def test_get_context_structure():
    """Test that get_context returns expected JSON structure"""
    _SESSION_STATE.reset("test-session-123")
    _RECENT_FILE_EVENTS.clear()
    write_tool = TOOLS["write_file"]
    write_tool.execute("context_meta/test.txt", "context verification")
    
    # Simulate tool calls/errors
    _SESSION_STATE.record_tool_call(
        tool_name="run_command",
        args={"command": "ls -la"},
        success=True,
        exit_code=0
    )
    _SESSION_STATE.record_tool_call(
        tool_name="read_file",
        args={"file_path": "test.txt"},
        success=False,
        error="File not found"
    )
    _SESSION_STATE.record_error(
        tool_name="read_file",
        error="File not found",
        context={"file_path": "test.txt"}
    )
    _SESSION_STATE.set_last_exit_code(0)
    
    output = GetContextTool().execute()
    assert "stdout" in output, "get_context must return stdout for strict mode"
    result = json.loads(output["stdout"])
    
    required_fields = ["working_dir", "shell_cwd", "recent_writes"]
    for field in required_fields:
        assert field in result, f"Missing backward compatible field: {field}"
    
    new_fields = [
        "session",
        "tool_history",
        "available_tools",
        "recent_errors",
        "configuration",
        "capabilities",
        "activity",
        "filesystem"
    ]
    for field in new_fields:
        assert field in result, f"Missing new field: {field}"
    
    session = result["session"]
    session_fields = ["id", "start_time", "duration_seconds", "total_interactions", "total_tool_calls"]
    for field in session_fields:
        assert field in session, f"Missing session field: {field}"
    assert session["id"] == "test-session-123"
    
    tool_history = result["tool_history"]
    assert len(tool_history) == 2
    assert tool_history[0]["tool"] == "run_command"
    assert tool_history[0]["exit_code"] == 0
    
    recent_errors = result["recent_errors"]
    assert len(recent_errors) == 1
    
    available_tools = result["available_tools"]
    assert "all" in available_tools
    assert isinstance(available_tools["all"], list)
    
    config = result["configuration"]
    assert "isolation" in config
    
    isolation = config["isolation"]
    isolation_fields = ["requested", "enabled", "active", "rootfs_sha256", "status"]
    for field in isolation_fields:
        assert field in isolation, f"Missing isolation field: {field}"
    
    capabilities = result["capabilities"]
    assert "interpreters_available" in capabilities
    interpreters = capabilities["interpreters_available"]
    expected_interpreters = ["python", "python3", "node", "ruby", "bash", "perl"]
    for interp in expected_interpreters:
        assert interp in interpreters, f"Missing interpreter: {interp}"
    
    activity = result["activity"]
    assert "last_command_exit_code" in activity
    assert activity["last_command_exit_code"] == 0

    filesystem = result["filesystem"]
    assert filesystem["workspace_root"].endswith("ai-terminal-wd")
    assert "recent_activity" in filesystem
    assert isinstance(filesystem["recent_activity"], list)
    assert filesystem["recent_activity"], "Expected at least one filesystem event"
    last_event = filesystem["recent_activity"][-1]
    assert last_event["operation"] == "write"
    assert last_event["source"] == "write_file"
    assert last_event["interactive_hint"].endswith("context_meta/test.txt")

def test_bounded_history():
    """Test that tool_history and recent_errors are bounded"""
    _SESSION_STATE.reset("test-session-bounded")
    
    for i in range(25):
        _SESSION_STATE.record_tool_call(
            tool_name="test_tool",
            args={"index": i},
            success=True
        )
    
    for i in range(5):
        _SESSION_STATE.record_error(
            tool_name="test_tool",
            error=f"Error {i}"
        )
    
    output = GetContextTool().execute()
    assert "stdout" in output
    result = json.loads(output["stdout"])
    
    assert len(result["tool_history"]) == 10
    first_index = json.loads(result["tool_history"][0]["args"])["index"]
    assert first_index == 15
    
    assert len(result["recent_errors"]) == 3
    
