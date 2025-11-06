#!/usr/bin/env python3
"""
Test for node and ruby P0 fixes.

Verifies:
- node script.js is allowed (was incorrectly blocked)
- bare node is blocked (REPL)
- ruby script.rb is allowed
- bare ruby is blocked (REPL)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command_parser import parse_command


def test_node_ruby_fixes():
    """Test node and ruby interactive detection"""
    print("=" * 60)
    print("TEST: Node and Ruby P0 Fixes")
    print("=" * 60)
    
    # Test 1: node script.js (should be allowed)
    print("\nTest 1: node script.js")
    is_interactive, reason = parse_command('node script.js')
    assert not is_interactive, f"node script.js should be allowed, got: {reason}"
    print(f"✓ Correctly allowed: {reason}")
    
    # Test 2: bare node (should be blocked - REPL)
    print("\nTest 2: bare node")
    is_interactive, reason = parse_command('node')
    assert is_interactive, f"bare node should be blocked, got: {reason}"
    print(f"✓ Correctly blocked: {reason}")
    
    # Test 3: node -e 'console.log("hi")' (should be allowed)
    print("\nTest 3: node -e 'console.log(\"hi\")'")
    is_interactive, reason = parse_command('node -e \'console.log("hi")\'')
    assert not is_interactive, f"node -e should be allowed, got: {reason}"
    print(f"✓ Correctly allowed: {reason}")
    
    # Test 4: node --eval 'console.log("hi")' (should be allowed)
    print("\nTest 4: node --eval 'console.log(\"hi\")'")
    is_interactive, reason = parse_command('node --eval \'console.log("hi")\'')
    assert not is_interactive, f"node --eval should be allowed, got: {reason}"
    print(f"✓ Correctly allowed: {reason}")
    
    # Test 5: node -p '1+1' (should be allowed)
    print("\nTest 5: node -p '1+1'")
    is_interactive, reason = parse_command('node -p \'1+1\'')
    assert not is_interactive, f"node -p should be allowed, got: {reason}"
    print(f"✓ Correctly allowed: {reason}")
    
    # Test 6: ruby script.rb (should be allowed)
    print("\nTest 6: ruby script.rb")
    is_interactive, reason = parse_command('ruby script.rb')
    assert not is_interactive, f"ruby script.rb should be allowed, got: {reason}"
    print(f"✓ Correctly allowed: {reason}")
    
    # Test 7: bare ruby (should be blocked - REPL)
    print("\nTest 7: bare ruby")
    is_interactive, reason = parse_command('ruby')
    assert is_interactive, f"bare ruby should be blocked, got: {reason}"
    print(f"✓ Correctly blocked: {reason}")
    
    # Test 8: ruby -e 'puts "hi"' (should be allowed)
    print("\nTest 8: ruby -e 'puts \"hi\"'")
    is_interactive, reason = parse_command('ruby -e \'puts "hi"\'')
    assert not is_interactive, f"ruby -e should be allowed, got: {reason}"
    print(f"✓ Correctly allowed: {reason}")
    
    # Test 9: irb (should be blocked - always interactive)
    print("\nTest 9: irb")
    is_interactive, reason = parse_command('irb')
    assert is_interactive, f"irb should be blocked, got: {reason}"
    print(f"✓ Correctly blocked: {reason}")
    
    # Test 10: nodejs app.js (nodejs alias)
    print("\nTest 10: nodejs app.js")
    is_interactive, reason = parse_command('nodejs app.js')
    assert not is_interactive, f"nodejs app.js should be allowed, got: {reason}"
    print(f"✓ Correctly allowed: {reason}")
    
    print("\n" + "=" * 60)
    print("✅ ALL NODE/RUBY TESTS PASSED")
    print("=" * 60)


def main():
    try:
        test_node_ruby_fixes()
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
