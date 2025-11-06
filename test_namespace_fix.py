#!/usr/bin/env python3
"""
Integration test for namespace confusion fix.

Tests:
1. Stateless run_command (cwd always resets to working_dir)
2. File write tracking
3. get_context tool
4. No redundant pwd/ls needed
"""

import sys
import json
from tools import TOOLS, _RECENT_WRITES

def test_stateless_run_command():
    """Test that run_command always executes from working_dir"""
    print("=" * 60)
    print("TEST 1: Stateless run_command")
    print("=" * 60)
    
    run_tool = TOOLS['run_command']
    
    # Write a test file
    write_tool = TOOLS['write_file']
    write_tool.execute('stateless_test.txt', 'Test content')
    
    # Verify we can see it
    result1 = run_tool.execute('ls stateless_test.txt')
    assert 'stateless_test.txt' in result1, "Should see file in working dir"
    print("✓ File visible in working dir")
    
    # Try to change directory within a command
    result2 = run_tool.execute('cd /tmp && pwd')
    assert '/tmp' in result2, "Should execute cd /tmp"
    print("✓ cd /tmp works within command")
    
    # Next command should still be in working dir (stateless)
    result3 = run_tool.execute('ls stateless_test.txt')
    assert 'stateless_test.txt' in result3, "Should still see file (cwd reset)"
    print("✓ cwd reset to working_dir after cd /tmp")
    
    # Try reading project file with ../
    result4 = run_tool.execute('cat ../agent.py | head -5')
    assert 'MiniAgent' in result4 or 'import' in result4, "Should read project file"
    print("✓ Can read project files with ../path")
    
    print("\n✅ TEST 1 PASSED: run_command is stateless\n")


def test_file_write_tracking():
    """Test that file writes are tracked"""
    print("=" * 60)
    print("TEST 2: File write tracking")
    print("=" * 60)
    
    # Clear previous writes
    _RECENT_WRITES.clear()
    
    write_tool = TOOLS['write_file']
    
    # Write some files
    files = ['track1.txt', 'track2.txt', 'subdir/track3.txt']
    for f in files:
        write_tool.execute(f, f'Content of {f}')
    
    # Check tracking
    tracked = list(_RECENT_WRITES)
    print(f"Tracked files: {tracked}")
    
    for f in files:
        assert f in tracked, f"File {f} should be tracked"
        print(f"✓ {f} tracked")
    
    print("\n✅ TEST 2 PASSED: File writes are tracked\n")


def test_get_context_tool():
    """Test get_context tool"""
    print("=" * 60)
    print("TEST 3: get_context tool")
    print("=" * 60)
    
    # Clear and write a file
    _RECENT_WRITES.clear()
    write_tool = TOOLS['write_file']
    write_tool.execute('context_test.txt', 'Test')
    
    # Get context
    ctx_tool = TOOLS['get_context']
    result = ctx_tool.execute()
    context = json.loads(result)
    
    print(f"Context: {json.dumps(context, indent=2)}")
    
    # Verify structure
    assert 'working_dir' in context, "Should have working_dir"
    assert 'shell_cwd' in context, "Should have shell_cwd"
    assert 'recent_writes' in context, "Should have recent_writes"
    print("✓ Context has all required fields")
    
    # Verify working_dir is set
    assert context['working_dir'].endswith('ai-terminal-wd'), "working_dir should end with ai-terminal-wd"
    print(f"✓ working_dir: {context['working_dir']}")
    
    # Verify recent writes
    assert 'context_test.txt' in context['recent_writes'], "Should track recent write"
    print(f"✓ recent_writes: {context['recent_writes']}")
    
    print("\n✅ TEST 3 PASSED: get_context works correctly\n")


def test_no_pwd_needed():
    """Test that we don't need pwd to know where we are"""
    print("=" * 60)
    print("TEST 4: No redundant pwd/ls needed")
    print("=" * 60)
    
    # Scenario: Write file, then run it
    # Old behavior: write_file → pwd → ls → run
    # New behavior: write_file → run (use get_context if needed)
    
    _RECENT_WRITES.clear()
    write_tool = TOOLS['write_file']
    ctx_tool = TOOLS['get_context']
    run_tool = TOOLS['run_command']
    
    # Write a script
    script = '''#!/bin/bash
echo "Hello from script"
echo "PWD: $PWD"
'''
    write_tool.execute('test_script.sh', script)
    
    # Check context to see what was written (no pwd/ls needed)
    context = json.loads(ctx_tool.execute())
    assert 'test_script.sh' in context['recent_writes'], "Script should be tracked"
    print("✓ Script tracked via get_context (no pwd/ls needed)")
    
    # Make executable and run (using relative path)
    run_tool.execute('chmod +x test_script.sh')
    result = run_tool.execute('./test_script.sh')
    
    assert 'Hello from script' in result, "Script should execute"
    assert 'ai-terminal-wd' in result, "Should run from working_dir"
    print("✓ Script executes from correct directory")
    
    print("\n✅ TEST 4 PASSED: No redundant navigation commands needed\n")


def test_consolidated_python():
    """Test that Python demos can be consolidated"""
    print("=" * 60)
    print("TEST 5: Consolidated Python execution")
    print("=" * 60)
    
    # Write a Python script with multiple demos (instead of multiple sandbox calls)
    script = '''#!/usr/bin/env python3
"""Consolidated demos instead of multiple run_python_sandbox calls"""

def demo_strings():
    print("=== String Demo ===")
    print("Hello, World!".upper())

def demo_math():
    print("=== Math Demo ===")
    print(f"2 + 2 = {2 + 2}")

def demo_lists():
    print("=== List Demo ===")
    nums = [1, 2, 3, 4, 5]
    print(f"Sum: {sum(nums)}")

if __name__ == "__main__":
    demo_strings()
    demo_math()
    demo_lists()
'''
    
    write_tool = TOOLS['write_file']
    run_tool = TOOLS['run_command']
    
    # Write consolidated script
    write_tool.execute('consolidated_demo.py', script)
    
    # Syntax check (as recommended in prompt)
    check_result = run_tool.execute('python -m py_compile ./consolidated_demo.py')
    assert 'Error' not in check_result or len(check_result) == 0, "Syntax should be valid"
    print("✓ Python syntax check passed")
    
    # Run once instead of multiple sandbox calls
    run_result = run_tool.execute('python ./consolidated_demo.py')
    
    assert 'String Demo' in run_result, "Should run demo 1"
    assert 'Math Demo' in run_result, "Should run demo 2"
    assert 'List Demo' in run_result, "Should run demo 3"
    print("✓ All demos executed in one run")
    
    print("\n✅ TEST 5 PASSED: Python demos can be consolidated\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("INTEGRATION TEST: Namespace Confusion Fix")
    print("=" * 60 + "\n")
    
    try:
        test_stateless_run_command()
        test_file_write_tracking()
        test_get_context_tool()
        test_no_pwd_needed()
        test_consolidated_python()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return 0
    
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
