# AI-Powered Linux Shell Terminal

**Version:** 1.2

This project implements an AI-powered Linux shell terminal using MiniMax M2 AI. It combines natural language processing, shell command execution, and tool-based operations to create an intelligent CLI interface.

## Features

- **AI-First Processing**: All user inputs go through MiniMax M2 AI for intelligent interpretation
- **Multi-Step Task Execution**: AI can break down complex requests into sequences of tool calls
- **Automatic Tool Discovery**: Tools are auto-registered from class definitions - add/remove tools without manual registry updates
- **Intelligent Output Display**: Clean agent summaries by default, with optional raw output mode for debugging
- **Tool-Based Execution**: AI translates natural language to shell commands and executes via shell integration
- **Content Processing**: Combine file operations, shell commands, and AI generation for complex workflows
- **Shell Integration**: Wrap around bash/zsh for efficient command execution and output capture
- **Namespace Isolation (Optional)**: Run commands inside isolated Linux namespace with deterministic rootfs for reproducible execution

## Available Agent Tools

The system automatically discovers and registers tools:
- `read_file` - Read file contents
- `write_file` - Create or overwrite files
- `run_command` - Execute non-interactive shell commands
- `run_sudo_command` - Execute commands with sudo privileges
- `run_interactive` - Run interactive commands (vim, nano, top, etc.)
- `run_python_sandbox` - Execute Python code in isolated, resource-limited sandbox with data science libraries (pandas, numpy, matplotlib). Auto-saves plots.
- `get_context` - Query agent's state (working directory, recent writes)
- `wikipedia_search` - Search Wikipedia for information
- `process_content` - Analyze and process text content

## Installation

1. Clone the repository
2. Create virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and configure:
   ```bash
   MINIMAX_M2_API_KEY=your_api_key_here
   MINIMAX_MODEL=MiniMax-M2
   SHOW_RAW_OUTPUT=false  # Set to true for debugging
   ```
5. (Optional) Set up Python sandbox environment:
   ```bash
   ./setup_sandbox.sh
   ```
   Then add to `.env`:
   ```bash
   SANDBOX_PYTHON=./sandbox_venv/bin/python
   ```
6. Run the terminal: `python main.py`

## Configuration

Key settings in `.env`:
- `SHOW_RAW_OUTPUT` (default: `false`) - Show raw command outputs. Set to `true` for debugging or verification workflows.
- `RAW_OUTPUT_MAX_CHARS` (default: `4000`) - Maximum characters to display when raw output is enabled.
- `HIDE_THINKING` (default: `true`) - Hide AI reasoning in responses.
- `MAX_STEPS` (default: `15`) - Maximum tool execution steps per request.

### Python Sandbox Configuration
- `SANDBOX_PATH` (default: `./sandbox_runs`) - Directory for sandbox execution environments
- `SANDBOX_PYTHON` (optional) - Path to dedicated sandbox Python interpreter with pre-installed data science libraries
- `SANDBOX_TIMEOUT` (default: `30`) - Default timeout in seconds for sandbox execution
- `SANDBOX_MAX_CPU_SEC` (default: `20`) - Maximum CPU time in seconds
- `SANDBOX_MAX_MEM_MB` (default: `1024`) - Maximum memory in MB
- `SANDBOX_MAX_FSIZE_MB` (default: `50`) - Maximum file size in MB
- `SANDBOX_DISABLE_NETWORK` (default: `1`) - Disable network access in sandbox

### Namespace Isolation (Optional)
Deterministic rootfs-based isolation for reproducible command execution:
- `SANDBOX_ENABLE_ISOLATION` (default: `0`) - Enable namespace isolation (requires Linux + bubblewrap)
- `SANDBOX_ROOTFS_SHA256` (optional) - Specific rootfs image SHA256 to use

**To enable:**
1. Build rootfs (one-time): `sudo ./build_rootfs.sh`
2. Run agent with isolation: `SANDBOX_ENABLE_ISOLATION=1 python main.py`

See [history/NAMESPACE_ISOLATION.md](history/NAMESPACE_ISOLATION.md) for full documentation.

## Usage

- Enter natural language commands
- The AI will interpret and execute them appropriately
- Supports file operations, shell commands, Wikipedia searches, and conversation
- By default, see clean AI summaries; enable raw output for detailed command results

## Development

See `plan.md` for detailed implementation plan and `starting_point.md` for technical guide.

## License

[Add license information]
