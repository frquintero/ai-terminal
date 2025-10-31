from abc import ABC, abstractmethod
import os
import subprocess
import sys
import shlex
from typing import Dict, Any, List
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
    def __init__(self):
        self.shell = ShellIntegration()

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return "Execute a non-interactive shell command (do not use for interactive programs like vim, nano, top, etc.)"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Execute a non-interactive shell command (will timeout if used with interactive programs)",
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
            
            # Check if any command name is interactive
            is_interactive = False
            interactive_cmd = None
            
            if cmd_names:
                # Check first command
                if cmd_names[0] in InteractiveCommandTool.INTERACTIVE_COMMANDS:
                    is_interactive = True
                    interactive_cmd = cmd_names[0]
                # Check sudo/doas followed by interactive command
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
                return f"Error: '{interactive_cmd}' is an interactive command. Use run_interactive tool instead to avoid timeout."
            
            return self.shell.run_command(command)
        except Exception as e:
            return f"Error executing command: {str(e)}"

class ChatTool(BaseTool):
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

# Tool registry
TOOLS: Dict[str, BaseTool] = {
    "read_file": ReadFileTool(),
    "write_file": WriteFileTool(),
    "run_command": RunCommandTool(),
    "run_interactive": InteractiveCommandTool(),
    "chat": ChatTool(),
    "process_content": ContentProcessingTool()
}

def get_tool_schemas() -> List[Dict[str, Any]]:
    return [tool.schema for tool in TOOLS.values()]
