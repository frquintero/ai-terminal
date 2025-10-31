import pexpect
import os
import time
import atexit

class ShellIntegration:
    # Use unique prompt sentinel to avoid false matches in command output
    PROMPT = "__AI_PROMPT__$ "
    
    def __init__(self):
        self.shell = None
        self._init_shell()
        # Ensure shell is closed on process exit
        atexit.register(self.close)

    def _init_shell(self):
        # Detect shell
        shell = os.environ.get('SHELL', '/bin/bash')
        if 'zsh' in shell:
            self.shell_type = 'zsh'
        else:
            self.shell_type = 'bash'

        # Start shell
        self.shell = pexpect.spawn(shell, encoding='utf-8')

        # Set unique prompt sentinel to avoid false matches in command output
        self.shell.sendline(f'export PS1="{self.PROMPT}"')
        self.shell.expect_exact(self.PROMPT)  # Wait for our exact prompt

    def run_command(self, command: str, timeout: int = 30) -> str:
        try:
            self.shell.sendline(command)
            index = self.shell.expect_exact([self.PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=timeout)
            
            if index == 0:  # Got prompt - command completed
                raw_output = self.shell.before or ""
                
                # Strip echoed command from output
                if raw_output.startswith(command):
                    raw_output = raw_output[len(command):]
                
                # Clean up leading whitespace
                output = raw_output.lstrip("\r\n").strip()
                return output if output else "Command executed successfully."
                
            elif index == 1:  # Timeout
                # Reset shell to recover from corrupted state
                self.close()
                self._init_shell()
                return f"Command timed out after {timeout} seconds (shell reset)."
                
            else:  # EOF - shell died
                # Reinitialize shell
                self.close()
                self._init_shell()
                return "Shell session ended unexpectedly (reset)."
                
        except Exception as e:
            # Try to recover from unexpected errors
            try:
                self.close()
                self._init_shell()
            except:
                pass
            return f"Error executing command: {str(e)}"

    def run_sudo_command(self, command: str, password: str = None, timeout: int = 30) -> str:
        sudo_cmd = f"sudo {command}"
        try:
            self.shell.sendline(sudo_cmd)
            index = self.shell.expect(['password', self.PROMPT, pexpect.TIMEOUT], timeout=10)
            if index == 0:  # Password prompt
                if password:
                    self.shell.sendline(password)
                    self.shell.expect_exact(self.PROMPT, timeout=timeout)
                    output = self.shell.before.strip()
                    return output
                else:
                    # Send Ctrl+C to cancel
                    self.shell.sendcontrol('c')
                    self.shell.expect_exact(self.PROMPT, timeout=5)
                    return "Sudo password required but not provided."
            elif index == 1:
                output = self.shell.before.strip()
                return output
            else:
                self.close()
                self._init_shell()
                return f"Sudo command timed out (shell reset)."
        except Exception as e:
            try:
                self.close()
                self._init_shell()
            except:
                pass
            return f"Error executing sudo command: {str(e)}"

    def close(self):
        if self.shell:
            self.shell.close()
