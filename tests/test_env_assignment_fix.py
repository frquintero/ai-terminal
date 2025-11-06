#!/usr/bin/env python3
"""
Test for environment variable assignment bypass fix (bd ai-terminal-2lr).

The interactive command guard should now properly detect commands like:
- PATH=/tmp python (should block unless safe flags)
- EDITOR=vim command (should detect vim and block)
- env VAR=x python (should detect python and block)
"""

import sys
from tools import TOOLS

def test_env_assignment_bypass():
    """Test that env assignments don't bypass interactive command guard"""
    print("=" * 60)
    print("TEST: Environment Assignment Bypass Fix")
    print("=" * 60)
    
    run_tool = TOOLS['run_command']
    
    # Test 1: PATH=/tmp python (should be blocked - REPL)
    print("\nTest 1: PATH=/tmp python")
    result = run_tool.execute('PATH=/tmp python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "PATH=/tmp python should be blocked (interactive REPL)"
    print("✓ Correctly blocked: PATH=/tmp python")
    
    # Test 2: PATH=/tmp python --version (should be allowed - safe flag)
    print("\nTest 2: PATH=/tmp python --version")
    result = run_tool.execute('PATH=/tmp python --version')
    assert 'Python' in result or 'python' in result, \
        "PATH=/tmp python --version should be allowed (safe flag)"
    print("✓ Correctly allowed: PATH=/tmp python --version")
    
    # Test 3: PATH=/tmp python -c "print('ok')" (should be allowed - script mode)
    print("\nTest 3: PATH=/tmp python -c \"print('ok')\"")
    result = run_tool.execute('PATH=/tmp python -c "print(\'ok\')"')
    assert 'ok' in result or 'InteractiveCommandTool' not in result, \
        "PATH=/tmp python -c should be allowed (script execution)"
    print("✓ Correctly allowed: PATH=/tmp python -c")
    
    # Test 4: env HOME=/tmp python (should be blocked)
    print("\nTest 4: env HOME=/tmp python")
    result = run_tool.execute('env HOME=/tmp python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env HOME=/tmp python should be blocked"
    print("✓ Correctly blocked: env HOME=/tmp python")
    
    # Test 5: VAR=1 VAR2=2 bash (should be blocked - REPL)
    print("\nTest 5: VAR=1 VAR2=2 bash")
    result = run_tool.execute('VAR=1 VAR2=2 bash')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "VAR=1 VAR2=2 bash should be blocked"
    print("✓ Correctly blocked: VAR=1 VAR2=2 bash")
    
    # Test 6: VAR=1 only (assignment-only, should be allowed)
    print("\nTest 6: VAR=1 (assignment-only)")
    result = run_tool.execute('VAR=1')
    # Assignment-only commands are allowed
    assert 'InteractiveCommandTool' not in result, \
        "VAR=1 (assignment-only) should be allowed"
    print("✓ Correctly allowed: VAR=1")
    
    # Test 7: grep python file.txt (should still work - not interactive)
    print("\nTest 7: grep python file.txt (regression check)")
    # Create test file first
    write_tool = TOOLS['write_file']
    write_tool.execute('test_grep.txt', 'python is great\njava too\npython rocks')
    result = run_tool.execute('grep python test_grep.txt')
    assert 'python is great' in result, \
        "grep python should work (not blocked)"
    print("✓ Correctly allowed: grep python file.txt (regression check passed)")
    
    # Test 8: sudo EDITOR=vim command (should detect 'command' not 'vim')
    print("\nTest 8: sudo EDITOR=vim ls")
    result = run_tool.execute('sudo EDITOR=vim ls')
    # This should work because 'ls' is not interactive
    # The guard should skip sudo, skip EDITOR=vim, and see 'ls'
    assert 'InteractiveCommandTool' not in result, \
        "sudo EDITOR=vim ls should be allowed (ls is safe)"
    print("✓ Correctly allowed: sudo EDITOR=vim ls")
    
    print("\n" + "=" * 60)
    print("✅ ALL ENV ASSIGNMENT TESTS PASSED")
    print("=" * 60)


def main():
    try:
        test_env_assignment_bypass()
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
