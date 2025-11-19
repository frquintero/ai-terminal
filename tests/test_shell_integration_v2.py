import pytest
import os
from shell_integration import ShellIntegration

class TestShellIntegrationV2:
    @pytest.fixture
    def shell(self):
        shell = ShellIntegration()
        yield shell
        shell.close()

    def test_stdout_stderr_separation(self, shell):
        # Command that writes to both stdout and stderr
        cmd = "echo 'hello stdout'; echo 'hello stderr' >&2"
        result = shell.run_command(cmd)
        
        assert isinstance(result, dict)
        assert "hello stdout" in result["stdout"]
        assert "hello stderr" in result["stderr"]
        assert result["exit_code"] == 0

    def test_stdin_input(self, shell):
        # Command that reads from stdin
        cmd = "cat"
        input_data = "hello stdin"
        result = shell.run_command(cmd, input_data=input_data)
        
        assert isinstance(result, dict)
        assert "hello stdin" in result["stdout"]
        assert result["exit_code"] == 0

    def test_exit_code_failure(self, shell):
        # Command that fails
        cmd = "ls /nonexistent_directory_xyz"
        result = shell.run_command(cmd)
        
        assert isinstance(result, dict)
        assert result["exit_code"] != 0
        assert "No such file or directory" in result["stderr"] or "cannot access" in result["stderr"]

    def test_cwd_tracking(self, shell):
        # Change directory
        cmd = "cd /tmp"
        result = shell.run_command(cmd)
        assert result["exit_code"] == 0
        assert result["cwd"] == "/tmp"
        
        # Verify persistence
        result2 = shell.run_command("pwd")
        assert result2["stdout"].strip() == "/tmp"

    def test_complex_pipeline(self, shell):
        # Pipeline with stdin
        cmd = "grep 'world'"
        input_data = "hello\nworld\nfoo"
        result = shell.run_command(cmd, input_data=input_data)
        
        assert "world" in result["stdout"]
        assert "hello" not in result["stdout"]
        assert result["exit_code"] == 0
