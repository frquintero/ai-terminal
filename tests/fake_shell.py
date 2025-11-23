import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional


class FakeShellIntegration:
    """
    Lightweight stand-in for ShellIntegration that runs commands via subprocess.
    Used in tests to avoid exhausting PTY devices while keeping behavior realistic.
    """

    def __init__(self, working_dir: Optional[str] = None):
        self.current_dir = working_dir or os.getcwd()
        self.isolation_requested = False
        self.isolation_enabled = False
        self.isolation_warning = None
        self.rootfs_sha256 = None
        self.rootfs_path = None
        self.last_exit_code = None
        self.last_command_raw_output = ""
        self.last_command_normalized_output = ""
        self.last_command_output_empty = False

    def run_command(self, command: str, timeout: int = 60, reset_dir: Optional[str] = None) -> str:
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
            self.last_command_raw_output = ""
            self.last_command_normalized_output = ""
            self.last_command_output_empty = True
            return "Command timed out."

        stdout_text = (completed.stdout or "").strip()
        stderr_text = (completed.stderr or "").strip()
        merged_output = "\n".join(
            part for part in (stdout_text, stderr_text) if part
        ).strip()
        self.last_command_raw_output = merged_output
        self.last_command_normalized_output = merged_output
        self.last_command_output_empty = merged_output == ""
        if completed.returncode != 0 and merged_output:
            output = f"{merged_output}\n[Exit code: {completed.returncode}]"
        elif completed.returncode != 0:
            output = f"Command failed with exit code {completed.returncode}"
        else:
            output = merged_output

        self._record_exit_code(completed.returncode)
        if reset_dir:
            self.current_dir = reset_dir
        return output

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
