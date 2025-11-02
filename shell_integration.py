import pexpect
import os
import re
import atexit

class ShellIntegration:
    """
    Production-grade shell integration using pexpect with:
    - Marker-based output parsing (no brittle prompt detection)
    - Randomized session tokens (prevents prompt confusion)
    - Controlled shell environment (--noprofile --norc)
    - Robust ANSI/control sequence stripping
    - Graceful timeout recovery with Ctrl-C
    - Exit code and PWD tracking
    """
    
    def __init__(self):
        # Generate random session tokens to prevent prompt confusion attacks
        self._token = os.urandom(8).hex()
        self.PROMPT = f"__AI_{self._token}__$ "
        self._start_marker = f"__AI_START_{self._token}__"
        self._end_marker = f"__AI_END_{self._token}__"
        self._sudo_prompt = f"__AI_SUDO_{self._token}__"
        
        self.shell = None
        self.current_dir = os.path.expanduser('~')
        self._init_shell()
        
        # Ensure shell is closed on process exit
        atexit.register(self.close)
    
    def _shq(self, s: str) -> str:
        """Shell-quote a string safely for single quotes"""
        return "'" + s.replace("'", "'\"'\"'") + "'"
    
    def _init_shell(self):
        """Initialize a controlled shell with predictable behavior"""
        # Prefer bash for consistency; fallback to user's shell
        shell_path = "/bin/bash"
        args = ["--noprofile", "--norc", "-i"]
        
        if not os.path.exists(shell_path):
            shell_path = os.environ.get('SHELL', '/bin/bash')
            if 'zsh' in shell_path:
                args = ["-f", "-i"]  # -f: no rc files
        
        # Spawn with controlled environment
        self.shell = pexpect.spawn(
            shell_path,
            args=args,
            encoding='utf-8',
            codec_errors='replace',  # Handle binary output gracefully
            env=dict(os.environ, TERM='dumb')  # Reduce fancy output
        )
        
        # Disable echo to prevent command echoing in output
        self.shell.setecho(False)
        
        # Set up minimal, controlled prompt
        # Disable dynamic prompt hooks that could interfere
        self.shell.sendline(f'unset PROMPT_COMMAND 2>/dev/null; PS1={self._shq(self.PROMPT)}; stty -echo 2>/dev/null || true')
        
        try:
            self.shell.expect_exact(self.PROMPT, timeout=5)
        except pexpect.TIMEOUT:
            # Fallback: try to resync
            self._resync()
    
    def _resync(self):
        """Attempt to resynchronize with shell prompt"""
        try:
            # Send newline and wait for prompt
            self.shell.sendline('')
            self.shell.expect_exact(self.PROMPT, timeout=3)
        except (pexpect.TIMEOUT, pexpect.EOF):
            # Hard reset if resync fails
            self.close()
            self._init_shell()
    
    def _normalize_output(self, raw: str) -> str:
        """
        Normalize terminal output by:
        1. Removing carriage returns (\r)
        2. Applying backspaces (\b)
        3. Stripping all ANSI/control sequences
        4. Removing leading/trailing blank lines
        """
        if not raw:
            return ""
        
        # Step 1: Normalize CR/LF to just LF
        # Replace \r\n with \n, then remove remaining \r
        normalized = raw.replace('\r\n', '\n').replace('\r', '')
        
        # Step 2: Split into lines
        lines = normalized.split('\n')
        
        # Step 3: Apply backspaces to each line
        processed_lines = []
        for line in lines:
            buf = []
            for ch in line:
                if ch == '\x08' or ch == '\x7f':  # backspace or DEL
                    if buf:
                        buf.pop()
                else:
                    buf.append(ch)
            processed_lines.append(''.join(buf))
        
        normalized_lines = processed_lines
        
        # Step 3: Strip ANSI escape sequences (CSI, OSC, DCS, etc.)
        # Comprehensive pattern covering:
        # - CSI: ESC[ ... (most common: colors, cursor movement)
        # - OSC: ESC] ... BEL or ESC\ (operating system commands)
        # - DCS: ESCP ... ESC\ (device control strings)
        # - Single-char ESC sequences: ESC letter
        ansi_pattern = re.compile(
            r'(?:\x1B\[|\x9B)[0-?]*[ -/]*[@-~]|'  # CSI sequences
            r'(?:\x1B\][^\x07]*(?:\x07|\x1B\\))|'  # OSC sequences
            r'(?:\x1BP.*?\x1B\\)|'                  # DCS sequences
            r'(?:\x1B[\(\)][A-Za-z0-9])|'          # Charset selection
            r'(?:\x1B[@-Z\\-_])',                   # Single-char ESC sequences
            re.DOTALL
        )
        
        normalized_lines = [ansi_pattern.sub('', line) for line in normalized_lines]
        
        # Step 4: Trim only completely empty leading/trailing lines
        # Be more conservative - only remove truly empty lines
        while normalized_lines and len(normalized_lines) > 0 and normalized_lines[0] == '':
            normalized_lines.pop(0)
        while normalized_lines and len(normalized_lines) > 0 and normalized_lines[-1] == '':
            normalized_lines.pop()
        
        result = '\n'.join(normalized_lines)
        return result.strip()  # Final strip of whitespace
    
    def run_command(self, command: str, timeout: int = 60) -> str:
        """
        Execute a command with robust output parsing using start/end markers.
        
        Returns the command output as a clean string.
        Captures exit code and updates current directory automatically.
        """
        try:
            # Wrap command with markers and capture exit code + PWD
            # Format: START_MARKER\nCOMMAND_OUTPUT\nEND_MARKER<exitcode>:<pwd>
            # Use echo instead of printf for simplicity and compatibility
            wrapped = (
                f'PS1={self._shq(self.PROMPT)}; '
                f'echo {self._shq(self._start_marker)}; '
                f'{command}; '
                f'__S=$?; '
                f'echo {self._shq(self._end_marker)}$__S:$PWD'
            )
            
            self.shell.sendline(wrapped)
            
            # Step 1: Wait for start marker
            try:
                self.shell.expect_exact(self._start_marker, timeout=5)
            except pexpect.TIMEOUT:
                self._resync()
                return "Error: Failed to start command execution (shell desync)"
            
            # Step 2: Wait for end marker with exit code and PWD
            # Pattern: END_MARKER<exitcode>:<pwd> followed by newline
            end_pattern = re.compile(
                rf'{re.escape(self._end_marker)}(\d+):([^\r\n]+)',
                re.MULTILINE
            )
            
            try:
                self.shell.expect(end_pattern, timeout=timeout)
                
                # Extract command output (everything between markers)
                raw_output = self.shell.before or ""
                
                # Extract exit code and PWD from marker
                exit_code = int(self.shell.match.group(1))
                new_pwd = self.shell.match.group(2).strip()
                
                # Update tracked directory
                if new_pwd and new_pwd.startswith('/'):
                    self.current_dir = new_pwd
                
                # Step 3: Drain to prompt
                try:
                    self.shell.expect_exact(self.PROMPT, timeout=3)
                except pexpect.TIMEOUT:
                    pass  # Non-critical if we already got the output
                
                # Normalize and clean the output
                output = self._normalize_output(raw_output)
                
                # If command failed, include exit code info
                if exit_code != 0 and output:
                    output += f"\n[Exit code: {exit_code}]"
                elif exit_code != 0:
                    output = f"Command failed with exit code {exit_code}"
                
                return output if output else "Command executed successfully."
                
            except pexpect.TIMEOUT:
                # Try Ctrl-C recovery before hard reset
                return self._handle_timeout(command, timeout)
            
            except pexpect.EOF:
                # Shell died - reinitialize
                self.close()
                self._init_shell()
                return "Shell session ended unexpectedly (reinitialized)"
        
        except Exception as e:
            # Attempt recovery
            try:
                self._resync()
            except:
                self.close()
                self._init_shell()
            return f"Error executing command: {str(e)}"
    
    def _handle_timeout(self, command: str, timeout: int) -> str:
        """
        Handle command timeout with graceful recovery:
        1. Try Ctrl-C to interrupt
        2. If that fails, hard reset the shell
        """
        try:
            # Send Ctrl-C to interrupt
            self.shell.sendcontrol('c')
            
            # Try to get back to prompt
            try:
                self.shell.expect_exact(self.PROMPT, timeout=3)
                return f"Command timed out after {timeout}s and was interrupted (Ctrl-C)"
            except pexpect.TIMEOUT:
                # Ctrl-C didn't work, hard reset
                self.close()
                self._init_shell()
                return f"Command timed out after {timeout}s (shell reset)"
        
        except Exception:
            # Hard reset on any error
            self.close()
            self._init_shell()
            return f"Command timed out after {timeout}s (shell reset)"
    
    def run_sudo_command(self, command: str, password: str = None, timeout: int = 60) -> str:
        """
        Execute a sudo command with robust password handling.
        Uses sudo -S with a custom prompt to detect password requests.
        """
        try:
            # Wrap sudo command with custom prompt and markers
            sudo_cmd = f'sudo -S -p {self._shq(self._sudo_prompt)} {command}'
            
            wrapped = (
                f'PS1={self._shq(self.PROMPT)}; '
                f'echo {self._shq(self._start_marker)}; '
                f'{sudo_cmd}; '
                f'__S=$?; '
                f'echo {self._shq(self._end_marker)}$__S:$PWD'
            )
            
            self.shell.sendline(wrapped)
            
            # Step 1: Wait for start marker first
            try:
                self.shell.expect_exact(self._start_marker, timeout=5)
            except pexpect.TIMEOUT:
                self._resync()
                return "Error: Failed to start sudo command execution (shell desync)"
            except pexpect.EOF:
                self.close()
                self._init_shell()
                return "Shell died during sudo command"
            
            # Step 2: Now wait for sudo prompt or end marker
            password_sent = False
            end_pattern = re.compile(
                rf'{re.escape(self._end_marker)}(\d+):([^\r\n]+)',
                re.MULTILINE
            )
            
            while True:
                idx = self.shell.expect(
                    [self._sudo_prompt, end_pattern, r'Sorry, try again', pexpect.EOF, pexpect.TIMEOUT],
                    timeout=timeout
                )
                
                if idx == 0:  # Sudo password prompt
                    if password and not password_sent:
                        self.shell.sendline(password)
                        password_sent = True
                        continue
                    else:
                        # No password or already tried once
                        self.shell.sendcontrol('c')
                        try:
                            self.shell.expect_exact(self.PROMPT, timeout=3)
                        except:
                            pass
                        return "Sudo password required but not provided or incorrect"
                
                elif idx == 1:  # End marker
                    raw_output = self.shell.before or ""
                    exit_code = int(self.shell.match.group(1))
                    new_pwd = self.shell.match.group(2).strip()
                    
                    if new_pwd and new_pwd.startswith('/'):
                        self.current_dir = new_pwd
                    
                    try:
                        self.shell.expect_exact(self.PROMPT, timeout=3)
                    except:
                        pass
                    
                    output = self._normalize_output(raw_output)
                    
                    if exit_code != 0 and output:
                        output += f"\n[Exit code: {exit_code}]"
                    elif exit_code != 0:
                        output = f"Sudo command failed with exit code {exit_code}"
                    
                    return output if output else "Sudo command executed successfully."
                
                elif idx == 2:  # "Sorry, try again" - wrong password
                    self.shell.sendcontrol('c')
                    try:
                        self.shell.expect_exact(self.PROMPT, timeout=3)
                    except:
                        pass
                    return "Sudo password incorrect"
                
                elif idx == 3:  # EOF
                    self.close()
                    self._init_shell()
                    return "Shell died during sudo command"
                
                else:  # TIMEOUT
                    return self._handle_timeout(f"sudo {command}", timeout)
        
        except pexpect.TIMEOUT:
            return self._handle_timeout(f"sudo {command}", timeout)
        
        except Exception as e:
            try:
                self._resync()
            except:
                self.close()
                self._init_shell()
            return f"Error executing sudo command: {str(e)}"
    
    def get_current_dir(self) -> str:
        """Get the shell's current working directory (tracked automatically)"""
        return self.current_dir
    
    def close(self):
        """Cleanly close the shell session"""
        if self.shell:
            try:
                self.shell.terminate(force=True)
            except:
                pass
            try:
                self.shell.close(force=True)
            except:
                pass
            self.shell = None
