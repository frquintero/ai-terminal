#!/usr/bin/env python3
"""
Test for long option argument bypass fix (bd ai-terminal-78s).

The interactive command guard should properly handle long options with separate arguments:
- env --unset PATH python (should block - REPL)
- sudo --user root vim (should block - interactive editor)
- env --chdir /tmp bash (should block - REPL)
- sudo --user=root vim (should block - with = separator)
- env --ignore-environment python (should block - no-arg option)
"""

import sys
from tools import TOOLS

def test_long_option_bypass():
    """Test that long option arguments don't bypass interactive command guard"""
    print("=" * 60)
    print("TEST: Long Option Argument Bypass Fix")
    print("=" * 60)
    
    run_tool = TOOLS['run_command']
    
    # Test 1: env --unset PATH python (should be blocked)
    print("\nTest 1: env --unset PATH python")
    result = run_tool.execute('env --unset PATH python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env --unset PATH python should be blocked (interactive REPL)"
    print("✓ Correctly blocked: env --unset PATH python")
    
    # Test 2: sudo --user root vim (should be blocked)
    print("\nTest 2: sudo --user root vim")
    result = run_tool.execute('sudo --user root vim')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "sudo --user root vim should be blocked (interactive editor)"
    print("✓ Correctly blocked: sudo --user root vim")
    
    # Test 3: env --chdir /tmp bash (should be blocked)
    print("\nTest 3: env --chdir /tmp bash")
    result = run_tool.execute('env --chdir /tmp bash')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env --chdir /tmp bash should be blocked (interactive shell)"
    print("✓ Correctly blocked: env --chdir /tmp bash")
    
    # Test 4: sudo --user=root vim (should be blocked - with = separator)
    print("\nTest 4: sudo --user=root vim")
    result = run_tool.execute('sudo --user=root vim')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "sudo --user=root vim should be blocked"
    print("✓ Correctly blocked: sudo --user=root vim")
    
    # Test 5: env --ignore-environment python (no-arg option, should be blocked)
    print("\nTest 5: env --ignore-environment python")
    result = run_tool.execute('env --ignore-environment python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env --ignore-environment python should be blocked"
    print("✓ Correctly blocked: env --ignore-environment python")
    
    # Test 6: sudo --user root ls (should be allowed - ls is safe)
    print("\nTest 6: sudo --user root ls")
    result = run_tool.execute('sudo --user root ls')
    assert 'InteractiveCommandTool' not in result, \
        "sudo --user root ls should be allowed (ls is not interactive)"
    print("✓ Correctly allowed: sudo --user root ls")
    
    # Test 7: env --unset PATH --unset HOME python (multiple long options)
    print("\nTest 7: env --unset PATH --unset HOME python")
    result = run_tool.execute('env --unset PATH --unset HOME python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env --unset PATH --unset HOME python should be blocked (multiple long options)"
    print("✓ Correctly blocked: env --unset PATH --unset HOME python")
    
    # Test 8: sudo --user root --group admin vim (multiple long options)
    print("\nTest 8: sudo --user root --group admin vim")
    result = run_tool.execute('sudo --user root --group admin vim')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "sudo --user root --group admin vim should be blocked"
    print("✓ Correctly blocked: sudo --user root --group admin vim")
    
    # Test 9: Mix short and long options - env -i --unset PATH python
    print("\nTest 9: env -i --unset PATH python")
    result = run_tool.execute('env -i --unset PATH python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env -i --unset PATH python should be blocked (mixed options)"
    print("✓ Correctly blocked: env -i --unset PATH python")
    
    # Test 10: env --unset PATH python --version (safe flag)
    print("\nTest 10: env --unset PATH python --version")
    result = run_tool.execute('env --unset PATH python --version')
    assert 'Python' in result or 'python' in result, \
        "env --unset PATH python --version should be allowed (safe flag)"
    print("✓ Correctly allowed: env --unset PATH python --version")
    
    # Test 11: Regression - grep python should still work
    print("\nTest 11: grep python file.txt (regression)")
    write_tool = TOOLS['write_file']
    write_tool.execute('long_opts_test.txt', 'python\njava\npython3')
    result = run_tool.execute('grep python long_opts_test.txt')
    assert 'python' in result and 'InteractiveCommandTool' not in result, \
        "grep python should work (not blocked)"
    print("✓ Correctly allowed: grep python file.txt (regression check passed)")
    
    # Test 12: Combination of all fixes - PATH=/tmp sudo --user root -E vim
    print("\nTest 12: PATH=/tmp sudo --user root -E vim (all fixes combined)")
    result = run_tool.execute('PATH=/tmp sudo --user root -E vim')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "PATH=/tmp sudo --user root -E vim should be blocked (combining all fixes)"
    print("✓ Correctly blocked: PATH=/tmp sudo --user root -E vim")
    
    print("\n" + "=" * 60)
    print("✅ ALL LONG OPTION TESTS PASSED")
    print("=" * 60)


def main():
    try:
        test_long_option_bypass()
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
