#!/usr/bin/env python3
"""
Test script for namespace isolation with complex multi-step scenarios.
Tests the RunCommandTool and ShellIntegration in isolated environment.
"""

import os
import tempfile
import json
from pathlib import Path
from shell_integration import ShellIntegration
from tools import RunCommandTool

def test_basic_isolation():
    """Test basic isolation functionality"""
    print("=== Testing Basic Isolation ===")

    # Test with isolation disabled
    print("1. Testing without isolation:")
    shell = ShellIntegration()
    print(f"   Isolation enabled: {shell.isolation_enabled}")
    result = shell.run_command("pwd")
    print(f"   PWD: {result}")
    result = shell.run_command("ls -la | head -5")
    print(f"   LS: {result}")

    # Test with isolation enabled (if configured)
    print("\n2. Testing with isolation:")
    os.environ["SANDBOX_ENABLE_ISOLATION"] = "1"
    try:
        shell_iso = ShellIntegration()
        print(f"   Isolation enabled: {shell_iso.isolation_enabled}")
        if shell_iso.isolation_enabled:
            result = shell_iso.run_command("pwd")
            print(f"   PWD: {result}")
            result = shell_iso.run_command("ls -la | head -5")
            print(f"   LS: {result}")
        else:
            print("   Isolation not available (no rootfs configured)")
    except Exception as e:
        print(f"   Error: {e}")
    finally:
        os.environ.pop("SANDBOX_ENABLE_ISOLATION", None)

def test_run_command_tool():
    """Test RunCommandTool with various commands"""
    print("\n=== Testing RunCommandTool ===")

    tool = RunCommandTool()

    # Test basic commands
    print("1. Basic commands:")
    result = tool.execute("echo 'Hello World'")
    print(f"   echo: {result}")

    result = tool.execute("pwd")
    print(f"   pwd: {result}")

    # Test file operations
    print("\n2. File operations:")
    result = tool.execute("echo 'test data' > test_file.txt")
    print(f"   create file: {result}")

    result = tool.execute("cat test_file.txt")
    print(f"   read file: {result}")

    result = tool.execute("ls -la test_file.txt")
    print(f"   ls file: {result}")

    # Test directory change (should be reset)
    print("\n3. Directory changes:")
    result = tool.execute("mkdir -p test_dir && cd test_dir && pwd")
    print(f"   cd and pwd: {result}")

    result = tool.execute("pwd")  # Should be back to working dir
    print(f"   pwd after: {result}")

    # Test interactive command blocking
    print("\n4. Interactive command blocking:")
    result = tool.execute("vim --version")  # Safe flag
    print(f"   vim --version: {result}")

    try:
        result = tool.execute("vim test_file.txt")  # Should be blocked
        print(f"   vim (blocked): {result}")
    except Exception as e:
        print(f"   vim (error): {e}")

def test_complex_pipeline():
    """Test complex command pipelines"""
    print("\n=== Testing Complex Pipelines ===")

    tool = RunCommandTool()

    # Create test data
    result = tool.execute("""
cat > test_data.csv << 'EOF'
name,age,city
Alice,25,New York
Bob,30,London
Charlie,35,Paris
EOF
""".strip())
    print(f"Create CSV: {result}")

    # Process with pipeline
    result = tool.execute("csvcut -c name,age test_data.csv | csvlook")
    print(f"Process CSV: {result}")

    # JSON processing
    result = tool.execute("""
cat > test_data.json << 'EOF'
{"users": [
  {"name": "Alice", "age": 25},
  {"name": "Bob", "age": 30}
]}
EOF
""".strip())
    print(f"Create JSON: {result}")

    result = tool.execute("jq '.users[].name' test_data.json")
    print(f"Process JSON: {result}")

def test_python_sandbox():
    """Test Python sandbox execution"""
    print("\n=== Testing Python Sandbox ===")

    from tools import run_python_sandbox

    # Simple script
    script = """
import sys
print(f"Python version: {sys.version}")
print("Hello from sandbox!")

# Test imports
try:
    import json
    print("json import: OK")
except ImportError as e:
    print(f"json import failed: {e}")

# Test data processing
data = [1, 2, 3, 4, 5]
avg = sum(data) / len(data)
print(f"Average: {avg}")
"""

    try:
        result = run_python_sandbox(script)
        print(f"Python sandbox result: {result}")
    except Exception as e:
        print(f"Python sandbox error: {e}")

def cleanup():
    """Clean up test files"""
    print("\n=== Cleanup ===")
    tool = RunCommandTool()
    result = tool.execute("rm -f test_file.txt test_data.csv test_data.json && rm -rf test_dir")
    print(f"Cleanup: {result}")

if __name__ == "__main__":
    print("Testing namespace isolation with complex multi-step scenarios")
    print("=" * 60)

    test_basic_isolation()
    test_run_command_tool()
    test_complex_pipeline()
    test_python_sandbox()
    cleanup()

    print("\n" + "=" * 60)
    print("Testing complete!")
