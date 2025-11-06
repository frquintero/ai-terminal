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

from tools import GetContextTool, _SESSION_STATE, TOOLS

def test_get_context_structure():
    """Test that get_context returns expected JSON structure"""
    print("Testing enhanced get_context structure...")
    
    # Initialize session state (simulate agent startup)
    _SESSION_STATE.reset("test-session-123")
    
    # Simulate some tool calls
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
    
    # Execute get_context
    tool = GetContextTool()
    result_json = tool.execute()
    
    # Parse result
    try:
        result = json.loads(result_json)
    except json.JSONDecodeError as e:
        print(f"❌ FAIL: Invalid JSON returned: {e}")
        return False
    
    # Verify backward compatible fields
    required_fields = ["working_dir", "shell_cwd", "recent_writes"]
    for field in required_fields:
        if field not in result:
            print(f"❌ FAIL: Missing backward compatible field: {field}")
            return False
    
    # Verify new fields
    new_fields = ["session", "tool_history", "available_tools", "recent_errors", 
                  "configuration", "repository", "capabilities", "activity"]
    for field in new_fields:
        if field not in result:
            print(f"❌ FAIL: Missing new field: {field}")
            return False
    
    # Verify session structure
    session = result["session"]
    session_fields = ["id", "start_time", "duration_seconds", "total_interactions", "total_tool_calls"]
    for field in session_fields:
        if field not in session:
            print(f"❌ FAIL: Missing session field: {field}")
            return False
    
    if session["id"] != "test-session-123":
        print(f"❌ FAIL: Session ID mismatch: {session['id']}")
        return False
    
    # Verify tool_history contains our calls
    tool_history = result["tool_history"]
    if len(tool_history) != 2:
        print(f"❌ FAIL: Expected 2 tool calls, got {len(tool_history)}")
        return False
    
    if tool_history[0]["tool"] != "run_command":
        print(f"❌ FAIL: First tool should be run_command, got {tool_history[0]['tool']}")
        return False
    
    if tool_history[0]["exit_code"] != 0:
        print(f"❌ FAIL: Expected exit_code 0, got {tool_history[0].get('exit_code')}")
        return False
    
    # Verify recent_errors
    recent_errors = result["recent_errors"]
    if len(recent_errors) != 1:
        print(f"❌ FAIL: Expected 1 error, got {len(recent_errors)}")
        return False
    
    # Verify available_tools
    available_tools = result["available_tools"]
    if "all" not in available_tools:
        print(f"❌ FAIL: Missing available_tools.all")
        return False
    
    if not isinstance(available_tools["all"], list):
        print(f"❌ FAIL: available_tools.all should be a list")
        return False
    
    # Verify configuration
    config = result["configuration"]
    if "sandbox" not in config or "isolation" not in config:
        print(f"❌ FAIL: Missing configuration.sandbox or configuration.isolation")
        return False
    
    sandbox = config["sandbox"]
    sandbox_fields = ["enabled", "timeout_seconds", "max_memory_mb", "max_cpu_seconds", 
                      "network_disabled", "write_protected"]
    for field in sandbox_fields:
        if field not in sandbox:
            print(f"❌ FAIL: Missing sandbox field: {field}")
            return False
    
    # Verify repository
    repository = result["repository"]
    if "in_repo" not in repository:
        print(f"❌ FAIL: Missing repository.in_repo")
        return False
    
    # Verify capabilities
    capabilities = result["capabilities"]
    if "interpreters_available" not in capabilities:
        print(f"❌ FAIL: Missing capabilities.interpreters_available")
        return False
    
    interpreters = capabilities["interpreters_available"]
    expected_interpreters = ["python", "python3", "node", "ruby", "bash", "perl"]
    for interp in expected_interpreters:
        if interp not in interpreters:
            print(f"❌ FAIL: Missing interpreter: {interp}")
            return False
    
    # Verify activity
    activity = result["activity"]
    if "last_command_exit_code" not in activity:
        print(f"❌ FAIL: Missing activity.last_command_exit_code")
        return False
    
    if activity["last_command_exit_code"] != 0:
        print(f"❌ FAIL: Expected last_command_exit_code 0, got {activity['last_command_exit_code']}")
        return False
    
    print("✅ PASS: All fields present and valid")
    return True

def test_bounded_history():
    """Test that tool_history and recent_errors are bounded"""
    print("\nTesting bounded history limits...")
    
    _SESSION_STATE.reset("test-session-bounded")
    
    # Add 25 tool calls (should keep only last 20)
    for i in range(25):
        _SESSION_STATE.record_tool_call(
            tool_name="test_tool",
            args={"index": i},
            success=True
        )
    
    # Add 5 errors (should keep only last 3)
    for i in range(5):
        _SESSION_STATE.record_error(
            tool_name="test_tool",
            error=f"Error {i}"
        )
    
    tool = GetContextTool()
    result = json.loads(tool.execute())
    
    # Verify tool_history is bounded to 20
    if len(result["tool_history"]) != 20:
        print(f"❌ FAIL: Expected 20 tool_history entries, got {len(result['tool_history'])}")
        return False
    
    # Verify it kept the last 20 (indexes 5-24)
    first_index = json.loads(result["tool_history"][0]["args"])["index"]
    if first_index != 5:
        print(f"❌ FAIL: Expected first tool_history index to be 5, got {first_index}")
        return False
    
    # Verify recent_errors is bounded to 3
    if len(result["recent_errors"]) != 3:
        print(f"❌ FAIL: Expected 3 recent_errors, got {len(result['recent_errors'])}")
        return False
    
    # Verify it kept the last 3 (errors 2-4)
    if "Error 2" not in result["recent_errors"][0]["error"]:
        print(f"❌ FAIL: Expected first error to be 'Error 2', got {result['recent_errors'][0]['error']}")
        return False
    
    print("✅ PASS: History bounded correctly (tool_history=20, recent_errors=3)")
    return True

if __name__ == "__main__":
    print("="*60)
    print("Enhanced get_context Test Suite")
    print("="*60)
    
    tests = [
        test_get_context_structure,
        test_bounded_history
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ FAIL: Test raised exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    
    sys.exit(0 if failed == 0 else 1)
