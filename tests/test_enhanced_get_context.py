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
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

with patch('shell_integration.ShellIntegration'):
    from tools import GetContextTool, _SESSION_STATE, TOOLS

def test_get_context_structure():
    """Test that get_context returns expected JSON structure"""
    _SESSION_STATE.reset("test-session-123")
    
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
    
    result = json.loads(GetContextTool().execute())
    
    required_fields = ["working_dir", "shell_cwd", "recent_writes"]
    for field in required_fields:
        assert field in result, f"Missing backward compatible field: {field}"
    
    new_fields = [
        "session",
        "tool_history",
        "available_tools",
        "recent_errors",
        "configuration",
        "repository",
        "capabilities",
        "activity"
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
    assert "sandbox" in config and "isolation" in config
    
    sandbox = config["sandbox"]
    sandbox_fields = [
        "enabled",
        "timeout_seconds",
        "max_memory_mb",
        "max_cpu_seconds",
        "network_disabled",
        "write_protected"
    ]
    for field in sandbox_fields:
        assert field in sandbox, f"Missing sandbox field: {field}"
    
    isolation = config["isolation"]
    isolation_fields = ["requested", "enabled", "active", "rootfs_sha256", "status"]
    for field in isolation_fields:
        assert field in isolation, f"Missing isolation field: {field}"
    
    repository = result["repository"]
    assert "in_repo" in repository
    
    capabilities = result["capabilities"]
    assert "interpreters_available" in capabilities
    interpreters = capabilities["interpreters_available"]
    expected_interpreters = ["python", "python3", "node", "ruby", "bash", "perl"]
    for interp in expected_interpreters:
        assert interp in interpreters, f"Missing interpreter: {interp}"
    
    activity = result["activity"]
    assert "last_command_exit_code" in activity
    assert activity["last_command_exit_code"] == 0

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
    
    result = json.loads(GetContextTool().execute())
    
    assert len(result["tool_history"]) == 20
    first_index = json.loads(result["tool_history"][0]["args"])["index"]
    assert first_index == 5
    
    assert len(result["recent_errors"]) == 3
    
