#!/usr/bin/env python3
"""
Test script to verify the regression fixes
"""

import os
import sys
import tempfile
from tools import WriteFileTool, RunCommandTool, InteractiveCommandTool

def test_write_file_in_cwd():
    """Test that write_file works for files in current directory"""
    tool = WriteFileTool()
    
    # Test writing to current directory
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        result = tool.execute("test.txt", "Hello World")
        assert "successfully" in result, f"Failed: {result}"
        assert os.path.exists("test.txt"), "File was not created"
        with open("test.txt", "r") as f:
            assert f.read() == "Hello World"
    print("✓ write_file in CWD works correctly")

def test_write_file_with_dirs():
    """Test that write_file works for files in subdirectories"""
    tool = WriteFileTool()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        result = tool.execute("subdir/test.txt", "Hello World")
        assert "successfully" in result, f"Failed: {result}"
        assert os.path.exists("subdir/test.txt"), "File was not created"
    print("✓ write_file with subdirectories works correctly")

def test_run_command_blocks_interactive():
    """Test that run_command blocks interactive commands"""
    tool = RunCommandTool()
    
    # Test blocking vim
    result = tool.execute("vim test.txt")
    assert "interactive command" in result.lower(), f"Should block vim: {result}"
    assert "run_interactive" in result.lower(), f"Should suggest run_interactive: {result}"
    
    # Test blocking nano
    result = tool.execute("nano test.txt")
    assert "interactive command" in result.lower(), f"Should block nano: {result}"
    
    # Test blocking top
    result = tool.execute("top")
    assert "interactive command" in result.lower(), f"Should block top: {result}"
    
    print("✓ run_command correctly blocks interactive commands")

def test_interactive_tool_tty_check():
    """Test that run_interactive checks for TTY"""
    tool = InteractiveCommandTool()
    
    # This test will pass if running in a TTY, or fail with the right message if not
    result = tool.execute("echo test")
    
    if sys.stdin.isatty():
        # Should execute
        assert "successfully" in result.lower() or "completed" in result.lower(), f"Should execute: {result}"
        print("✓ run_interactive executes when TTY available")
    else:
        # Should fail with TTY error
        assert "tty" in result.lower(), f"Should require TTY: {result}"
        print("✓ run_interactive correctly checks for TTY")

if __name__ == "__main__":
    print("Testing regression fixes...\n")
    
    try:
        test_write_file_in_cwd()
        test_write_file_with_dirs()
        test_run_command_blocks_interactive()
        test_interactive_tool_tty_check()
        
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
