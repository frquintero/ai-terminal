"""
AI Terminal Tool Registry

Provides shell-first tools for the AI agent to interact with the system.
Philosophy: Prefer shell commands (run_command) over Python for most tasks.
Use Python sandbox only for visualization, ML, or explicit Python requirements.
"""

from abc import ABC, abstractmethod
import os
import subprocess
import sys
import shlex
import shutil
import json
import inspect
from typing import Dict, Any, List, Optional
from shell_integration import ShellIntegration


# ============================================================================
# Working Directory Isolation
# ============================================================================

WORKING_DIR_PREFIX = "ai-terminal-wd"

def _get_working_dir_path() -> str:
    """Get absolute path to working directory (relative to this script's location)"""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(tools_dir, WORKING_DIR_PREFIX)


# ============================================================================
# Base Tool Interface
# ============================================================================

class BaseTool(ABC):
    """
    Abstract base class for all tools available to the AI agent.
    
    Each tool must implement:
    - name: Unique identifier for the tool
    - description: Brief description of what the tool does
    - schema: JSON schema for tool parameters
    - execute: Method that performs the tool's action
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of tool purpose"""
        pass

    @property
    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        """JSON schema defining tool parameters for LLM"""
        pass

    @property
    def usage_examples(self) -> Optional[List[str]]:
        """
        Optional usage examples for this tool.
        Override in subclasses to provide common patterns.
        """
        return None

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """
        Execute the tool's action.
        
        Returns:
            String result to be passed back to the LLM
        """
        pass


# ============================================================================
# File Operations Tools
# ============================================================================

class ReadFileTool(BaseTool):
    """
    Read file contents into memory from the isolated working directory.
    
    Use for: Small to medium text files (< 5MB)
    Don't use for: Large files, binary files, or when you only need portions
    Alternative: Use run_command with head/tail/grep for large files
    """
    
    # Maximum file size to read (5MB default, configurable via env)
    MAX_BYTES = int(os.getenv("READ_FILE_MAX_BYTES", str(5 * 1024 * 1024)))
    
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return f"Read the contents of a file from the isolated working directory ({WORKING_DIR_PREFIX})"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": f"Read the contents of a file. IMPORTANT: Do NOT include '{WORKING_DIR_PREFIX}/' prefix in file_path - it is automatically prepended. Example: use 'script.sh' not '{WORKING_DIR_PREFIX}/script.sh'",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": f"Path relative to working directory (WITHOUT '{WORKING_DIR_PREFIX}/' prefix). Examples: 'file.txt', 'subdir/data.csv', 'config/settings.json'"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        }

    def execute(self, file_path: str) -> str:
        """
        Read and return file contents from isolated working directory.
        
        Guards:
        - File size limit to avoid memory exhaustion
        - UTF-8 encoding required (text files only)
        """
        # Prepend working directory prefix to isolate file operations
        isolated_path = os.path.join(_get_working_dir_path(), file_path)
        
        try:
            # Check file size before reading
            size = os.path.getsize(isolated_path)
            if size > self.MAX_BYTES:
                return (
                    f"File is {size} bytes; exceeds READ_FILE_MAX_BYTES={self.MAX_BYTES}. "
                    f"Use run_command with head/tail/less for large files."
                )
            
            with open(isolated_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return f"Error: File not found: {isolated_path}"
        except UnicodeDecodeError:
            return f"Error: File is not valid UTF-8 text. Use run_command with cat/hexdump for binary files."
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(BaseTool):
    """
    Create or overwrite files with text content in the isolated working directory.
    
    Use for: Config files, scripts, data files
    Note: For executable scripts, use run_command to chmod +x after writing
    """
    
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return f"Create or overwrite a file with content in the isolated working directory ({WORKING_DIR_PREFIX})"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": f"Create or overwrite a file with content. IMPORTANT: Do NOT include '{WORKING_DIR_PREFIX}/' prefix in file_path - it is automatically prepended. Example: use 'output.txt' not '{WORKING_DIR_PREFIX}/output.txt'",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": f"Path relative to working directory (WITHOUT '{WORKING_DIR_PREFIX}/' prefix). Examples: 'script.sh', 'logs/output.log', 'data/results.json'"
                        },
                        "content": {
                            "type": "string",
                            "description": "The content to write to the file"
                        }
                    },
                    "required": ["file_path", "content"]
                }
            }
        }
    
    @property
    def usage_examples(self) -> List[str]:
        return [
            "write_file('script.sh', '#!/bin/bash\\necho Hello')",
            "write_file('config/settings.json', '{\"debug\": true}')",
            "write_file('output/results.txt', 'Analysis complete\\nTotal: 100')"
        ]

    def execute(self, file_path: str, content: str) -> str:
        """
        Write content to file in isolated working directory, creating parent directories if needed.
        
        Security: No path traversal checks - agent should validate paths
        """
        # Get absolute working directory path
        working_dir = _get_working_dir_path()
        isolated_path = os.path.join(working_dir, file_path)
        
        try:
            # Ensure base working directory exists
            os.makedirs(working_dir, exist_ok=True)
            
            # Create parent directories if needed
            dirpath = os.path.dirname(isolated_path)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            
            with open(isolated_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return f"File written successfully: {isolated_path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


# ============================================================================
# Shell Command Execution Tools
# ============================================================================

class RunCommandTool(BaseTool):
    """
    Execute non-interactive shell commands.
    
    Use for: File operations, text processing, system queries, shell pipelines
    Don't use for: Interactive programs (vim, top), sudo commands, Python REPL
    
    Guards:
    - Blocks interactive commands → redirect to run_interactive
    - Blocks sudo/doas → redirect to run_sudo_command  
    - Blocks package managers without --noconfirm → requires explicit confirmation bypass
    """
    
    def __init__(self, shell: 'ShellIntegration' = None):
        self.shell = shell or ShellIntegration()

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return "Execute a non-interactive shell command. Do not use for: interactive programs (vim, nano, top), sudo commands (use run_sudo_command), or package managers without --noconfirm flag."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Execute a non-interactive shell command. Package managers (yay/pacman) must include --noconfirm flag. Use run_sudo_command for sudo. Will timeout if used with interactive programs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute"
                        }
                    },
                    "required": ["command"]
                }
            }
        }
    
    @property
    def usage_examples(self) -> List[str]:
        return [
            "ls -la /home/user/projects",
            "grep -r 'TODO' ./src",
            "find . -name '*.py' -type f",
            "ps aux | grep python",
            "df -h"
        ]

    def execute(self, command: str) -> str:
        """
        Execute shell command with safety guards.
        
        Protection layers:
        1. Sudo detection → redirect to run_sudo_command
        2. Package manager confirmation → enforce --noconfirm
        3. Interactive command detection → redirect to run_interactive
        4. Smart bypass for safe flags (--version, --help, -c for interpreters)
        """
        try:
            # Parse command tokens
            tokens = shlex.split(command) if command.strip() else []
            if not tokens:
                return "Error: Empty command"
            
            # Control operators that delimit simple commands in a pipeline
            CONTROL_OPS = {'|', '||', '&&', ';'}
            
            # Extract first simple command (before any pipe/control operator)
            first_cmd_tokens = []
            for t in tokens:
                if t in CONTROL_OPS:
                    break
                first_cmd_tokens.append(t)
            
            if not first_cmd_tokens:
                return "Error: Empty command"
            
            # Identify the actual command being executed
            base = first_cmd_tokens[0]
            base_name = os.path.basename(base)
            
            # Handle sudo/doas prefix
            if base_name in ('sudo', 'doas'):
                if len(first_cmd_tokens) < 2:
                    return "Error: sudo/doas used without a target command."
                target_name = os.path.basename(first_cmd_tokens[1])
            else:
                target_name = base_name
            
            # ----------------------------------------------------------------
            # GUARD 1: Redirect sudo/doas to run_sudo_command
            # ----------------------------------------------------------------
            if base_name in ('sudo', 'doas'):
                return (
                    "Error: This command uses sudo. "
                    "Use run_sudo_command tool to handle password prompts safely."
                )
            
            # ----------------------------------------------------------------
            # GUARD 2: Package manager operations require confirmation bypass
            # ----------------------------------------------------------------
            if target_name in {'yay', 'pacman', 'apt', 'apt-get', 'dnf', 'yum', 'zypper', 'apk'}:
                flags = [t for t in first_cmd_tokens[1:] if t.startswith('-')]
                
                # Arch-based package managers
                if target_name in {'pacman', 'yay'}:
                    # Check for system-modifying operations: -S (sync/install), -R (remove), -U (upgrade)
                    has_privileged_operation = any(
                        any(c in flag for c in ['S', 'R', 'U']) 
                        for flag in flags
                    )
                    if has_privileged_operation and '--noconfirm' not in tokens:
                        return (
                            f"Error: Package manager '{target_name}' requires root privileges and confirmation. "
                            f"Use run_sudo_command with --noconfirm flag. "
                            f"Example: run_sudo_command('{command} --noconfirm', password='...')"
                        )
                
                # Other package managers (apt, dnf, yum, zypper, apk)
                else:
                    return (
                        f"Error: Package manager '{target_name}' likely requires root privileges. "
                        f"Use run_sudo_command with appropriate non-interactive flags (e.g., -y for apt/dnf)."
                    )
            
            # ----------------------------------------------------------------
            # GUARD 3: Interactive command detection with smart bypass
            # ----------------------------------------------------------------
            cmd_is_interactive = target_name in InteractiveCommandTool.INTERACTIVE_COMMANDS
            
            if cmd_is_interactive:
                # Safe flags that allow non-interactive usage
                SAFE_GLOBAL_FLAGS = {'--version', '-V', '--help', '-h'}
                INTERPRETERS = {'python', 'python3', 'node', 'ruby', 'bash', 'sh', 'zsh'}
                
                # Check for universal safe flags (version/help)
                safe_global = any(flag in SAFE_GLOBAL_FLAGS for flag in first_cmd_tokens)
                
                # Check for interpreter safe modes (script execution)
                interpreter_safe = False
                if target_name in INTERPRETERS:
                    # Flags that execute code without REPL: -c, -m, -e
                    script_flags = {'-c', '-m', '-e'}
                    if any(flag in script_flags for flag in first_cmd_tokens):
                        interpreter_safe = True
                    # Heuristic: if there are additional args, likely executing a script
                    elif len(first_cmd_tokens) > 1:
                        interpreter_safe = True
                
                # Bypass interactive guard if safe pattern detected
                if safe_global or interpreter_safe:
                    return self.shell.run_command(command)
                
                # Block interactive usage
                return (
                    f"Error: '{target_name}' is an interactive command. "
                    f"Use run_interactive tool to avoid timeout."
                )
            
            # Execute command via shell integration
            return self.shell.run_command(command)
            
        except Exception as e:
            return f"Error executing command: {str(e)}"


class SudoRunCommandTool(BaseTool):
    """
    Execute commands with sudo privileges.
    
    Use for: System administration tasks requiring root
    Handles: Password prompts, passwordless sudo
    Guard: Package managers must include --noconfirm to avoid interactive prompts
    """
    
    def __init__(self, shell: 'ShellIntegration' = None):
        self.shell = shell or ShellIntegration()
    
    @property
    def name(self) -> str:
        return "run_sudo_command"
    
    @property
    def description(self) -> str:
        return "Execute a command with sudo privileges, handling password prompts"
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "run_sudo_command",
                "description": "Execute a command with sudo privileges, handling password prompts",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The command to execute with sudo (do not include 'sudo' prefix)"
                        },
                        "password": {
                            "type": "string",
                            "description": "Sudo password (optional if passwordless sudo is configured)"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Command timeout in seconds (default: 60)",
                            "default": 60
                        }
                    },
                    "required": ["command"]
                }
            }
        }
    
    def execute(self, command: str, password: str = None, timeout: int = 60) -> str:
        """
        Execute command with sudo, enforcing non-interactive package manager usage.
        
        Security: Password is never logged or persisted
        """
        try:
            # Parse command to detect package managers
            tokens = shlex.split(command) if command.strip() else []
            if not tokens:
                return "Error: Empty command"
            
            cmd_names = [os.path.basename(t) for t in tokens if not t.startswith('-')]
            
            # Enforce --noconfirm for package managers to avoid hanging on prompts
            if cmd_names:
                base_cmd = cmd_names[0]
                if base_cmd in {'yay', 'pacman'}:
                    flags = [t for t in tokens if t.startswith('-')]
                    # Check for operations that modify system state
                    has_prompt_operation = any(
                        any(c in flag for c in ['S', 'R', 'U']) 
                        for flag in flags
                    )
                    
                    if has_prompt_operation and '--noconfirm' not in tokens:
                        return (
                            f"Error: Package manager '{base_cmd}' may prompt for confirmation. "
                            f"Add --noconfirm to run non-interactively. "
                            f"Example: '{command} --noconfirm'"
                        )
            
            # Execute via shell integration
            return self.shell.run_sudo_command(command, password, timeout)
            
        except Exception as e:
            return f"Error executing sudo command: {str(e)}"


class InteractiveCommandTool(BaseTool):
    """
    Execute interactive programs that require TTY (terminal control).
    
    Use for: Text editors (vim, nano), TUI programs (top, htop), interactive shells
    Requires: TTY-enabled environment (won't work in background/cron jobs)
    Note: Agent cannot interact with the program - user controls it directly
    """
    
    # Commands known to require full terminal control
    INTERACTIVE_COMMANDS = {
        'vim', 'vi', 'nano', 'emacs', 'less', 'more', 'top', 'htop', 
        'man', 'ssh', 'mysql', 'psql', 'mongo', 'python', 'python3',
        'node', 'irb', 'ruby', 'bash', 'zsh', 'sh', 'tmux', 'screen'
    }
    
    @property
    def name(self) -> str:
        return "run_interactive"
    
    @property
    def description(self) -> str:
        return "Execute an interactive command that requires full terminal control (vim, nano, top, etc.)"
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "run_interactive",
                "description": "Execute an interactive command that requires full terminal control (vim, nano, top, etc.)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The interactive command to execute (e.g., 'vim file.txt', 'top', 'nano config.py')"
                        }
                    },
                    "required": ["command"]
                }
            }
        }
    
    @property
    def usage_examples(self) -> List[str]:
        return [
            "vim /etc/hosts",
            "nano ~/.bashrc",
            "top",
            "htop"
        ]
    
    def execute(self, command: str) -> str:
        """
        Pass full terminal control to the command.
        
        Limitations:
        - Requires TTY (fails in non-interactive contexts)
        - Agent cannot see or control the program
        - User must interact directly
        """
        try:
            # Verify TTY availability
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                return "Interactive commands require a TTY; cannot run in non-interactive environment."
            
            # Execute with full terminal control - stdin/stdout/stderr connected
            result = subprocess.run(
                command,
                shell=True,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            
            # Report exit status
            if result.returncode == 0:
                return f"Interactive command '{command}' completed successfully."
            else:
                return f"Interactive command '{command}' exited with code {result.returncode}."
                
        except KeyboardInterrupt:
            return f"Interactive command '{command}' was interrupted by user."
        except Exception as e:
            return f"Error executing interactive command: {str(e)}"


# ============================================================================
# Python Sandbox Tool
# ============================================================================

class RunPythonSandboxTool(BaseTool):
    """
    Execute Python code in an isolated, resource-limited sandbox.
    
    Use ONLY for:
    - Data visualization/plotting (matplotlib, seaborn)
    - Complex algorithms, ML, scientific computing (numpy, scipy, sklearn)
    - API calls or database operations requiring Python libraries
    - Explicit Python library usage (pandas, requests, etc.)
    
    DON'T use for:
    - File operations (use run_command with cat/grep/sed/awk)
    - Text processing (use run_command with shell pipelines)
    - System queries (use run_command)
    
    Features:
    - Resource limits (CPU, memory, file size)
    - Auto-capture matplotlib plots to artifacts
    - Project file access via SANDBOX_PROJECT env var
    - Optional network isolation
    """
    
    @property
    def name(self) -> str:
        return "run_python_sandbox"
    
    @property
    def description(self) -> str:
        return "Run Python code in an isolated, resource-limited sandbox with data science libs (pandas, numpy, matplotlib). Auto-saves plots to artifacts."
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "run_python_sandbox",
                "description": "Run Python code in an isolated, resource-limited sandbox with data science libs (pandas, numpy, matplotlib). Auto-saves plots to artifacts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Path to an existing .py script (alternative to code parameter)"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (optional, uses SANDBOX_TIMEOUT env default)"
                        },
                        "return_artifacts": {
                            "type": "boolean",
                            "description": "List saved artifacts (default: true)",
                            "default": True
                        }
                    }
                }
            }
        }
    
    @property
    def usage_examples(self) -> List[str]:
        """Critical patterns for sandbox file I/O"""
        return [
            """# Reading project CSV files
import os
import pandas as pd
project_dir = os.environ['SANDBOX_PROJECT']
df = pd.read_csv(os.path.join(project_dir, 'data.csv'))
print(df.head())""",
            
            """# Creating plots (automatically saved to artifacts)
import matplotlib.pyplot as plt
import numpy as np
x = np.linspace(0, 10, 100)
plt.plot(x, np.sin(x))
plt.title('Sine Wave')
# Plot automatically saved to artifacts/plot_1.png""",
            
            """# Writing results back to project
import os
project_dir = os.environ['SANDBOX_PROJECT']
with open(os.path.join(project_dir, 'output.txt'), 'w') as f:
    f.write('Analysis results:\\n')
    f.write('Mean: 42.5\\n')"""
        ]
    
    def execute(self, code: str = None, file_path: str = None, timeout: int = None, return_artifacts: bool = True) -> str:
        """
        Execute Python code in sandboxed environment.
        
        Sandbox protections:
        - CPU time limit (SANDBOX_MAX_CPU_SEC, default 20s)
        - Memory limit (SANDBOX_MAX_MEM_MB, default 1024MB)
        - File size limit (SANDBOX_MAX_FSIZE_MB, default 50MB)
        - Optional network isolation (SANDBOX_DISABLE_NETWORK=1)
        - Optional project write protection (SANDBOX_ALLOW_PROJECT_WRITES=0)
        
        Environment:
        - SANDBOX_PROJECT: Path to project directory for file access
        - Matplotlib configured for non-interactive backend
        - Plots automatically saved to artifacts/
        """
        import uuid
        import shutil as _shutil
        import textwrap
        import signal
        from pathlib import Path
        
        # Validate inputs
        if not code and not file_path:
            return "Error: Either 'code' or 'file_path' parameter is required"
        
        # Optional POSIX resource limits
        try:
            import resource
        except ImportError:
            resource = None
        
        # Capture original working directory for project file access
        original_cwd = Path(os.getcwd()).resolve()
        
        # Setup isolated run directory
        base = os.getenv("SANDBOX_PATH", "./sandbox_runs")
        run_id = str(uuid.uuid4())
        run_dir = (Path(base) / "runs" / run_id).resolve()
        artifacts_dir = run_dir / "artifacts"
        
        try:
            os.makedirs(artifacts_dir, mode=0o700, exist_ok=True)
        except Exception as e:
            return f"Error creating sandbox directory: {str(e)}"
        
        # Create symlink to project directory for convenient access
        project_link = run_dir / "project"
        try:
            project_link.symlink_to(original_cwd, target_is_directory=True)
            project_mount = project_link
        except Exception:
            # Symlink not supported (e.g., Windows without privileges)
            project_mount = original_cwd
        
        # Prepare script
        try:
            if file_path:
                src = Path(file_path)
                if not src.exists():
                    return f"Error: file not found: {file_path}"
                script_path = run_dir / src.name
                _shutil.copy2(src, script_path)
            else:
                script_path = run_dir / "script.py"
                script_path.write_text(code or "", encoding='utf-8')
        except Exception as e:
            return f"Error preparing script: {str(e)}"
        
        # ----------------------------------------------------------------
        # Inject sandbox prologue and epilogue
        # ----------------------------------------------------------------
        
        disable_net = os.getenv("SANDBOX_DISABLE_NETWORK", "0") in ("1", "true", "yes")
        
        # Write protection for project directory
        write_protection = """
# Write protection for project directory
_allow_writes = os.environ.get("SANDBOX_ALLOW_PROJECT_WRITES", "1") in ("1", "true", "yes")
if not _allow_writes:
    _original_open = open
    _project_dir = os.environ.get("SANDBOX_PROJECT", "")
    _real_project = os.path.realpath(_project_dir) if _project_dir else ""
    
    def _protected_open(file, mode='r', *args, **kwargs):
        # Check if this is a write operation to project directory
        if _real_project and ('w' in mode or 'a' in mode or 'x' in mode or '+' in mode):
            try:
                real_path = os.path.realpath(os.path.abspath(str(file)))
                if real_path.startswith(_real_project + os.sep) or real_path == _real_project:
                    raise PermissionError(f"Write access to project directory is disabled (SANDBOX_ALLOW_PROJECT_WRITES=0): {file}")
            except PermissionError:
                raise  # Re-raise PermissionError
            except (OSError, ValueError):
                pass  # Only catch path resolution errors
        return _original_open(file, mode, *args, **kwargs)
    
    import builtins
    builtins.open = _protected_open
"""
        
        prologue = """
import os
import sys
{write_protection}
# Matplotlib: configure non-interactive backend
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    def _no_show(*args, **kwargs): pass
    plt.show = _no_show
except ImportError:
    pass  # matplotlib not available
# Optional network isolation
{disable_net}
""".format(
            disable_net=textwrap.dedent("""
try:
    import socket
    class _BlockedSocket(socket.socket):
        def __init__(self, *a, **k): raise RuntimeError("Network disabled in sandbox")
    socket.socket = _BlockedSocket
    socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Network disabled"))
except Exception: pass
""") if disable_net else "",
            write_protection=write_protection
        )

        # Auto-save matplotlib figures to artifacts
        epilogue = """
# Auto-save matplotlib figures
try:
    import matplotlib.pyplot as _plt
    import os
    artifacts_path = os.path.join(os.getcwd(), "artifacts")
    os.makedirs(artifacts_path, exist_ok=True)
    for i, num in enumerate(_plt.get_fignums(), start=1):
        _plt.figure(num).savefig(os.path.join(artifacts_path, f"plot_{i}.png"), dpi=150, bbox_inches="tight")
except ImportError:
    pass  # matplotlib not available
except Exception as _e:
    import sys
    print(f"[sandbox] plot save error: {_e}", file=sys.stderr)
"""

        # Inject prologue and epilogue into script
        try:
            original = script_path.read_text(encoding='utf-8')
            script_path.write_text(prologue + "\n" + original + "\n" + epilogue, encoding='utf-8')
        except Exception as e:
            return f"Error injecting sandbox wrappers: {str(e)}"
        
        # ----------------------------------------------------------------
        # Configure execution environment
        # ----------------------------------------------------------------
        
        # Python binary
        py = os.getenv("SANDBOX_PYTHON") or sys.executable
        args = [py, "-I", "-B", script_path.name]
        
        # Minimal environment
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(run_dir),
            "PYTHONNOUSERSITE": "1",
            "PYTHONHASHSEED": "0",
            "MPLBACKEND": "Agg",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "SANDBOX_ORIGINAL_CWD": str(original_cwd),
            "SANDBOX_PROJECT": str(project_mount),  # Access project files via this path
            "SANDBOX_RUN_DIR": str(run_dir),
            "SANDBOX_ALLOW_PROJECT_WRITES": os.getenv("SANDBOX_ALLOW_PROJECT_WRITES", "1"),
        }
        # Preserve locale settings
        env.update({k: v for k, v in os.environ.items() if k in ("LC_ALL", "LANG")})
        
        # Resource limits (configurable via environment)
        max_cpu = int(os.getenv("SANDBOX_MAX_CPU_SEC", "20"))
        max_mem_mb = int(os.getenv("SANDBOX_MAX_MEM_MB", "1024"))
        max_fsize_mb = int(os.getenv("SANDBOX_MAX_FSIZE_MB", "50"))
        if timeout is None:
            timeout = int(os.getenv("SANDBOX_TIMEOUT", str(max_cpu)))
        
        def _apply_limits():
            """Apply POSIX resource limits in subprocess"""
            try:
                os.setsid()  # Create new process group for clean termination
                if resource:
                    # CPU time limit
                    resource.setrlimit(resource.RLIMIT_CPU, (max_cpu, max_cpu))
                    # Memory limit
                    if hasattr(resource, "RLIMIT_AS"):
                        resource.setrlimit(resource.RLIMIT_AS, (max_mem_mb * 1024 * 1024, max_mem_mb * 1024 * 1024))
                    elif hasattr(resource, "RLIMIT_DATA"):
                        resource.setrlimit(resource.RLIMIT_DATA, (max_mem_mb * 1024 * 1024, max_mem_mb * 1024 * 1024))
                    # File size limit
                    resource.setrlimit(resource.RLIMIT_FSIZE, (max_fsize_mb * 1024 * 1024, max_fsize_mb * 1024 * 1024))
                    # File descriptor limit
                    if hasattr(resource, "RLIMIT_NOFILE"):
                        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
                    # Note: RLIMIT_NPROC disabled to allow matplotlib threading
            except Exception:
                pass  # Resource limits not critical
        
        # ----------------------------------------------------------------
        # Execute sandboxed code
        # ----------------------------------------------------------------
        
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(run_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                preexec_fn=_apply_limits if os.name == "posix" else None
            )
        except Exception as e:
            return f"Error starting sandbox process: {str(e)}"
        
        # Wait for completion with timeout
        timed_out = False
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Kill process group to clean up any child processes
            try:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except Exception:
                pass
            out, err = proc.communicate()
        except Exception as e:
            return f"Error executing sandbox: {str(e)}"
        
        # ----------------------------------------------------------------
        # Collect artifacts (plots, exports)
        # ----------------------------------------------------------------
        
        artifacts = []
        if return_artifacts and artifacts_dir.exists():
            for p in sorted(artifacts_dir.glob("*")):
                if p.suffix.lower() in (".png", ".svg", ".html", ".csv", ".json"):
                    try:
                        artifacts.append({"path": str(p), "size": p.stat().st_size})
                    except Exception:
                        pass
        
        # Save execution manifest
        manifest = {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "exit_code": None if timed_out else proc.returncode,
            "timed_out": timed_out,
            "artifacts": artifacts,
        }
        
        try:
            (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        except Exception:
            pass  # Non-critical
        
        # ----------------------------------------------------------------
        # Format result for agent
        # ----------------------------------------------------------------
        
        parts = []
        parts.append(f"[python-sandbox] run_id={run_id}")
        parts.append(f"Interpreter: {py}")
        parts.append(f"Project Mount: {project_mount}")
        parts.append(f"Timeout: {timeout}s (timed_out={timed_out})")
        parts.append(f"Exit code: {manifest['exit_code']}")
        
        if out:
            parts.append("Stdout:\n" + out)
        if err:
            parts.append("Stderr:\n" + err)
        if artifacts:
            parts.append("Artifacts:")
            for a in artifacts:
                parts.append(f"- {a['path']} ({a['size']} bytes)")
        
        parts.append(f"Manifest: {run_dir / 'manifest.json'}")
        
        return "\n".join(parts)


# ============================================================================
# Tool Registry - Automatic Discovery
# ============================================================================

def _iter_tool_classes(module):
    """
    Discover all BaseTool subclasses defined in this module.
    
    Auto-registers all concrete tool classes unless AUTO_REGISTER=False.
    """
    for _, obj in inspect.getmembers(module, inspect.isclass):
        # Only classes defined in this file
        if obj.__module__ != module.__name__:
            continue
        # Skip BaseTool itself and non-subclasses
        if not issubclass(obj, BaseTool) or obj is BaseTool:
            continue
        # Skip abstract classes
        if inspect.isabstract(obj):
            continue
        # Allow opt-out via class attribute
        if not getattr(obj, "AUTO_REGISTER", True):
            continue
        yield obj


def _instantiate_tool(cls):
    """
    Instantiate a tool class.
    
    Raises TypeError if class doesn't have a zero-arg constructor.
    """
    try:
        return cls()
    except TypeError as e:
        raise TypeError(f"Auto-registration requires a no-arg constructor: {cls.__name__}: {e}")


def _build_tools():
    """
    Build the TOOLS dictionary from discovered tool classes.
    
    Returns:
        Dict mapping tool names to tool instances
    """
    instances = [_instantiate_tool(cls) for cls in _iter_tool_classes(sys.modules[__name__])]
    # Sort by tool name for deterministic order
    instances.sort(key=lambda t: t.name)
    tools = {}
    for inst in instances:
        if inst.name in tools:
            raise ValueError(f"Duplicate tool name detected: {inst.name}")
        tools[inst.name] = inst
    return tools


# Global tool registry - automatically populated
TOOLS: Dict[str, BaseTool] = _build_tools()


def get_tool_schemas() -> List[Dict[str, Any]]:
    """
    Get JSON schemas for all registered tools.
    
    Used by the agent to provide tool definitions to the LLM.
    """
    return [tool.schema for tool in TOOLS.values()]
