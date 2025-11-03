from abc import ABC, abstractmethod
import os
import subprocess
import sys
import shlex
import urllib.request
import urllib.parse
import json
import inspect
from typing import Dict, Any, List, Optional
from shell_integration import ShellIntegration

class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def execute(self, **kwargs) -> str:
        pass

class ReadFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "The path to the file to read"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        }

    def execute(self, file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

class WriteFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Create or overwrite a file with content"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or overwrite a file with content",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "The path to the file to create or overwrite"
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

    def execute(self, file_path: str, content: str) -> str:
        try:
            dirpath = os.path.dirname(file_path)
            if dirpath:  # Only create dirs if path contains directory component
                os.makedirs(dirpath, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"File written successfully: {file_path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

class RunCommandTool(BaseTool):
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

    def execute(self, command: str) -> str:
        try:
            # Guard against interactive commands to prevent timeouts
            tokens = shlex.split(command) if command.strip() else []
            if not tokens:
                return "Error: Empty command"
            
            # Extract command names (skip flags starting with -)
            cmd_names = [os.path.basename(t) for t in tokens if not t.startswith('-')]
            
            # Guard 1: Check for sudo/doas - redirect to run_sudo_command
            if cmd_names and cmd_names[0] in ('sudo', 'doas'):
                return "Error: This command uses sudo. Use run_sudo_command tool to handle password prompts safely."
            
            # Guard 2: Check for package managers that may require confirmation and/or sudo
            if cmd_names:
                base_cmd = cmd_names[0]
                if base_cmd in {'yay', 'pacman'}:
                    # Check if this is a privileged operation (S/U/R flags)
                    flags = [t for t in tokens if t.startswith('-')]
                    has_privileged_operation = any(
                        any(c in flag for c in ['S', 'R', 'U']) 
                        for flag in flags
                    )
                    
                    if has_privileged_operation:
                        # These operations require sudo - enforce it
                        return (
                            f"Error: Package manager command '{base_cmd}' with install/update/remove operations requires root privileges. "
                            f"Use run_sudo_command tool with --noconfirm flag. "
                            f"Example: run_sudo_command('{command} --noconfirm', password='your_password')"
                        )
            
            # Guard 3: Check if any command name is interactive
            is_interactive = False
            interactive_cmd = None
            
            if cmd_names:
                # Check first command
                if cmd_names[0] in InteractiveCommandTool.INTERACTIVE_COMMANDS:
                    is_interactive = True
                    interactive_cmd = cmd_names[0]
                # Check sudo/doas followed by interactive command (shouldn't reach here due to Guard 1)
                elif cmd_names[0] in ('sudo', 'doas') and len(cmd_names) > 1:
                    if cmd_names[1] in InteractiveCommandTool.INTERACTIVE_COMMANDS:
                        is_interactive = True
                        interactive_cmd = cmd_names[1]
                # Check for interactive command anywhere (catches /usr/bin/vim, etc.)
                else:
                    for name in cmd_names:
                        if name in InteractiveCommandTool.INTERACTIVE_COMMANDS:
                            is_interactive = True
                            interactive_cmd = name
                            break
            
            if is_interactive:
                # Smart guard: allow non-interactive usage patterns
                SAFE_GLOBAL_FLAGS = {'--version', '-V', '--help', '-h'}
                INTERPRETERS = {'python', 'python3', 'node', 'ruby', 'bash', 'sh', 'zsh'}
                
                # Check for universal safe flags
                safe_global = any(flag in SAFE_GLOBAL_FLAGS for flag in tokens)
                
                # Check for interpreter safe modes
                interpreter_safe = False
                if interactive_cmd in INTERPRETERS:
                    # Check for script execution flags
                    script_flags = {'-c', '-m', '-e'}
                    if any(flag in script_flags for flag in tokens):
                        interpreter_safe = True
                    # Check for script file argument (heuristic: command + arguments > 1)
                    elif len(cmd_names) > 1:
                        interpreter_safe = True
                
                # Bypass guard if safe pattern detected
                if safe_global or interpreter_safe:
                    return self.shell.run_command(command)
                
                return f"Error: '{interactive_cmd}' is an interactive command. Use run_interactive tool instead to avoid timeout."
            
            return self.shell.run_command(command)
        except Exception as e:
            return f"Error executing command: {str(e)}"

class ChatTool(BaseTool):
    # Deprecated: Assistants should respond directly without tools for conversation
    AUTO_REGISTER = False
    
    @property
    def name(self) -> str:
        return "chat"

    @property
    def description(self) -> str:
        return "Provide a conversational response"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "chat",
                "description": "Provide a conversational response",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The conversational message"
                        }
                    },
                    "required": ["message"]
                }
            }
        }

    def execute(self, message: str) -> str:
        return message  # For now, just echo; in agent, this will be handled by AI

class ContentProcessingTool(BaseTool):
    @property
    def name(self) -> str:
        return "process_content"

    @property
    def description(self) -> str:
        return "Analyze and process text content"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "process_content",
                "description": "Analyze and process text content",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The text content to process"
                        },
                        "task": {
                            "type": "string",
                            "description": "The processing task (e.g., summarize, analyze)"
                        }
                    },
                    "required": ["content", "task"]
                }
            }
        }

    def execute(self, content: str, task: str) -> str:
        # Placeholder; in practice, this might call AI or simple processing
        if task.lower() == "summarize":
            return f"Summary: {content[:100]}..."  # Simple truncation for now
        return f"Processed content for task '{task}': {content}"

class SudoRunCommandTool(BaseTool):
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
        try:
            # Parse command to check for package manager operations
            tokens = shlex.split(command) if command.strip() else []
            if not tokens:
                return "Error: Empty command"
            
            cmd_names = [os.path.basename(t) for t in tokens if not t.startswith('-')]
            
            # Guard: Check for package managers that may require confirmation
            if cmd_names:
                base_cmd = cmd_names[0]
                if base_cmd in {'yay', 'pacman'}:
                    # Check if this is a prompt-prone operation (S/U/R flags)
                    flags = [t for t in tokens if t.startswith('-')]
                    has_prompt_operation = any(
                        any(c in flag for c in ['S', 'R', 'U']) 
                        for flag in flags
                    )
                    
                    if has_prompt_operation and '--noconfirm' not in tokens:
                        return (
                            f"Error: Package manager command '{base_cmd}' may prompt for confirmation. "
                            f"Add --noconfirm to the command to run non-interactively. "
                            f"Example: '{command} --noconfirm'"
                        )
            
            return self.shell.run_sudo_command(command, password, timeout)
        except Exception as e:
            return f"Error executing sudo command: {str(e)}"

class InteractiveCommandTool(BaseTool):
    # List of known interactive commands that require TTY
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
    
    def execute(self, command: str) -> str:
        try:
            # Verify TTY is available for interactive commands
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
            
            if result.returncode == 0:
                return f"Interactive command '{command}' completed successfully."
            else:
                return f"Interactive command '{command}' exited with code {result.returncode}."
        except KeyboardInterrupt:
            return f"Interactive command '{command}' was interrupted by user."
        except Exception as e:
            return f"Error executing interactive command: {str(e)}"

class WikipediaSearchTool(BaseTool):
    @property
    def name(self) -> str:
        return "wikipedia_search"
    
    @property
    def description(self) -> str:
        return "Search Wikipedia for general knowledge, definitions, or external information"
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "wikipedia_search",
                "description": "Search Wikipedia for general knowledge, definitions, or external information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query or topic to look up on Wikipedia"
                        },
                        "sentences": {
                            "type": "integer",
                            "description": "Number of sentences to return (default: 3)",
                            "default": 3
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    
    def execute(self, query: str, sentences: int = 3) -> str:
        try:
            # Create a request with User-Agent header (Wikipedia requires it)
            headers = {
                'User-Agent': 'AI-Terminal/1.0 (https://github.com/frquintero/ai-terminal) Python-urllib'
            }
            
            # Step 1: Search for the page title
            search_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&list=search&srsearch={urllib.parse.quote(query)}&srlimit=1"
            
            request = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(request, timeout=10) as response:
                search_data = json.loads(response.read().decode())
            
            # Check if we got any results
            if not search_data.get('query', {}).get('search'):
                return f"No Wikipedia results found for '{query}'"
            
            # Get the first search result's title
            page_title = search_data['query']['search'][0]['title']
            
            # Step 2: Fetch the page extract
            extract_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&prop=extracts&exintro=1&explaintext=1&titles={urllib.parse.quote(page_title)}"
            
            request = urllib.request.Request(extract_url, headers=headers)
            with urllib.request.urlopen(request, timeout=10) as response:
                extract_data = json.loads(response.read().decode())
            
            # Extract the content
            pages = extract_data.get('query', {}).get('pages', {})
            if not pages:
                return f"Could not retrieve content for '{page_title}'"
            
            page = list(pages.values())[0]
            extract = page.get('extract', '')
            
            if not extract:
                return f"No content available for '{page_title}'"
            
            # Split into sentences and take the requested number
            # Simple sentence splitting (could be improved)
            sentence_list = extract.replace('.\n', '. ').split('. ')
            result_sentences = sentence_list[:sentences]
            result_text = '. '.join(result_sentences)
            
            # Ensure it ends with a period
            if not result_text.endswith('.'):
                result_text += '.'
            
            return f"Wikipedia - {page_title}:\n\n{result_text}"
            
        except urllib.error.URLError as e:
            return f"Network error accessing Wikipedia: {str(e)}"
        except json.JSONDecodeError as e:
            return f"Error parsing Wikipedia response: {str(e)}"
        except Exception as e:
            return f"Error searching Wikipedia: {str(e)}"

class RunPythonSandboxTool(BaseTool):
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
    
    def execute(self, code: str = None, file_path: str = None, timeout: int = None, return_artifacts: bool = True) -> str:
        import tempfile
        import uuid
        import shutil
        import textwrap
        import signal
        from pathlib import Path
        
        # Validate inputs
        if not code and not file_path:
            return "Error: Either 'code' or 'file_path' parameter is required"
        
        # Optional POSIX resource limits
        try:
            import resource
        except Exception:
            resource = None
        
        # Setup run directory
        base = os.getenv("SANDBOX_PATH", "./sandbox_runs")
        run_id = str(uuid.uuid4())
        run_dir = Path(base) / "runs" / run_id
        artifacts_dir = run_dir / "artifacts"
        
        try:
            os.makedirs(artifacts_dir, mode=0o700, exist_ok=True)
        except Exception as e:
            return f"Error creating sandbox directory: {str(e)}"
        
        # Prepare code
        try:
            if file_path:
                src = Path(file_path)
                if not src.exists():
                    return f"Error: file not found: {file_path}"
                script_path = run_dir / src.name
                shutil.copy2(src, script_path)
            else:
                script_path = run_dir / "script.py"
                script_path.write_text(code or "", encoding='utf-8')
        except Exception as e:
            return f"Error preparing script: {str(e)}"
        
        # Inject plotting/network prologue + epilogue
        disable_net = os.getenv("SANDBOX_DISABLE_NETWORK", "1") in ("1", "true", "yes")
        prologue = """
import os
import sys
# plotting safe mode (optional - only if matplotlib is available)
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    def _no_show(*args, **kwargs): pass
    plt.show = _no_show
except ImportError:
    pass  # matplotlib not available, skip plotting setup
# optional network disable
{disable_net}
""".format(disable_net=textwrap.dedent("""
try:
    import socket
    class _BlockedSocket(socket.socket):
        def __init__(self, *a, **k): raise RuntimeError("Network disabled in sandbox")
    socket.socket = _BlockedSocket
    socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Network disabled"))
except Exception: pass
""") if disable_net else "")

        # Use relative path for epilogue since we run with cwd=run_dir
        epilogue = """
# auto-save figures (if matplotlib is available)
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

        # Rebuild script with wrappers
        try:
            original = script_path.read_text(encoding='utf-8')
            script_path.write_text(prologue + "\n" + original + "\n" + epilogue, encoding='utf-8')
        except Exception as e:
            return f"Error injecting sandbox wrappers: {str(e)}"
        
        # Python binary
        py = os.getenv("SANDBOX_PYTHON") or sys.executable
        # Use relative path since we set cwd to run_dir
        args = [py, "-I", "-B", script_path.name]
        
        # Env
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
        }
        # Keep only safe inherited vars
        env.update({k: v for k, v in os.environ.items() if k in ("LC_ALL", "LANG")})
        
        # Limits
        max_cpu = int(os.getenv("SANDBOX_MAX_CPU_SEC", "20"))
        max_mem_mb = int(os.getenv("SANDBOX_MAX_MEM_MB", "1024"))
        max_fsize_mb = int(os.getenv("SANDBOX_MAX_FSIZE_MB", "50"))
        if timeout is None:
            timeout = int(os.getenv("SANDBOX_TIMEOUT", str(max_cpu)))
        
        def _limit():
            """Apply resource limits in subprocess (POSIX only)"""
            try:
                os.setsid()
                if resource:
                    resource.setrlimit(resource.RLIMIT_CPU, (max_cpu, max_cpu))
                    # Address space or data
                    if hasattr(resource, "RLIMIT_AS"):
                        resource.setrlimit(resource.RLIMIT_AS, (max_mem_mb * 1024 * 1024, max_mem_mb * 1024 * 1024))
                    elif hasattr(resource, "RLIMIT_DATA"):
                        resource.setrlimit(resource.RLIMIT_DATA, (max_mem_mb * 1024 * 1024, max_mem_mb * 1024 * 1024))
                    resource.setrlimit(resource.RLIMIT_FSIZE, (max_fsize_mb * 1024 * 1024, max_fsize_mb * 1024 * 1024))
                    if hasattr(resource, "RLIMIT_NOFILE"):
                        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
                    if hasattr(resource, "RLIMIT_NPROC"):
                        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            except Exception:
                pass
        
        # Run
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(run_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                preexec_fn=_limit if os.name == "posix" else None
            )
        except Exception as e:
            return f"Error starting sandbox process: {str(e)}"
        
        timed_out = False
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
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
        
        # Collect artifacts
        artifacts = []
        if return_artifacts and artifacts_dir.exists():
            for p in sorted(artifacts_dir.glob("*")):
                if p.suffix.lower() in (".png", ".svg", ".html", ".csv", ".json"):
                    try:
                        artifacts.append({"path": str(p), "size": p.stat().st_size})
                    except Exception:
                        pass
        
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
        
        # Build textual result
        parts = []
        parts.append(f"[python-sandbox] run_id={run_id}")
        parts.append(f"Interpreter: {py}")
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

# Automatic tool discovery and registration
def _iter_tool_classes(module):
    """Discover all BaseTool subclasses defined in this module"""
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
    """Instantiate a tool class with zero-arg constructor"""
    try:
        return cls()
    except TypeError as e:
        raise TypeError(f"Auto-registration requires a no-arg constructor: {cls.__name__}: {e}")

def _build_tools():
    """Build the TOOLS dictionary from discovered tool classes"""
    instances = [_instantiate_tool(cls) for cls in _iter_tool_classes(sys.modules[__name__])]
    # Sort by tool name for deterministic order
    instances.sort(key=lambda t: t.name)
    tools = {}
    for inst in instances:
        if inst.name in tools:
            raise ValueError(f"Duplicate tool name detected: {inst.name}")
        tools[inst.name] = inst
    return tools

# Tool registry - automatically built from tool classes
TOOLS: Dict[str, BaseTool] = _build_tools()

def get_tool_schemas() -> List[Dict[str, Any]]:
    return [tool.schema for tool in TOOLS.values()]
