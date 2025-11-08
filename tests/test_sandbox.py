import unittest
import tempfile
import os
import shutil
import uuid
from unittest.mock import patch
from pathlib import Path

# Mock ShellIntegration to avoid shell initialization during import
with patch('shell_integration.ShellIntegration'):
    from tools import RunPythonSandboxTool, _get_working_dir_path

class TestPythonSandbox(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        self.sandbox_tool = RunPythonSandboxTool()
        self.test_dir = tempfile.mkdtemp()
        os.environ['SANDBOX_PATH'] = self.test_dir
        os.environ['SANDBOX_TIMEOUT'] = '5'
        os.environ['SANDBOX_DISABLE_NETWORK'] = '0'  # Allow network for tests
        os.environ['SANDBOX_ALLOW_PROJECT_WRITES'] = '1'
        
    def tearDown(self):
        """Clean up test environment"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_basic_execution(self):
        """Test basic Python code execution"""
        code = """
print("Hello from sandbox")
x = [1, 2, 3, 4, 5]
print(f"Sum: {sum(x)}")
"""
        result = self.sandbox_tool.execute(code=code)
        
        self.assertIn("exit code: 0", result.lower())
        self.assertIn("Hello from sandbox", result)
        self.assertIn("Sum: 15", result)
    
    def test_timeout_enforcement(self):
        """Test that long-running code is terminated"""
        code = """
import time
print("Starting...")
time.sleep(10)
print("This should not print")
"""
        result = self.sandbox_tool.execute(code=code, timeout=2)
        
        self.assertIn("timed_out=True", result)
        self.assertIn("exit code: none", result.lower())
    
    def test_file_path_execution(self):
        """Test executing Python from a file"""
        # Create a test script
        script_path = os.path.join(self.test_dir, "test_script.py")
        with open(script_path, 'w') as f:
            f.write("print('Executed from file')\nprint(2 + 2)")
        
        result = self.sandbox_tool.execute(file_path=script_path)
        
        self.assertIn("exit code: 0", result.lower())
        self.assertIn("Executed from file", result)
        self.assertIn("4", result)
    
    def test_invalid_code(self):
        """Test handling of syntax errors"""
        code = """
print("Invalid syntax"
# Missing closing parenthesis
"""
        result = self.sandbox_tool.execute(code=code)
        
        self.assertIn("SyntaxError", result)
    
    def test_runtime_error(self):
        """Test handling of runtime errors"""
        code = """
x = 1 / 0  # Division by zero
"""
        result = self.sandbox_tool.execute(code=code)
        
        self.assertIn("ZeroDivisionError", result)
    
    def test_missing_parameters(self):
        """Test error when neither code nor file_path provided"""
        result = self.sandbox_tool.execute()
        
        self.assertIn("Error:", result)
        self.assertIn("'code' or 'file_path'", result)
    
    def test_nonexistent_file(self):
        """Test error when file_path doesn't exist"""
        result = self.sandbox_tool.execute(file_path="/nonexistent/file.py")
        
        self.assertIn("Error:", result)
        self.assertIn("not found", result)
    
    def test_artifacts_directory_creation(self):
        """Test that artifacts directory is created"""
        code = "print('Test')"
        result = self.sandbox_tool.execute(code=code)
        
        # Extract run_id from result
        import re
        match = re.search(r'run_id=([a-f0-9-]+)', result)
        self.assertIsNotNone(match)
        
        run_id = match.group(1)
        artifacts_dir = Path(self.test_dir) / "runs" / run_id / "artifacts"
        self.assertTrue(artifacts_dir.exists())
    
    def test_manifest_creation(self):
        """Test that manifest.json is created"""
        code = "print('Test')"
        result = self.sandbox_tool.execute(code=code)
        
        # Extract run_id from result
        import re
        match = re.search(r'run_id=([a-f0-9-]+)', result)
        self.assertIsNotNone(match)
        
        run_id = match.group(1)
        manifest_path = Path(self.test_dir) / "runs" / run_id / "manifest.json"
        self.assertTrue(manifest_path.exists())
        
        # Verify manifest content
        import json
        with open(manifest_path) as f:
            manifest = json.load(f)
        
        self.assertEqual(manifest['run_id'], run_id)
        self.assertIn('exit_code', manifest)
        self.assertIn('timed_out', manifest)
        self.assertIn('artifacts', manifest)
    
    def test_network_isolation_option(self):
        """Test network isolation toggle"""
        # Test with network disabled
        os.environ['SANDBOX_DISABLE_NETWORK'] = '1'
        code = """
try:
    import socket
    s = socket.socket()
    print("Network not blocked")
except RuntimeError as e:
    print(f"Network blocked: {e}")
"""
        result = self.sandbox_tool.execute(code=code)
        self.assertIn("Network blocked", result)
    
    def test_output_capture(self):
        """Test that stdout and stderr are captured"""
        code = """
import sys
print("stdout message")
print("stderr message", file=sys.stderr)
"""
        result = self.sandbox_tool.execute(code=code)
        
        self.assertIn("Stdout:", result)
        self.assertIn("stdout message", result)
        self.assertIn("Stderr:", result)
        self.assertIn("stderr message", result)
    
    def test_graceful_matplotlib_handling(self):
        """Test that code works without matplotlib installed"""
        code = """
# Code that doesn't use matplotlib
import math
print(f"Pi: {math.pi}")
"""
        result = self.sandbox_tool.execute(code=code)
        
        # Should succeed even if matplotlib not available
        self.assertIn("exit code: 0", result.lower())
        self.assertIn("Pi: 3.14", result)
    
    def test_project_file_read(self):
        """Test reading project files via SANDBOX_PROJECT"""
        # Create a test file in the project directory (test_dir acts as project)
        test_file = os.path.join(self.test_dir, "test_data.txt")
        with open(test_file, 'w') as f:
            f.write("Hello from project directory")
        
        # Change to test_dir to simulate being in the project
        original_cwd = os.getcwd()
        try:
            os.chdir(self.test_dir)
            
            code = """
import os

project_dir = os.environ.get('SANDBOX_PROJECT')
if not project_dir:
    print("ERROR: SANDBOX_PROJECT not set")
else:
    test_file = os.path.join(project_dir, 'test_data.txt')
    with open(test_file, 'r') as f:
        content = f.read()
    print(f"Read from project: {content}")
"""
            result = self.sandbox_tool.execute(code=code)
            
            self.assertIn("exit code: 0", result.lower())
            self.assertIn("Read from project: Hello from project directory", result)
        finally:
            os.chdir(original_cwd)
    
    def test_relative_read_fallback(self):
        """Ensure sandbox can read project files via relative paths"""
        data_file = os.path.join(self.test_dir, "number_roots.csv")
        with open(data_file, 'w') as f:
            f.write("42\n")
        
        original_cwd = os.getcwd()
        try:
            os.chdir(self.test_dir)
            os.environ['SANDBOX_ALLOW_PROJECT_WRITES'] = '0'
            
            code = """
with open('number_roots.csv', 'r') as f:
    print('Loaded:', f.read().strip())
"""
            result = self.sandbox_tool.execute(code=code)
            self.assertIn("Loaded: 42", result)
        finally:
            os.chdir(original_cwd)
    
    def test_workdir_relative_read_support(self):
        """Ensure files in the agent working directory are readable via relative paths"""
        workdir = Path(_get_working_dir_path())
        if not workdir.exists():
            self.skipTest("working directory missing")
        
        file_name = f"sandbox_workdir_{uuid.uuid4().hex}.txt"
        target = workdir / file_name
        target.write_text("workdir content", encoding="utf-8")
        
        # Default behavior blocks writes; ensure reads can still locate files
        previous = os.environ.get('SANDBOX_ALLOW_PROJECT_WRITES')
        os.environ['SANDBOX_ALLOW_PROJECT_WRITES'] = '0'
        
        code = f"""
with open('{file_name}', 'r') as f:
    print('Workdir content:', f.read().strip())
"""
        try:
            result = self.sandbox_tool.execute(code=code)
            self.assertIn("Workdir content: workdir content", result)
        finally:
            if target.exists():
                target.unlink()
            if previous is None:
                os.environ.pop('SANDBOX_ALLOW_PROJECT_WRITES', None)
            else:
                os.environ['SANDBOX_ALLOW_PROJECT_WRITES'] = previous
    
    def test_run_dir_writes_are_allowed(self):
        """Sandbox should still write inside its ephemeral run directory"""
        previous = os.environ.get('SANDBOX_ALLOW_PROJECT_WRITES')
        os.environ['SANDBOX_ALLOW_PROJECT_WRITES'] = '0'
        code = """
import os
from pathlib import Path

run_dir = Path(os.environ['SANDBOX_RUN_DIR'])
target = run_dir / "artifacts" / "allowed.txt"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("sandbox ok")
print("Allowed file exists:", target.exists())
"""
        try:
            result = self.sandbox_tool.execute(code=code)
            self.assertIn("Allowed file exists: True", result)
        finally:
            if previous is None:
                os.environ.pop('SANDBOX_ALLOW_PROJECT_WRITES', None)
            else:
                os.environ['SANDBOX_ALLOW_PROJECT_WRITES'] = previous

    def test_project_write_guard(self):
        """Test that writing to project directory is blocked by default"""
        # Create a test file in the project directory
        test_file = os.path.join(self.test_dir, "protected.txt")
        with open(test_file, 'w') as f:
            f.write("Original content")
        
        # Change to test_dir to simulate being in the project
        original_cwd = os.getcwd()
        try:
            os.chdir(self.test_dir)
            
            # Ensure write protection is enabled
            os.environ['SANDBOX_ALLOW_PROJECT_WRITES'] = '0'
            
            code = """
import os

project_dir = os.environ.get('SANDBOX_PROJECT')
if project_dir:
    test_file = os.path.join(project_dir, 'protected.txt')
    try:
        with open(test_file, 'w') as f:
            f.write("Modified content")
        print("ERROR: Write should have been blocked")
    except PermissionError as e:
        print(f"Write blocked as expected: {e}")
"""
            result = self.sandbox_tool.execute(code=code)
            
            self.assertIn("exit code: 0", result.lower())
            self.assertIn("Write blocked as expected", result)
            
            # Verify file was not modified
            with open(test_file, 'r') as f:
                content = f.read()
            self.assertEqual(content, "Original content")
        finally:
            os.chdir(original_cwd)
    
    def test_project_os_remove_guard(self):
        """Ensure os.remove can't delete project files when writes disabled"""
        test_file = os.path.join(self.test_dir, "remove_guard.txt")
        with open(test_file, 'w') as f:
            f.write("Protected data")
        
        original_cwd = os.getcwd()
        try:
            os.chdir(self.test_dir)
            os.environ['SANDBOX_ALLOW_PROJECT_WRITES'] = '0'
            
            code = """
import os

project_dir = os.environ.get('SANDBOX_PROJECT')
target = os.path.join(project_dir, 'remove_guard.txt')
try:
    os.remove(target)
    print("remove succeeded unexpectedly")
except PermissionError as exc:
    print(f"Remove blocked: {exc}")
"""
            result = self.sandbox_tool.execute(code=code)
            self.assertIn("Remove blocked", result)
            
            with open(test_file, 'r') as f:
                self.assertEqual(f.read(), "Protected data")
        finally:
            os.chdir(original_cwd)

if __name__ == '__main__':
    unittest.main()
