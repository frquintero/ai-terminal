#!/usr/bin/env python3
"""
Test for wrapper option flag bypass fix (bd ai-terminal-v0x).

The interactive command guard should now properly detect commands with wrapper options:
- env -i python (should block - REPL)
- sudo -E vim (should block - interactive editor)
- env -u VAR bash (should block - REPL)
- env -i -u PATH python (multiple options, should block)
- sudo -E ls (should allow - ls is safe)
"""

import sys
from tools import TOOLS

def test_wrapper_option_bypass():
    """Test that wrapper option flags don't bypass interactive command guard"""
    print("=" * 60)
    print("TEST: Wrapper Option Flag Bypass Fix")
    print("=" * 60)
    
    run_tool = TOOLS['run_command']
    
    # Test 1: env -i python (should be blocked - REPL)
    print("\nTest 1: env -i python")
    result = run_tool.execute('env -i python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env -i python should be blocked (interactive REPL)"
    print("✓ Correctly blocked: env -i python")
    
    # Test 2: sudo -E vim (should be blocked - interactive editor)
    print("\nTest 2: sudo -E vim")
    result = run_tool.execute('sudo -E vim')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "sudo -E vim should be blocked (interactive editor)"
    print("✓ Correctly blocked: sudo -E vim")
    
    # Test 3: env -u PATH bash (should be blocked - REPL)
    print("\nTest 3: env -u PATH bash")
    result = run_tool.execute('env -u PATH bash')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env -u PATH bash should be blocked (interactive shell)"
    print("✓ Correctly blocked: env -u PATH bash")
    
    # Test 4: env -i -u VAR python (multiple options, should be blocked)
    print("\nTest 4: env -i -u VAR python")
    result = run_tool.execute('env -i -u VAR python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env -i -u VAR python should be blocked (multiple options)"
    print("✓ Correctly blocked: env -i -u VAR python")
    
    # Test 5: sudo -E ls (should be allowed - ls is safe)
    print("\nTest 5: sudo -E ls")
    result = run_tool.execute('sudo -E ls')
    assert 'InteractiveCommandTool' not in result, \
        "sudo -E ls should be allowed (ls is not interactive)"
    print("✓ Correctly allowed: sudo -E ls")
    
    # Test 6: time -p python (should be blocked)
    print("\nTest 6: time -p python")
    result = run_tool.execute('time -p python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "time -p python should be blocked"
    print("✓ Correctly blocked: time -p python")
    
    # Test 7: env -i python --version (safe flag with option, should be allowed)
    print("\nTest 7: env -i python --version")
    result = run_tool.execute('env -i python --version')
    assert 'Python' in result or 'python' in result, \
        "env -i python --version should be allowed (safe flag)"
    print("✓ Correctly allowed: env -i python --version")
    
    # Test 8: sudo -E -u user vim (multiple wrapper options, should be blocked)
    print("\nTest 8: sudo -E -u user vim")
    result = run_tool.execute('sudo -E -u user vim')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "sudo -E -u user vim should be blocked (multiple options)"
    print("✓ Correctly blocked: sudo -E -u user vim")
    
    # Test 9: Regression - PATH=/tmp sudo vim (assignment + wrapper + options)
    print("\nTest 9: PATH=/tmp sudo -E vim (regression)")
    result = run_tool.execute('PATH=/tmp sudo -E vim')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "PATH=/tmp sudo -E vim should be blocked (combining fixes)"
    print("✓ Correctly blocked: PATH=/tmp sudo -E vim")
    
    # Test 10: env -i VAR=1 python (option + assignment + interactive)
    print("\nTest 10: env -i VAR=1 python")
    result = run_tool.execute('env -i VAR=1 python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env -i VAR=1 python should be blocked"
    print("✓ Correctly blocked: env -i VAR=1 python")
    
    # Test 11: Regression - grep python should still work
    print("\nTest 11: grep python file.txt (regression)")
    write_tool = TOOLS['write_file']
    write_tool.execute('wrapper_opts_test.txt', 'python\njava\npython3')
    result = run_tool.execute('grep python wrapper_opts_test.txt')
    assert 'python' in result and 'InteractiveCommandTool' not in result, \
        "grep python should work (not blocked)"
    print("✓ Correctly allowed: grep python file.txt (regression check passed)")
    
    print("\n" + "=" * 60)
    print("✅ ALL WRAPPER OPTION TESTS PASSED")
    print("=" * 60)


def main():
    try:
        test_wrapper_option_bypass()
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
