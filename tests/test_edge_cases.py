#!/usr/bin/env python3
"""
Test edge cases for robust command parser.

Tests advanced scenarios from oracle recommendations:
- env -S (ambiguous - should block)
- sudo -i/-s (interactive shell - should block)
- Combined short options (env -iu)
- --opt=value syntax
- bash -c (non-interactive)
- timeout with duration
"""

import sys
from tools import TOOLS

def test_edge_cases():
    """Test edge cases and advanced scenarios"""
    print("=" * 60)
    print("TEST: Edge Cases for Robust Parser")
    print("=" * 60)
    
    run_tool = TOOLS['run_command']
    
    # Test 1: env -S (ambiguous - should block)
    print("\nTest 1: env -S 'python -i' (ambiguous)")
    result = run_tool.execute("env -S 'python -i'")
    assert 'interactive' in result.lower() or 'ambiguous' in result.lower(), \
        "env -S should be blocked (ambiguous parsing)"
    print("✓ Correctly blocked: env -S (ambiguous)")
    
    # Test 2: sudo -i (interactive shell)
    print("\nTest 2: sudo -i (interactive shell)")
    result = run_tool.execute('sudo -i')
    assert 'interactive' in result.lower(), \
        "sudo -i should be blocked (interactive shell)"
    print("✓ Correctly blocked: sudo -i")
    
    # Test 3: sudo -s (interactive shell)
    print("\nTest 3: sudo -s (interactive shell)")
    result = run_tool.execute('sudo -s')
    assert 'interactive' in result.lower(), \
        "sudo -s should be blocked (interactive shell)"
    print("✓ Correctly blocked: sudo -s")
    
    # Test 4: env -iu PATH python (combined short options)
    print("\nTest 4: env -iu PATH python")
    result = run_tool.execute('env -iu PATH python')
    assert 'interactive' in result.lower(), \
        "env -iu PATH python should be blocked"
    print("✓ Correctly blocked: env -iu PATH python")
    
    # Test 5: sudo --user=root vim (--opt=value syntax)
    print("\nTest 5: sudo --user=root vim (--opt=value)")
    result = run_tool.execute('sudo --user=root vim')
    assert 'interactive' in result.lower(), \
        "sudo --user=root vim should be blocked"
    print("✓ Correctly blocked: sudo --user=root vim")
    
    # Test 6: bash -c 'echo ok' (non-interactive)
    print("\nTest 6: bash -c 'echo ok' (non-interactive)")
    result = run_tool.execute("bash -c 'echo ok'")
    assert 'ok' in result and 'interactive' not in result.lower(), \
        "bash -c should be allowed (non-interactive)"
    print("✓ Correctly allowed: bash -c")
    
    # Test 7: timeout 5 bash (should block - bare bash)
    print("\nTest 7: timeout 5 bash")
    result = run_tool.execute('timeout 5 bash')
    assert 'interactive' in result.lower(), \
        "timeout 5 bash should be blocked (bare bash)"
    print("✓ Correctly blocked: timeout 5 bash")
    
    # Test 8: timeout 5 bash -c 'true' (non-interactive)
    print("\nTest 8: timeout 5 bash -c 'true'")
    result = run_tool.execute("timeout 5 bash -c 'true'")
    assert 'interactive' not in result.lower(), \
        "timeout 5 bash -c should be allowed"
    print("✓ Correctly allowed: timeout 5 bash -c")
    
    # Test 9: nice -n 5 bash -c 'echo hi' (non-interactive)
    print("\nTest 9: nice -n 5 bash -c 'echo hi'")
    result = run_tool.execute("nice -n 5 bash -c 'echo hi'")
    assert 'hi' in result and 'interactive' not in result.lower(), \
        "nice -n 5 bash -c should be allowed"
    print("✓ Correctly allowed: nice -n 5 bash -c")
    
    # Test 10: time -o out.txt python (bare python - should block)
    print("\nTest 10: time -o out.txt python")
    result = run_tool.execute('time -o out.txt python')
    assert 'interactive' in result.lower(), \
        "time -o out.txt python should be blocked (bare python)"
    print("✓ Correctly blocked: time -o out.txt python")
    
    # Test 11: python test.py (script - non-interactive)
    print("\nTest 11: python test.py")
    write_tool = TOOLS['write_file']
    write_tool.execute('test.py', 'print("hello from script")')
    result = run_tool.execute('python test.py')
    assert 'hello from script' in result and 'interactive' not in result.lower(), \
        "python test.py should be allowed (script execution)"
    print("✓ Correctly allowed: python test.py")
    
    # Test 12: python -m json.tool (module - non-interactive)
    print("\nTest 12: echo '{}' | python -m json.tool")
    result = run_tool.execute("echo '{}' | python -m json.tool")
    assert 'interactive' not in result.lower(), \
        "python -m should be allowed (module execution)"
    print("✓ Correctly allowed: python -m")
    
    # Test 13: python -i script.py (explicit interactive flag)
    print("\nTest 13: python -i test.py")
    result = run_tool.execute('python -i test.py')
    assert 'interactive' in result.lower(), \
        "python -i should be blocked (explicit interactive)"
    print("✓ Correctly blocked: python -i")
    
    # Test 14: Empty command (should block or allow safely)
    print("\nTest 14: Empty command")
    result = run_tool.execute("")
    # Empty command is handled by shell, just ensure no crash
    assert result is not None, "Empty command should return result"
    print("✓ Handled: empty command")
    
    # Test 15: Regression - grep python should still work
    print("\nTest 15: grep -r python . (regression)")
    write_tool.execute('edge_test.txt', 'python code here')
    result = run_tool.execute('grep python edge_test.txt')
    assert 'python code here' in result and 'interactive' not in result.lower(), \
        "grep python should work (not blocked)"
    print("✓ Correctly allowed: grep python (regression check passed)")
    
    print("\n" + "=" * 60)
    print("✅ ALL EDGE CASE TESTS PASSED")
    print("=" * 60)


def main():
    try:
        test_edge_cases()
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
