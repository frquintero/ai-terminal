#!/usr/bin/env python3
"""
Test for interleaved wrapper/assignment skipping (bd ai-terminal-eiz).

The guard should handle any mixture of wrappers and assignments:
- PATH=/tmp sudo vim (assignment then wrapper)
- sudo PATH=/tmp vim (wrapper then assignment)
- env VAR=1 sudo python (wrapper, assignment, wrapper)
"""

import sys
from tools import TOOLS

def test_interleaved_skipping():
    """Test that wrappers and assignments are interleaved correctly"""
    print("=" * 60)
    print("TEST: Interleaved Wrapper/Assignment Skipping")
    print("=" * 60)
    
    run_tool = TOOLS['run_command']
    
    # Test 1: PATH=/tmp sudo vim (assignment -> wrapper -> interactive)
    print("\nTest 1: PATH=/tmp sudo vim")
    result = run_tool.execute('PATH=/tmp sudo vim')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "PATH=/tmp sudo vim should detect vim as interactive"
    print("✓ Correctly blocked: PATH=/tmp sudo vim")
    
    # Test 2: sudo PATH=/tmp vim (wrapper -> assignment -> interactive)
    print("\nTest 2: sudo PATH=/tmp vim")
    result = run_tool.execute('sudo PATH=/tmp vim')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "sudo PATH=/tmp vim should detect vim as interactive"
    print("✓ Correctly blocked: sudo PATH=/tmp vim")
    
    # Test 3: env VAR=1 sudo python (wrapper -> assignment -> wrapper -> interactive)
    print("\nTest 3: env VAR=1 sudo python")
    result = run_tool.execute('env VAR=1 sudo python')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "env VAR=1 sudo python should detect python as interactive"
    print("✓ Correctly blocked: env VAR=1 sudo python")
    
    # Test 4: VAR1=1 sudo VAR2=2 bash (assign -> wrapper -> assign -> interactive)
    print("\nTest 4: VAR1=1 sudo VAR2=2 bash")
    result = run_tool.execute('VAR1=1 sudo VAR2=2 bash')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "VAR1=1 sudo VAR2=2 bash should detect bash as interactive"
    print("✓ Correctly blocked: VAR1=1 sudo VAR2=2 bash")
    
    # Test 5: sudo env EDITOR=vim nano (multiple wrappers + assignment)
    print("\nTest 5: sudo env EDITOR=vim nano")
    result = run_tool.execute('sudo env EDITOR=vim nano')
    assert 'InteractiveCommandTool' in result or 'interactive' in result.lower(), \
        "sudo env EDITOR=vim nano should detect nano as interactive"
    print("✓ Correctly blocked: sudo env EDITOR=vim nano")
    
    # Test 6: PATH=/tmp sudo ls (assignment -> wrapper -> safe command)
    print("\nTest 6: PATH=/tmp sudo ls (safe command)")
    result = run_tool.execute('PATH=/tmp sudo ls')
    assert 'InteractiveCommandTool' not in result, \
        "PATH=/tmp sudo ls should allow ls (not interactive)"
    print("✓ Correctly allowed: PATH=/tmp sudo ls")
    
    # Test 7: Regression - grep python should still work
    print("\nTest 7: grep python file.txt (regression)")
    write_tool = TOOLS['write_file']
    write_tool.execute('interleave_test.txt', 'python\njava\npython3')
    result = run_tool.execute('grep python interleave_test.txt')
    assert 'python' in result and 'InteractiveCommandTool' not in result, \
        "grep python should work (not blocked)"
    print("✓ Correctly allowed: grep python file.txt")
    
    # Test 8: env VAR=1 python --version (safe flag with complex prefix)
    print("\nTest 8: env VAR=1 python --version")
    result = run_tool.execute('env VAR=1 python --version')
    assert 'Python' in result or 'python' in result, \
        "env VAR=1 python --version should be allowed (safe flag)"
    print("✓ Correctly allowed: env VAR=1 python --version")
    
    print("\n" + "=" * 60)
    print("✅ ALL INTERLEAVED SKIPPING TESTS PASSED")
    print("=" * 60)


def main():
    try:
        test_interleaved_skipping()
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
