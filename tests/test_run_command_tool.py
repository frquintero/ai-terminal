import os
import re
import tempfile
from typing import Optional

from tools import RunCommandTool


class StubShell:
    """Minimal ShellIntegration stub for RunCommandTool tests."""

    def __init__(self, isolation_enabled: bool, current_dir: str):
        self.isolation_enabled = isolation_enabled
        self.current_dir = current_dir
        self.commands = []
        self.last_exit_code = 0

    def run_command(self, command: str, reset_dir: Optional[str] = None, **_: Optional[str]) -> dict:
        """Record command invocations instead of executing them."""
        target_dir = reset_dir or self.current_dir
        prefix = f"cd {_shell_quote(target_dir)}"
        recorded = f"{prefix} && {command}"
        self.commands.append({"command": recorded, "reset_dir": reset_dir})
        return {"stdout": "", "stderr": "", "exit_code": 0, "cwd": target_dir}

    def get_current_dir(self) -> str:
        return self.current_dir


def _shell_quote(value: str) -> str:
    if value == "":
        return "''"
    if re.match(r'^[A-Za-z0-9@%_=+:,./-]+$', value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def test_run_command_tool_resets_dir_to_workspace_when_isolated():
    """Isolation shells should never receive host paths via cd/reset_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shell = StubShell(isolation_enabled=True, current_dir="/workspace")
        tool = RunCommandTool(shell=shell)
        tool.working_dir = tmpdir

        tool.execute("echo isolated")

        assert shell.commands, "Shell should have been invoked"
        captured = shell.commands[0]
        assert captured["reset_dir"] == "/workspace"
        assert "cd /workspace" in captured["command"]


def test_run_command_tool_uses_host_working_dir_when_not_isolated():
    """Non-isolated shells should use the sandbox working_dir for cd/reset."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = f"{tmpdir}/sandbox"
        os.makedirs(sandbox, exist_ok=True)

        shell = StubShell(isolation_enabled=False, current_dir=sandbox)
        tool = RunCommandTool(shell=shell)
        tool.working_dir = sandbox

        tool.execute("echo direct")

        assert shell.commands, "Shell should have been invoked"
        captured = shell.commands[0]
        assert captured["reset_dir"] == sandbox
        expected_prefix = f"cd {_shell_quote(sandbox)}"
        assert expected_prefix in captured["command"]
