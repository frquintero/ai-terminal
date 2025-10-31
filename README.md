# AI-Powered Linux Shell Terminal

This project implements an AI-powered Linux shell terminal using MiniMax M2 AI. It combines natural language processing, shell command execution, and tool-based operations to create an intelligent CLI interface.

## Features

- **AI-First Processing**: All user inputs go through MiniMax M2 AI for intelligent interpretation
- **Multi-Step Task Execution**: AI can break down complex requests into sequences of tool calls
- **Tool-Based Execution**: AI translates natural language to shell commands and executes via shell integration
- **Chat Tool**: Handle pure conversational responses when no command execution is needed
- **Content Processing**: Combine file operations, shell commands, and AI generation for complex workflows
- **Shell Integration**: Wrap around bash/zsh for efficient command execution and output capture

## Installation

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your MiniMax M2 API key
4. Run the terminal: `python main.py`

## Usage

- Enter natural language commands
- The AI will interpret and execute them appropriately
- Supports file operations, shell commands, and conversation

## Development

See `plan.md` for detailed implementation plan and `starting_point.md` for technical guide.

## License

[Add license information]
