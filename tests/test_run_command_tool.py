import shlex

from tools import RunCommandTool


class StubShell:
    """Minimal ShellIntegration stub for RunCommandTool tests."""

    def __init__(self, isolation_enabled: bool, current_dir: str):
        self.isolation_enabled = isolation_enabled
        self.current_dir = current_dir
        self.commands = []
        self.last_exit_code = 0

    def run_command(self, command: str, reset_dir: Optional[str] = None) -> str:
        """Record command invocations instead of executing them."""
        self.commands.append({"command": command, "reset_dir": reset_dir})
        return "ok"

    def get_current_dir(self) -> str:
        return self.current_dir


def test_run_command_tool_resets_dir_to_workspace_when_isolated(tmp_path):
    """Isolation shells should never receive host paths via cd/reset_dir."""
    shell = StubShell(isolation_enabled=True, current_dir="/workspace")
    tool = RunCommandTool(shell=shell)
    tool.working_dir = str(tmp_path)

    tool.execute("echo isolated")

    assert shell.commands, "Shell should have been invoked"
    captured = shell.commands[0]
    assert captured["reset_dir"] == "/workspace"
    assert "cd /workspace" in captured["command"]


def test_run_command_tool_uses_host_working_dir_when_not_isolated(tmp_path):
    """Non-isolated shells should use the sandbox working_dir for cd/reset."""
    host_dir = tmp_path / "sandbox"
    host_dir.mkdir(parents=True, exist_ok=True)

    shell = StubShell(isolation_enabled=False, current_dir=str(host_dir))
    tool = RunCommandTool(shell=shell)
    tool.working_dir = str(host_dir)

    tool.execute("echo direct")

    assert shell.commands, "Shell should have been invoked"
    captured = shell.commands[0]
    assert captured["reset_dir"] == str(host_dir)
    expected_prefix = f"cd {shlex.quote(str(host_dir))}"
    assert expected_prefix in captured["command"]
