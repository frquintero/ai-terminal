# AI-Powered Linux Shell Terminal

**Version:** 1.3

## Overview

This is an **AI-powered Linux terminal** built with MiniMax M2 (or Kimi-2/custom LLM). Here's the structure:

**Purpose**: Intelligent CLI combining natural language processing with shell execution—users type requests in plain English, the AI interprets and executes via tools.

**Architecture**:
- **agent.py**: ReAct loop engine (max 15 steps) with tool calling, history trimming, session state tracking, and multi-step planning
- **tools.py**: Auto-registered tool suite (run/read/write commands, filesystem snapshotting, Python sandbox with pandas/numpy/matplotlib, context queries, history_sql memory access, HTTP client)
- **config.py**: Multi-backend support (MiniMax/Kimi-2/custom OpenAI-compatible APIs) with env-based configuration
- **shell_integration.py**: Persistent bash/zsh wrapper, working directory isolation (`ai-terminal-wd/`)
- **db_logger.py**: SQLite session logging with telemetry
- **filesystem_context.py**: Persists shell-derived cwd snapshots plus read/write events to SQLite + JSONL so agents always know the real workspace layout

**Key Features**:
- Shell-first philosophy (prefer `awk/sed/jq` over Python for text/math)
- Resource-limited Python sandbox with write protection, network isolation
- Optional namespace isolation via bubblewrap (reproducible rootfs)
- Persistent filesystem awareness (auto-logged cwd, recent file events, absolute/relative path hints surfaced via the `filesystem_snapshot` tool and prompt injections)
- Lean context tracking (10-call live history + history_sql-first permanent recall, recent errors, session stats)
- Structured history DB access via `history_schema` + `history_sql` so the agent can inspect tables, then run parameterized SELECT/INSERT/UPDATE statements (DELETE/DROP blocked) for precise recall and memory writing
- Smart HTTP tooling: templated requests, jq selectors, TLS certificate telemetry, session-aware curl profiles
- Raw output mode toggle for debugging

**Extended Memory & Filesystem Context:** High-signal events stream into JSONL (`logs/events/<session>.jsonl`) and are mirrored into `logs/history/history.db`, powering the `history_sql` tool for authoritative SELECT/INSERT/UPDATE access. In parallel, shell executions and file reads/writes are captured by `filesystem_context.py` (SQLite + JSONL) so agents always know the true cwd, sandbox roots, and recent file mutations without rerunning `pwd/ls`. See `docs/HISTORY_TOOL.md` and `filesystem_context.py` for implementation notes.

**State**: v1.3, 88 closed beads (all issues completed), production-ready with comprehensive docs and test coverage.

---

This project implements an AI-powered Linux shell terminal using MiniMax M2 AI. It combines natural language processing, shell command execution, and tool-based operations to create an intelligent CLI interface.

## 🎯 Vibe Coded with Amp

This project was built using [Amp](https://ampcode.com) - Sourcegraph's AI coding agent. Amp combines the power of Claude 3.5 Sonnet for execution with GPT-5 (Oracle) for expert planning and review. The entire v1.3 enhanced context system, including the comprehensive `get_context` tool with session tracking, tool history, and intelligent prompt optimization, was designed and implemented through iterative collaboration with Amp's dual-model architecture. Amp's ability to consult the Oracle for architectural decisions, maintain context across complex implementations, and execute with precision made this level of sophisticated agent-to-agent development possible.

**Development highlights:**
- Oracle-reviewed architecture (3+ consultations for design validation)
- Comprehensive session state tracking (20 tool calls, 3 errors, bounded memory)
- Zero-regression implementation (backward compatible, all tests passing)
- Prompt engineering with explicit usage triggers and shell-first philosophy
- 18 feature commits across 8 files (+1,486 lines) shipped in a single session

Learn more about Amp at [ampcode.com](https://ampcode.com).

## Features

- **AI-First Processing**: All user inputs go through MiniMax M2 AI for intelligent interpretation
- **Multi-Step Task Execution**: AI can break down complex requests into sequences of tool calls
- **Automatic Tool Discovery**: Tools are auto-registered from class definitions - add/remove tools without manual registry updates
- **Intelligent Output Display**: Clean agent summaries by default, with optional raw output mode for debugging
- **Tool-Based Execution**: AI translates natural language to shell commands and executes via shell integration
- **Content Processing**: Combine file operations, shell commands, and AI generation for complex workflows
- **Shell Integration**: Wrap around bash/zsh for efficient command execution and output capture
- **Namespace Isolation (Optional)**: Run commands inside isolated Linux namespace with deterministic rootfs for reproducible execution
- **Traceable AI Calls**: Every OpenAI request is tagged with a short trace ID and stored under `logs/openai_traces/<trace>.json` for debugging
- **Event-Driven Memory**: High-signal events (tool calls/results/errors) stream into `logs/events/<session>.jsonl`, letting the agent recall past work without resending the entire conversation

## Available Agent Tools

The system currently auto-registers these tools (direct mirror of `tools.py` and `get_context.available_tools`):
- `run_command` – Execute non-interactive shell commands (ls, grep, pipelines, etc.)
- `run_interactive` – Launch TTY programs such as vim, nano, top
- `run_python_sandbox` – Run Python snippets inside the resource-limited sandbox for data/plotting tasks
- `read_file` – Output a file’s contents
- `write_file` – Create or overwrite files in the working directory
- `get_context` – Return session metadata, tool history, and recent errors for debugging
- `filesystem_snapshot` – Fetch the latest persisted cwd snapshot plus recent read/write telemetry so path decisions are accurate without extra shell probes
- `http_request` – Structured curl wrapper with profiles, session persistence, templating variables, jq JSON selectors, certificate-chain reporting, retries, metrics, and diagnostics (preferred for any HTTP/API work)
- `history_schema` – List history tables or describe specific columns so you know the schema before querying
- `history_sql` – Run parameterized SELECT/INSERT/UPDATE statements against `logs/history/history.db` (DELETE/DROP blocked) to retrieve or append durable memories with precise filters

Detailed knobs for `http_request` live in `docs/HTTP_REQUEST.md`.

## Workflow & Issue Tracking

This repo uses **bd (beads)** for all work tracking. Never add Markdown TODO lists—open or update beads instead:

```bash
bd ready --json                  # see unblocked work
bd create "Title" -t feature -p 1 --json
bd update bd-123 --status in_progress --json
bd close bd-123 --reason "Done" --json
```

AI-generated plans/design docs must live under `history/` (e.g., `history/PLAN.md`). Keep the repository root focused on durable assets.

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
- `USE_EVENT_MEMORY` (default: `true`) - Enable the event-driven memory builder (JSONL logs + selective prompt injection).
- `EVENT_LOG_RETENTION_DAYS` (default: `7`) - Auto-delete event logs older than N days.
- `EVENT_MEMORY_MAX_EVENTS` / `EVENT_MEMORY_MAX_CHARS` - Upper bounds for the Agent Memory block sent to the LLM.
- `EVENT_MEMORY_ARTIFACT_THRESHOLD` (default: `8192`) - Tool outputs larger than this many bytes are persisted as artifacts under `ai-terminal-wd/artifacts/`.
- `SESSION_TOOL_HISTORY_LIMIT` (default: `10`) - Live `tool_history` length. Lower values reduce prompt cost; rely on `history_sql` (with concise SELECTs) for older context.

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
1. Build rootfs (one-time, ~6 min, ~234MB):
   ```bash
   sudo ./build_rootfs.sh
   ```
   This caches the rootfs in `~/.cache/agent_sandbox/images/` (auto-detects your user even with sudo)
2. Run agent with isolation:
   ```bash
   SANDBOX_ENABLE_ISOLATION=1 python main.py
   ```

See [history/NAMESPACE_ISOLATION.md](history/NAMESPACE_ISOLATION.md) for full documentation.

## Usage

- Enter natural language commands
- The AI will interpret and execute them appropriately
- Supports file operations, shell commands, Wikipedia searches, and conversation
- By default, see clean AI summaries; enable raw output for detailed command results
- Need deeper debugging guidance? See [docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md) for trace logs, session telemetry, and beads workflow tips.

## Development

See `plan.md` for detailed implementation plan and `starting_point.md` for technical guide.

## License

[Add license information]
