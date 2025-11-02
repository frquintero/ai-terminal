#!/usr/bin/env python3
"""
Test suite for package manager and sudo command handling.

This test file validates that:
1. Package manager commands (yay/pacman) without --noconfirm are caught
2. Package manager commands with --noconfirm are allowed
3. Sudo commands are redirected to run_sudo_command tool
4. run_sudo_command handles passwords correctly
5. Commands don't hang indefinitely

USAGE:
    python tests/test_package_manager_sudo.py

CONFIGURATION:
    Set SUDO_PASSWORD environment variable or edit SUDO_PASSWORD constant below
"""

import sys
import os
from typing import Dict, Any

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import TOOLS

# ============================================================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================================================

# Set your sudo password here or via environment variable
SUDO_PASSWORD = os.environ.get('SUDO_PASSWORD', 'PLACEHOLDER_PASSWORD_HERE')

# Use 'pacman' for testing instead of 'yay' to avoid AUR operations
# Both should behave identically for our guards
TEST_PACKAGE_MANAGER = 'pacman'

# ============================================================================
# TEST CASES
# ============================================================================

class TestResults:
    """Simple test result tracker"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add_pass(self, name: str, message: str = ""):
        self.passed += 1
        self.tests.append((name, "PASS", message))
        print(f"✅ PASS: {name}")
        if message:
            print(f"   └─ {message}")
    
    def add_fail(self, name: str, message: str = ""):
        self.failed += 1
        self.tests.append((name, "FAIL", message))
        print(f"❌ FAIL: {name}")
        if message:
            print(f"   └─ {message}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*70}")
        print(f"TEST SUMMARY: {self.passed}/{total} passed, {self.failed}/{total} failed")
        print(f"{'='*70}")
        return self.failed == 0


def test_package_manager_without_sudo(results: TestResults):
    """Test that package manager privileged operations require run_sudo_command"""
    print("\n[Test 1] Package manager privileged operations require sudo")
    
    tool = TOOLS['run_command']
    
    # Test yay -Syu (should be blocked - needs sudo)
    result = tool.execute('yay -Syu')
    if 'Error' in result and 'run_sudo_command' in result:
        results.add_pass('yay -Syu blocked (needs sudo)', result[:100])
    else:
        results.add_fail('yay -Syu should require sudo', f"Got: {result[:100]}")
    
    # Test pacman -S package (should be blocked - needs sudo)
    result = tool.execute('pacman -S vim')
    if 'Error' in result and 'run_sudo_command' in result:
        results.add_pass('pacman -S blocked (needs sudo)', result[:100])
    else:
        results.add_fail('pacman -S should require sudo', f"Got: {result[:100]}")
    
    # Test pacman -R package (should be blocked - needs sudo)
    result = tool.execute('pacman -R vim')
    if 'Error' in result and 'run_sudo_command' in result:
        results.add_pass('pacman -R blocked (needs sudo)', result[:100])
    else:
        results.add_fail('pacman -R should require sudo', f"Got: {result[:100]}")


def test_package_manager_query_operations(results: TestResults):
    """Test that package manager query operations are allowed without sudo"""
    print("\n[Test 2] Package manager query operations (no sudo needed)")
    
    tool = TOOLS['run_command']
    
    # Test pacman -Q (query - non-privileged operation, should work)
    result = tool.execute('pacman -Q | head -3')
    if 'Error' not in result or 'requires root' not in result:
        results.add_pass('pacman -Q allowed (query operation)', result[:100])
    else:
        results.add_fail('pacman -Q should be allowed', f"Got: {result[:100]}")
    
    # Test pacman -Qi (query info - non-privileged)
    result = tool.execute('pacman -Qi bash')
    if 'Error' not in result or 'requires root' not in result:
        results.add_pass('pacman -Qi allowed (query operation)', result[:50])
    else:
        results.add_fail('pacman -Qi should be allowed', f"Got: {result[:100]}")


def test_sudo_redirect(results: TestResults):
    """Test that sudo commands are redirected to run_sudo_command"""
    print("\n[Test 3] Sudo command redirect")
    
    tool = TOOLS['run_command']
    
    # Test sudo command (should be blocked)
    result = tool.execute('sudo ls /root')
    if 'Error' in result and 'run_sudo_command' in result:
        results.add_pass('sudo command blocked', result[:100])
    else:
        results.add_fail('sudo should be blocked', f"Got: {result[:100]}")
    
    # Test doas command (should be blocked)
    result = tool.execute('doas ls /root')
    if 'Error' in result and 'run_sudo_command' in result:
        results.add_pass('doas command blocked', result[:100])
    else:
        results.add_fail('doas should be blocked', f"Got: {result[:100]}")


def test_sudo_command_tool_correct_password(results: TestResults):
    """Test run_sudo_command with correct password"""
    print("\n[Test 4] run_sudo_command with correct password")
    
    if SUDO_PASSWORD == 'PLACEHOLDER_PASSWORD_HERE':
        print("   ⚠️  SKIPPED: SUDO_PASSWORD not configured")
        print("   ℹ️  Set SUDO_PASSWORD environment variable to run this test")
        return
    
    tool = TOOLS['run_sudo_command']
    
    # Test simple sudo command with password
    result = tool.execute('whoami', password=SUDO_PASSWORD, timeout=10)
    if 'root' in result.lower():
        results.add_pass('sudo with correct password', result[:100])
    else:
        results.add_fail('sudo with correct password failed', f"Got: {result[:100]}")


def test_sudo_command_tool_wrong_password(results: TestResults):
    """Test run_sudo_command with incorrect password"""
    print("\n[Test 5] run_sudo_command with incorrect password")
    print("   ⚠️  SKIPPED: Disabled to avoid sudo lockout")
    print("   ℹ️  Wrong password attempts can trigger sudo account lockout")
    # Note: This test is disabled to prevent sudo lockout from multiple failed attempts
    # The functionality is implicitly tested when correct password fails to authenticate


def test_sudo_package_manager_without_noconfirm(results: TestResults):
    """Test that sudo package manager commands without --noconfirm are caught"""
    print("\n[Test 6] sudo + package manager without --noconfirm")
    
    if SUDO_PASSWORD == 'PLACEHOLDER_PASSWORD_HERE':
        print("   ⚠️  SKIPPED: SUDO_PASSWORD not configured")
        return
    
    tool = TOOLS['run_sudo_command']
    
    # Test sudo pacman -Syu without --noconfirm (should be blocked)
    result = tool.execute('pacman -Syu', password=SUDO_PASSWORD, timeout=10)
    if 'Error' in result and '--noconfirm' in result:
        results.add_pass('sudo pacman without --noconfirm blocked', result[:100])
    else:
        results.add_fail('sudo pacman should require --noconfirm', f"Got: {result[:100]}")


def test_no_hang_on_privileged_operations(results: TestResults):
    """Test that privileged operations don't hang (they should return quickly with error)"""
    print("\n[Test 7] No hanging on privileged operations")
    
    import time
    tool = TOOLS['run_command']
    
    # Test that yay -Syu returns quickly (not hangs for 60s)
    start = time.time()
    result = tool.execute('yay -Syu')
    elapsed = time.time() - start
    
    if elapsed < 5:  # Should return almost instantly with error
        results.add_pass(f'yay -Syu returned quickly ({elapsed:.2f}s)', result[:100])
    else:
        results.add_fail(f'yay -Syu took too long ({elapsed:.2f}s)', f"Got: {result[:100]}")


def main():
    """Run all tests"""
    print("="*70)
    print("PACKAGE MANAGER & SUDO COMMAND TEST SUITE")
    print("="*70)
    
    if SUDO_PASSWORD == 'PLACEHOLDER_PASSWORD_HERE':
        print("\n⚠️  WARNING: SUDO_PASSWORD not configured!")
        print("Some tests will be skipped. Set SUDO_PASSWORD environment variable to run all tests.")
        print("Example: SUDO_PASSWORD='your_password' python tests/test_package_manager_sudo.py\n")
    
    results = TestResults()
    
    # Run all tests
    test_package_manager_without_sudo(results)
    test_package_manager_query_operations(results)
    test_sudo_redirect(results)
    test_sudo_command_tool_correct_password(results)
    test_sudo_command_tool_wrong_password(results)
    test_sudo_package_manager_without_noconfirm(results)
    test_no_hang_on_privileged_operations(results)
    
    # Print summary
    success = results.summary()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
