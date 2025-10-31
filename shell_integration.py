import pexpect
import os
import time

class ShellIntegration:
    def __init__(self):
        self.shell = None
        self._init_shell()

    def _init_shell(self):
        # Detect shell
        shell = os.environ.get('SHELL', '/bin/bash')
        if 'zsh' in shell:
            self.shell_type = 'zsh'
        else:
            self.shell_type = 'bash'

        # Start shell
        self.shell = pexpect.spawn(shell, encoding='utf-8')

        # Set a simple prompt to make detection reliable
        self.shell.sendline('export PS1="\\$ "')
        self.shell.expect(r'\$ ')  # Wait for our custom prompt

    def run_command(self, command: str, timeout: int = 30) -> str:
        try:
            self.shell.sendline(command)
            index = self.shell.expect([r'\$ ', pexpect.TIMEOUT, pexpect.EOF], timeout=timeout)
            if index == 0:
                output = self.shell.before.strip()
                return output if output else "Command executed successfully."
            elif index == 1:
                return f"Command timed out after {timeout} seconds."
            else:
                return "Shell session ended unexpectedly."
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def run_sudo_command(self, command: str, password: str = None, timeout: int = 30) -> str:
        sudo_cmd = f"sudo {command}"
        try:
            self.shell.sendline(sudo_cmd)
            index = self.shell.expect(['password', r'\$ ', pexpect.TIMEOUT], timeout=10)
            if index == 0:  # Password prompt
                if password:
                    self.shell.sendline(password)
                    self.shell.expect(r'\$ ', timeout=timeout)
                    output = self.shell.before.strip()
                    return output
                else:
                    return "Sudo password required but not provided."
            elif index == 1:
                output = self.shell.before.strip()
                return output
            else:
                return f"Sudo command timed out."
        except Exception as e:
            return f"Error executing sudo command: {str(e)}"

    def close(self):
        if self.shell:
            self.shell.close()
