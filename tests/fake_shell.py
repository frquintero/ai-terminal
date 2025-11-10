import os
import subprocess
import sys
from datetime import datetime, timezone


class FakeShellIntegration:
    """
    Lightweight stand-in for ShellIntegration that runs commands via subprocess.
    Used in tests to avoid exhausting PTY devices while keeping behavior realistic.
    """

    def __init__(self, working_dir: str | None = None):
        self.current_dir = working_dir or os.getcwd()
        self.isolation_requested = False
        self.isolation_enabled = False
        self.isolation_warning = None
        self.rootfs_sha256 = None
        self.rootfs_path = None
        self.last_exit_code = None

    def run_command(self, command: str, timeout: int = 60, reset_dir: str | None = None) -> str:
        """
        Execute the provided shell command using the system bash binary.
        Mirrors ShellIntegration.run_command by resetting cwd and recording exit codes.
        """
        cwd = reset_dir or self.current_dir
        try:
            completed = subprocess.run(
                ["bash", "-lc", command],
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=timeout,
                env=os.environ,
            )
        except subprocess.TimeoutExpired:
            self._record_exit_code(124)
            if reset_dir:
                self.current_dir = reset_dir
            return "Command timed out."

        output = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if stderr:
            output = f"{output}\n{stderr}".strip()
        if completed.returncode != 0:
            if output:
                output = f"{output}\n[Exit code: {completed.returncode}]"
            else:
                output = f"Command failed with exit code {completed.returncode}"

        self._record_exit_code(completed.returncode)
        if reset_dir:
            self.current_dir = reset_dir
        return output or "Command executed successfully."

    def get_current_dir(self) -> str:
        return self.current_dir

    def close(self):
        """Placeholder for interface compatibility."""
        return None

    def _record_exit_code(self, code: int) -> None:
        self.last_exit_code = code
        module = sys.modules.get("tools")
        session_state = getattr(module, "_SESSION_STATE", None) if module else None
        if session_state:
            session_state.set_last_exit_code(code)
