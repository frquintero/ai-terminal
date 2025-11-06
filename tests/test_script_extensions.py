#!/usr/bin/env python3
"""
Test for script extension detection (P1 fix for ai-terminal-8xh, P2 fix for ai-terminal-aby).

Verifies:
- Node.js: .js, .mjs, .cjs, .jsx, .ts, .tsx, extensionless
- Ruby: .rb, extensionless
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command_parser import parse_command


def test_node_extensions():
    """Test Node.js script extension detection"""
    print("=" * 60)
    print("TEST: Node.js Script Extension Detection")
    print("=" * 60)
    
    # Test standard .js
    print("\nTest 1: node app.js")
    is_interactive, reason = parse_command('node app.js')
    assert not is_interactive, f"node app.js should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test ES modules .mjs
    print("\nTest 2: node server.mjs")
    is_interactive, reason = parse_command('node server.mjs')
    assert not is_interactive, f"node server.mjs should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test CommonJS .cjs
    print("\nTest 3: node config.cjs")
    is_interactive, reason = parse_command('node config.cjs')
    assert not is_interactive, f"node config.cjs should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test React .jsx
    print("\nTest 4: node component.jsx")
    is_interactive, reason = parse_command('node component.jsx')
    assert not is_interactive, f"node component.jsx should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test TypeScript .ts
    print("\nTest 5: node script.ts")
    is_interactive, reason = parse_command('node script.ts')
    assert not is_interactive, f"node script.ts should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test TypeScript React .tsx
    print("\nTest 6: node app.tsx")
    is_interactive, reason = parse_command('node app.tsx')
    assert not is_interactive, f"node app.tsx should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test extensionless
    print("\nTest 7: node build (extensionless)")
    is_interactive, reason = parse_command('node build')
    assert not is_interactive, f"node build should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test extensionless with path
    print("\nTest 8: node ./scripts/deploy (extensionless with path)")
    is_interactive, reason = parse_command('node ./scripts/deploy')
    assert not is_interactive, f"node ./scripts/deploy should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test bare node (should still block)
    print("\nTest 9: bare node (should block)")
    is_interactive, reason = parse_command('node')
    assert is_interactive, f"bare node should be blocked, got: {reason}"
    print(f"✓ Blocked: {reason}")
    
    # Test with flags before script
    print("\nTest 10: node --trace-warnings app.mjs")
    is_interactive, reason = parse_command('node --trace-warnings app.mjs')
    assert not is_interactive, f"node --trace-warnings app.mjs should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    print("\n" + "=" * 60)
    print("✅ ALL NODE.JS EXTENSION TESTS PASSED")
    print("=" * 60)


def test_ruby_extensions():
    """Test Ruby script extension detection"""
    print("\n" + "=" * 60)
    print("TEST: Ruby Script Extension Detection")
    print("=" * 60)
    
    # Test standard .rb
    print("\nTest 1: ruby script.rb")
    is_interactive, reason = parse_command('ruby script.rb')
    assert not is_interactive, f"ruby script.rb should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test extensionless
    print("\nTest 2: ruby deploy (extensionless)")
    is_interactive, reason = parse_command('ruby deploy')
    assert not is_interactive, f"ruby deploy should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test extensionless with path
    print("\nTest 3: ruby ./scripts/migrate (extensionless with path)")
    is_interactive, reason = parse_command('ruby ./scripts/migrate')
    assert not is_interactive, f"ruby ./scripts/migrate should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test bare ruby (should still block)
    print("\nTest 4: bare ruby (should block)")
    is_interactive, reason = parse_command('ruby')
    assert is_interactive, f"bare ruby should be blocked, got: {reason}"
    print(f"✓ Blocked: {reason}")
    
    # Test with flags before script
    print("\nTest 5: ruby -w script.rb")
    is_interactive, reason = parse_command('ruby -w script.rb')
    assert not is_interactive, f"ruby -w script.rb should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Test irb (should always block)
    print("\nTest 6: irb (should always block)")
    is_interactive, reason = parse_command('irb')
    assert is_interactive, f"irb should be blocked, got: {reason}"
    print(f"✓ Blocked: {reason}")
    
    print("\n" + "=" * 60)
    print("✅ ALL RUBY EXTENSION TESTS PASSED")
    print("=" * 60)


def test_edge_cases():
    """Test edge cases for extension detection"""
    print("\n" + "=" * 60)
    print("TEST: Extension Detection Edge Cases")
    print("=" * 60)
    
    # File with multiple dots should be treated as having extension
    print("\nTest 1: node app.config.js")
    is_interactive, reason = parse_command('node app.config.js')
    assert not is_interactive, f"node app.config.js should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Hidden file with extension
    print("\nTest 2: node .build.js")
    is_interactive, reason = parse_command('node .build.js')
    assert not is_interactive, f"node .build.js should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Hidden file without extension should be treated as extensionless
    print("\nTest 3: node .bashrc (hidden extensionless)")
    is_interactive, reason = parse_command('node .bashrc')
    assert not is_interactive, f"node .bashrc should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Wrapper + script
    print("\nTest 4: timeout 10 node server.mjs")
    is_interactive, reason = parse_command('timeout 10 node server.mjs')
    assert not is_interactive, f"timeout 10 node server.mjs should be allowed, got: {reason}"
    print(f"✓ Allowed: {reason}")
    
    # Wrapper + bare node (should block)
    print("\nTest 5: timeout 10 node (should block)")
    is_interactive, reason = parse_command('timeout 10 node')
    assert is_interactive, f"timeout 10 node should be blocked, got: {reason}"
    print(f"✓ Blocked: {reason}")
    
    print("\n" + "=" * 60)
    print("✅ ALL EDGE CASE TESTS PASSED")
    print("=" * 60)


def main():
    try:
        test_node_extensions()
        test_ruby_extensions()
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
