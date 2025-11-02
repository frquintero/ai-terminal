"""Comprehensive test suite for production shell integration"""
from shell_integration import ShellIntegration
import sys

def test_basic_commands():
    """Test basic command execution"""
    print("=" * 80)
    print("TEST: Basic Commands")
    print("=" * 80)
    
    shell = ShellIntegration()
    
    tests = [
        ("ls", "should list files"),
        ("pwd", "should show current directory"),
        ("echo 'Hello World'", "should echo text"),
        ("date", "should show date"),
        ("uname -a", "should show system info"),
    ]
    
    for cmd, description in tests:
        result = shell.run_command(cmd)
        print(f"\n✓ {cmd}: {description}")
        print(f"  Output: {result[:100]}...")
        assert result and result != "Command executed successfully.", f"Empty output for: {cmd}"
    
    shell.close()
    print("\n✓ All basic command tests passed!\n")

def test_directory_tracking():
    """Test that cd tracking works"""
    print("=" * 80)
    print("TEST: Directory Tracking")
    print("=" * 80)
    
    shell = ShellIntegration()
    
    # Get initial directory
    initial_dir = shell.get_current_dir()
    print(f"\nInitial dir: {initial_dir}")
    
    # Change to /tmp
    result = shell.run_command("cd /tmp && pwd")
    current = shell.get_current_dir()
    print(f"After cd /tmp: {current}")
    assert current == "/tmp", f"Expected /tmp, got {current}"
    
    # Change back
    shell.run_command(f"cd {initial_dir}")
    current = shell.get_current_dir()
    print(f"After cd back: {current}")
    assert current == initial_dir, f"Expected {initial_dir}, got {current}"
    
    shell.close()
    print("\n✓ Directory tracking test passed!\n")

def test_multiline_output():
    """Test commands with multiline output"""
    print("=" * 80)
    print("TEST: Multiline Output")
    print("=" * 80)
    
    shell = ShellIntegration()
    
    # Create multiline output
    result = shell.run_command("echo -e 'line1\\nline2\\nline3'")
    lines = result.split('\n')
    print(f"\nMultiline output has {len(lines)} lines")
    assert len(lines) >= 3, f"Expected 3+ lines, got {len(lines)}"
    
    shell.close()
    print("\n✓ Multiline output test passed!\n")

def test_special_characters():
    """Test handling of special characters"""
    print("=" * 80)
    print("TEST: Special Characters")
    print("=" * 80)
    
    shell = ShellIntegration()
    
    tests = [
        ("echo 'Hello $USER'", "variables in quotes"),
        ("echo test | grep test", "pipes"),
        ("echo 'a' && echo 'b'", "command chaining"),
    ]
    
    for cmd, description in tests:
        result = shell.run_command(cmd)
        print(f"\n✓ {cmd}: {description}")
        print(f"  Output: {result[:100]}")
        assert result, f"Empty output for: {cmd}"
    
    shell.close()
    print("\n✓ Special characters test passed!\n")

def test_error_handling():
    """Test error handling for failed commands"""
    print("=" * 80)
    print("TEST: Error Handling")
    print("=" * 80)
    
    shell = ShellIntegration()
    
    # Command that doesn't exist
    result = shell.run_command("nonexistentcommand12345")
    print(f"\nNonexistent command result: {result[:100]}")
    assert "Exit code" in result or "not found" in result.lower(), "Should indicate error"
    
    # Command with bad syntax
    result = shell.run_command("ls --invalid-flag-xyz")
    print(f"Bad flag result: {result[:100]}")
    
    shell.close()
    print("\n✓ Error handling test passed!\n")

def run_all_tests():
    """Run all test suites"""
    print("\n" + "=" * 80)
    print(" " * 20 + "SHELL INTEGRATION TEST SUITE")
    print("=" * 80 + "\n")
    
    try:
        test_basic_commands()
        test_directory_tracking()
        test_multiline_output()
        test_special_characters()
        test_error_handling()
        
        print("=" * 80)
        print(" " * 25 + "ALL TESTS PASSED!")
        print("=" * 80)
        return 0
    
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
