#!/usr/bin/env python3
"""
Test script to verify the regression fixes
"""

import os
import sys
import tempfile
import json

from tools import WriteFileTool, RunCommandTool, InteractiveCommandTool
from command_parser import parse_command

def test_write_file_in_cwd():
    """Test that write_file works for files in current directory"""
    tool = WriteFileTool()
    
    # Test writing to current directory
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        result = tool.execute("test.txt", "Hello World")
        assert result["success"], f"Failed: {result}"
        assert "successfully" in result["message"].lower()
        assert os.path.exists(result["path"]), "File was not created in sandbox"
        with open(result["path"], "r") as f:
            assert f.read() == "Hello World"
    print("✓ write_file in CWD works correctly")

def test_write_file_with_dirs():
    """Test that write_file works for files in subdirectories"""
    tool = WriteFileTool()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        result = tool.execute("subdir/test.txt", "Hello World")
        assert result["success"], f"Failed: {result}"
        assert "successfully" in result["message"].lower()
        assert os.path.exists(result["path"]), "File was not created in sandbox"
    print("✓ write_file with subdirectories works correctly")

def test_run_command_blocks_interactive():
    """Test that run_command blocks interactive commands"""
    tool = RunCommandTool()
    
    # Test blocking vim
    result = tool.execute("vim test.txt")
    stderr = (result.get("stderr") or "").lower()
    assert "interactive command" in stderr, f"Should block vim: {result}"
    assert "run_interactive" in stderr, f"Should suggest run_interactive: {result}"
    
    # Test blocking nano
    result = tool.execute("nano test.txt")
    assert "interactive command" in (result.get("stderr") or "").lower(), f"Should block nano: {result}"
    
    # Test blocking top
    result = tool.execute("top")
    assert "interactive command" in (result.get("stderr") or "").lower(), f"Should block top: {result}"
    
    print("✓ run_command correctly blocks interactive commands")

def test_run_command_allows_man_with_cat_pager():
    """Verify MANPAGER=cat man ... is treated as non-interactive."""
    interactive, reason = parse_command("MANPAGER=cat man printf")
    assert not interactive, f"MANPAGER=cat should disable pager detection (reason={reason})"
    print("✓ MANPAGER=cat man ... allowed by command parser")


def test_run_interactive_session_flow():
    """Ensure run_interactive sessions emit prompts and can be completed."""
    tool = InteractiveCommandTool()
    command = "python3 -c \"print('start'); input('Press y to continue: '); print('done')\""
    result = tool.execute(command=command, timeout=1.0)
    assert result["success"], f"Session should start: {result}"
    assert result["status"] in {"waiting_for_input", "awaiting_output"}, "Should await input after prompt"
    assert result.get("session_id"), "Session id required"
    agent_message = json.loads(result.get("agent_message"))
    assert agent_message["status"] in {"waiting_for_input", "awaiting_output"}
    session_id = result["session_id"]
    
    # Respond to prompt
    follow_up = tool.execute(session_id=session_id, input_text="y\n", timeout=1.0)
    assert follow_up["success"], f"Follow-up failed: {follow_up}"
    assert follow_up["status"] in {"completed", "awaiting_output"}, "Should progress after sending input"
    if follow_up["status"] == "completed":
        assert "done" in follow_up["stdout"], "Should capture final output"
    else:
        # Send another newline to finish
        final = tool.execute(session_id=session_id, input_text="\n", timeout=1.0)
        assert final["status"] == "completed", "Session should complete after newline"
    print("✓ run_interactive PTY session lifecycle works")

if __name__ == "__main__":
    print("Testing regression fixes...\n")
    
    try:
        test_write_file_in_cwd()
        test_write_file_with_dirs()
        test_run_command_blocks_interactive()
        test_run_command_allows_man_with_cat_pager()
        test_run_interactive_session_flow()
        
        print("\n✓ All regression fixes verified!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
