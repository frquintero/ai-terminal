import unittest
import tempfile
import os
import shutil
from unittest.mock import patch
from pathlib import Path

# Mock ShellIntegration to avoid shell initialization during import
with patch('shell_integration.ShellIntegration'):
    from tools import RunPythonSandboxTool

class TestPythonSandbox(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        self.sandbox_tool = RunPythonSandboxTool()
        self.test_dir = tempfile.mkdtemp()
        os.environ['SANDBOX_PATH'] = self.test_dir
        os.environ['SANDBOX_TIMEOUT'] = '5'
        os.environ['SANDBOX_DISABLE_NETWORK'] = '0'  # Allow network for tests
        
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

if __name__ == '__main__':
    unittest.main()
