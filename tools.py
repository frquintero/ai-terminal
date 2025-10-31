from abc import ABC, abstractmethod
import os
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
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
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
        return "Execute a shell command"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Execute a shell command",
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

# Tool registry
TOOLS: Dict[str, BaseTool] = {
    "read_file": ReadFileTool(),
    "write_file": WriteFileTool(),
    "run_command": RunCommandTool(),
    "chat": ChatTool(),
    "process_content": ContentProcessingTool()
}

def get_tool_schemas() -> List[Dict[str, Any]]:
    return [tool.schema for tool in TOOLS.values()]
