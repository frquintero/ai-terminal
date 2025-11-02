# Agent Guidelines for Intelligent Terminal

## Build/Lint/Test Commands
- **Run all tests**: `python -m unittest discover tests/`
- **Run single test**: `python -m unittest tests.test_tools.TestFileTools.test_read_file_success`
- **Install dependencies**: `pip install -r requirements.txt`
- **Run terminal**: `python main.py`

## Architecture & Codebase Structure
- **Main components**: agent.py (AI agent), tools.py (modular tools), shell_integration.py (shell ops), config.py (config)
- **Tool system**: Abstract BaseTool class with ReadFileTool, WriteFileTool, RunCommandTool, ChatTool, ContentProcessingTool
- **AI integration**: MiniMax M2 via OpenAI-compatible API with tool calling and conversation management
- **Shell integration**: pexpect-based persistent shell sessions supporting bash/zsh with sudo and interactive commands

## Code Style Guidelines
- **Imports**: Standard library first, then third-party, then local imports
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Types**: Use typing module for type hints on all function parameters and return values
- **Error handling**: try/except blocks with specific exception types, return error strings from tools
- **Formatting**: 4-space indentation, single quotes for strings, f-strings for formatting
- **File operations**: Use absolute paths, handle encoding explicitly (utf-8), check parent directories
- **Docstrings**: Use triple quotes for multi-line docstrings describing purpose and parameters
