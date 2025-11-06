#!/usr/bin/env python3
"""Test static prompt system: verify shell-first philosophy is in place"""

from agent import MiniAgent

def test_static_prompt():
    """Test that static system prompt contains shell-first philosophy"""
    
    print("=" * 80)
    print("STATIC PROMPT TEST")
    print("=" * 80)
    
    # Create agent
    agent = MiniAgent()
    
    # Extract system message from history
    system_message = agent.message_history[0]
    system_prompt = system_message["content"]
    
    print("\n📋 SYSTEM PROMPT (used for all queries):")
    print("=" * 80)
    print(system_prompt)
    print("=" * 80)
    
    # Verify shell-first philosophy is present
    checks = {
        "Shell-First Philosophy": "Shell-First Philosophy" in system_prompt,
        "DEFAULT to run_command": "DEFAULT to run_command" in system_prompt,
        "run_python_sandbox ONLY when": "run_python_sandbox ONLY when" in system_prompt,
        "Tool list included": "Available agent tools:" in system_prompt,
        "System context included": "System:" in system_prompt,
    }
    
    print(f"\n✅ VERIFICATION CHECKS:")
    all_passed = True
    for check_name, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check_name}")
        if not passed:
            all_passed = False
    
    print(f"\n📊 STATS:")
    print(f"  - Prompt length: {len(system_prompt)} characters")
    print(f"  - Lines: {len(system_prompt.splitlines())}")
    print(f"  - Message history size: {len(agent.message_history)} (should be 1 - system only)")
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✓ ALL CHECKS PASSED - Static prompt configured correctly")
    else:
        print("✗ SOME CHECKS FAILED - Review prompt configuration")
    print("=" * 80)

if __name__ == "__main__":
    test_static_prompt()
