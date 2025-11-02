"""Direct test of shell integration"""
from shell_integration import ShellIntegration

shell = ShellIntegration()

print("=== Test 1: ls ===")
result = shell.run_command("ls")
print(f"Result: {repr(result)}")
print(f"Length: {len(result)}")

print("\n=== Test 2: pwd ===")
result = shell.run_command("pwd")
print(f"Result: {repr(result)}")

print("\n=== Test 3: echo hello ===")
result = shell.run_command("echo 'Hello World'")
print(f"Result: {repr(result)}")

print("\n=== Test 4: date ===")
result = shell.run_command("date")
print(f"Result: {repr(result)}")

shell.close()
