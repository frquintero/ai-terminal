# AI Terminal - MiniMax M2 Implementation Guide

## Overview

This document serves as a comprehensive starting point for building an AI Terminal using MiniMax M2. It combines AI language model capabilities with shell command execution, tool calling, and interactive terminal operations to create a powerful AI-driven terminal interface.

## Architecture Overview

### Core Components

1. **AI Agent (`agent.py`)**: Main orchestrator that handles conversations and tool execution
2. **Tool System (`tools.py`)**: Modular tools for file operations and shell commands
3. **Configuration (`config.py`)**: Environment and model settings management
4. **Main Interface (`main.py`)**: Interactive CLI for user communication

### Agent Workflow

```
User Input → MiniMax M2 API → Tool Calls → Execute Tools → Feed Results Back → Final Response
```

## MiniMax M2 Integration

### API Configuration

```python
import openai

# Initialize OpenAI-compatible client for MiniMax
client = openai.OpenAI(
    api_key="your_minimax_api_key",
    base_url="https://api.minimax.chat/v1"  # MiniMax API endpoint
)

# Chat completion with tool calling
response = client.chat.completions.create(
    model="MiniMax-Text-01",  # Use appropriate MiniMax model
    messages=messages,
    tools=tool_schemas,
    tool_choice="auto",
    max_tokens=1024,
    temperature=0.7
)
```

### Tool Schema Format

MiniMax supports OpenAI-compatible tool calling:

```python
tool_schema = {
    "type": "function",
    "function": {
        "name": "tool_name",
        "description": "Tool description",
        "parameters": {
            "type": "object",
            "properties": {
                "param_name": {
                    "type": "string",
                    "description": "Parameter description"
                }
            },
            "required": ["param_name"]
        }
    }
}
```

## Tool Implementation

### Base Tool Class

```python
class BaseTool:
    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def description(self) -> str:
        raise NotImplementedError

    @property
    def parameters(self) -> Dict[str, Any]:
        raise NotImplementedError

    def execute(self, **kwargs) -> ToolResult:
        raise NotImplementedError
```

### Essential Tools

#### 1. File Operations

**ReadFileTool:**
- Reads file contents
- Handles encoding and file existence checks
- Returns content or error messages

**WriteFileTool:**
- Creates/overwrites files
- Auto-creates directories
- Handles encoding and permissions

#### 2. Shell Command Tool (Advanced)

**RunCommandTool with Sudo & Interactive Support:**
- Basic command execution
- Sudo privilege escalation
- Interactive mode for password prompts
- Timeout handling

```python
def execute(self, command: str, use_sudo: bool = False, interactive: bool = False) -> ToolResult:
    if use_sudo:
        command = f"sudo {command}"

    if interactive:
        # Run without capturing output - allows user interaction
        result = subprocess.run(command, shell=True, timeout=60)
        return ToolResult(result.returncode == 0, "Command executed successfully (interactive mode)")
    else:
        # Capture output for non-interactive commands
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return ToolResult(result.returncode == 0, result.stdout + result.stderr)
```

## Agent Implementation

### Conversation Management

```python
class MiniAgent:
    def __init__(self, config: Config):
        self.config = config
        self.client = openai.OpenAI(**config.openai_config)
        self.messages = []
        self.max_steps = 10

    def run(self, user_input: str) -> str:
        # Initialize conversation with system prompt
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ]

        for step in range(self.max_steps):
            # Get AI response with tool schemas
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=self.messages,
                tools=get_tool_schemas(),
                tool_choice="auto"
            )

            message = response.choices[0].message

            if not message.tool_calls:
                return message.content  # Final response

            # Process tool calls
            self.messages.append(self._format_message_with_tools(message))

            for tool_call in message.tool_calls:
                tool_result = self._execute_tool(tool_call)
                self.messages.append({
                    "role": "tool",
                    "content": tool_result.content,
                    "tool_call_id": tool_call.id
                })

        return "Maximum steps reached"
```

### System Prompt Design

```python
SYSTEM_PROMPT = """
You are a helpful AI assistant with access to shell commands and file operations.
You can read and write files, and run shell commands including sudo operations.

Available tools:
- read_file: Read file contents
- write_file: Write content to files
- run_command: Execute shell commands (supports sudo and interactive modes)

When using sudo commands:
- For non-interactive commands: use_sudo=true, interactive=false
- For commands needing passwords: use_sudo=true, interactive=true

Be concise but helpful. Use tools when needed to accomplish tasks.
"""
```

## Configuration Management

### Environment Variables

```python
# .env file structure
MINIMAX_M2_API_KEY=your_api_key_here
MINIMAX_MODEL=MiniMax-Text-01
MAX_TOKENS=1024
TEMPERATURE=0.7
```

### Config Class

```python
class Config:
    def __init__(self):
        self.api_key = os.getenv("MINIMAX_M2_API_KEY")
        self.model = os.getenv("MINIMAX_MODEL", "MiniMax-Text-01")
        self.max_tokens = int(os.getenv("MAX_TOKENS", "1024"))
        self.temperature = float(os.getenv("TEMPERATURE", "0.7"))

        if not self.api_key:
            raise ValueError("MINIMAX_M2_API_KEY environment variable required")

        self.openai_config = {
            "api_key": self.api_key,
            "base_url": "https://api.minimax.chat/v1"
        }
```

## Error Handling & Safety

### Tool Execution Safety

```python
def _execute_tool(self, tool_call) -> ToolResult:
    tool_name = tool_call.function.name
    tool_args = json.loads(tool_call.function.arguments)

    if tool_name not in TOOLS:
        return ToolResult(False, "", f"Unknown tool: {tool_name}")

    try:
        return TOOLS[tool_name].execute(**tool_args)
    except Exception as e:
        return ToolResult(False, "", f"Tool execution error: {str(e)}")
```

### Command Timeouts

- Interactive commands: 60 seconds (allows user input time)
- Non-interactive commands: 30 seconds
- Configurable timeouts prevent hanging

### Input Validation

- JSON parsing for tool arguments
- File path validation
- Command sanitization (basic)

## Advanced Features

### Interactive Mode Implementation

The interactive mode is crucial for sudo operations:

```python
if interactive:
    # Don't capture stdout/stderr - let user interact directly
    result = subprocess.run(command, shell=True, timeout=60)
    # User sees prompts and can respond
else:
    # Capture output for programmatic processing
    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
```

### Conversation State Management

- Message history preservation
- Tool call/result integration
- Context maintenance across steps
- Step limits to prevent infinite loops

### Tool Registry

```python
TOOLS = {
    "read_file": ReadFileTool(),
    "write_file": WriteFileTool(),
    "run_command": RunCommandTool(),
}

def get_tool_schemas():
    return [{
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters
        }
    } for tool in TOOLS.values()]
```

## Project Structure

```
ai-terminal/
├── README.md              # Project documentation
├── requirements.txt       # Dependencies
├── .env                   # Environment variables
├── config.py             # Configuration management
├── tools.py              # Tool implementations
├── agent.py              # Main agent logic
├── main.py               # CLI interface
└── tests/                # Test files
    ├── test_tools.py
    ├── test_agent.py
    └── test_sudo.py
```

## Dependencies

```txt
python-dotenv>=1.0.0
openai>=1.0.0
```

## Usage Examples

### Basic File Operations

```
User: Create a hello.py file that prints "Hello from AI!"
Agent: [uses write_file tool]
Final: File created successfully
```

### Shell Commands

```
User: List files in current directory
Agent: [uses run_command tool]
Final: Shows directory listing
```

### Sudo Operations

```
User: Update system packages
Agent: [uses run_command with use_sudo=true, interactive=true]
Final: Package update completed
```

## Testing Strategy

### Unit Tests

```python
def test_read_file_tool():
    tool = ReadFileTool()
    result = tool.execute(file_path="test.txt")
    assert result.success

def test_sudo_tool():
    tool = RunCommandTool()
    # Test non-interactive sudo (if configured)
    result = tool.execute(command="whoami", use_sudo=True, interactive=False)
    assert "root" in result.content
```

### Integration Tests

- End-to-end conversation flows
- Tool calling accuracy
- Error handling scenarios
- Interactive command testing

## Deployment Considerations

### Security

- API key protection
- Command validation
- File operation restrictions
- Sudo usage policies

### Performance

- Model response times
- Tool execution overhead
- Memory usage for conversation history
- Rate limiting

### Scalability

- Multiple agent instances
- Conversation persistence
- Tool extension mechanisms
- API rate limit handling

## Next Steps

1. **Setup Project Structure**: Create directories and basic files
2. **Implement Core Tools**: Start with file operations and basic commands
3. **Add MiniMax Integration**: Configure API connection and tool schemas
4. **Build Agent Logic**: Implement conversation flow and tool calling
5. **Add Interactive Features**: Implement sudo and interactive command support
6. **Testing**: Create comprehensive test suite
7. **Documentation**: Update README and usage examples
8. **Security Review**: Audit for potential vulnerabilities
9. **Performance Optimization**: Optimize response times and resource usage

## Key Insights from Implementation

1. **Interactive vs Non-Interactive**: Critical distinction for sudo operations
2. **Tool Schema Design**: Proper parameter definitions enable accurate tool calling
3. **Error Handling**: Comprehensive error catching prevents agent failures
4. **Conversation Management**: Message history is crucial for context
5. **Timeout Management**: Prevents hanging on long-running commands
6. **Modular Design**: Tool system allows easy extension
7. **API Compatibility**: OpenAI-compatible interface simplifies integration

This implementation provides a solid foundation for building powerful AI-assisted terminal operations with MiniMax M2.
