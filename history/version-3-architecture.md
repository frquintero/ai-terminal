# AI-Powered Linux Shell Terminal (v3.0 Architecture)

**AI-Terminal** is an intelligent command-line interface that translates natural language user queries into precise shell commands. It solves the problem of complex shell syntax and multi-step workflows by using a **Routerless Dual-Agent Orchestrator** to plan, execute, and narrate system operations.

### Quick Start
```bash
# Set up and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the terminal
python main.py
```

### Debugging & Development
- **Debug a Cycle**: To analyze a specific interaction (bugs, semantic errors), use the debug tool with the cycle ID (visible in the REPL status line):
  ```bash
  python3 debug_cycle.py <cycle_id_prefix>
  ```
  This tool provides a full audit trail of Agent A's intent, Agent B's execution manifest, tool outputs, and database state.

- **Issue Tracking**: This project uses **bd (beads)** for issue tracking.
  - Check work: `bd ready`
  - Create issue: `bd create "Title" -t bug|feature`
  - Update status: `bd update <id> --status in_progress`
  - Close issue: `bd close <id> --reason "Done"`

---

# Version 3 Architecture: Routerless Dual-Agent System

## Overview

The Version 3 architecture represents a shift from a router-based control flow to a **Routerless, Dual-Agent** system. This design separates high-level reasoning ("Intent") from low-level execution ("Manifest"), improving reliability and simplifying the orchestration logic.

## Core Philosophy

1.  **Routerless Entry**: Every user query is processed by **Agent A** first. There is no separate "Router" or "Classifier" step. Agent A implicitly routes by deciding whether to respond directly or propose a plan.
2.  **Separation of Concerns**:
    *   **Agent A (The Planner/Narrator)**: Focuses on *what* the user wants and *why*. Handles conversation and high-level strategy.
    *   **Agent B (The Executor)**: Focuses on *how* to achieve the goal. Handles tool syntax, command flags, and technical implementation.
3.  **Declarative Execution**: Agent B generates a complete **Execution Manifest** (all steps) in one shot, rather than a loop of "think-act-observe".

## Main Components

### 1. Orchestrator (`orchestrator/orchestrator.py`)
The central controller of the application. It manages the lifecycle of a "Cycle" (a single user query resolution).
*   **Responsibilities**:
    *   Session and Cycle management.
    *   Invoking Agent A and interpreting its decision (Direct Response vs. Plan).
    *   Invoking Agent B to generate the Execution Manifest.
    *   Executing the Manifest steps via `ToolExecutor`.
    *   Logging all events to the Memory system.
    *   Rendering the final response to the user.

### 2. Agent Roles
The system uses two distinct agent personas, which can be powered by the same or different LLM models.

*   **Agent A (Intent & Narration)**
    *   **Role**: Product Manager / User Liaison.
    *   **Input**: User query, Chat History.
    *   **Output**:
        *   **Direct Response**: Text for conversational queries.
        *   **Intent**: A high-level JSON object describing the goal (e.g., "Scan the current directory for python files").
    *   **Configuration**: Typically uses a higher temperature for more natural conversation.

*   **Agent B (Execution)**
    *   **Role**: Senior DevOps Engineer.
    *   **Input**: Agent A's "Intent", Tool Definitions (Schemas).
    *   **Output**: **Execution Manifest**. A JSON list of concrete steps (e.g., `run_command` with `ls -la`, `read_file` with specific paths).
    *   **Configuration**: Uses a low temperature (near 0) for precise, deterministic code generation.

### 3. Tool Executor (`tool_executor.py`)
A dedicated component for safely executing the steps defined in the Manifest.
*   **Responsibilities**:
    *   Validating tool names and arguments.
    *   Handling variable substitution (e.g., replacing `$PREVIOUS_OUTPUT` with the actual result of the last step).
    *   Capturing `stdout`, `stderr`, and exit codes.
    *   Formatting outputs for the database.

### 4. Memory System (`memory/api.py`, `memory/schema.py`)
A unified interface for persistent state, backed by SQLite (`logs/orchestrator.db`).
*   **Key Tables**:
    *   `sessions`: Tracks global session metadata.
    *   `task_state`: Stores the "Plan" (Agent A's Intent + Agent B's Manifest).
    *   `step_outputs`: Stores the actual results of every executed step.
    *   `interactions`: Logs raw LLM prompts and responses for debugging and auditing.
    *   `chat_history`: Stores the user-facing conversation log.
    *   `cycle_metrics`, `step_metrics`, `llm_metrics`: Telemetry data.

### 5. LLM Client (`llm_client.py`)
A standardized wrapper for OpenAI-compatible API calls.
*   **Features**:
    *   Automatic retries with exponential backoff.
    *   Role-based logging (tagging calls as 'A' or 'B').
    *   Token usage tracking.

## Information Flow

1.  **User Query**: The user types a command or question into the terminal.
2.  **Cycle Start**: The Orchestrator creates a unique `cycle_id`.
3.  **Agent A (Intent)**:
    *   The Orchestrator sends the query + chat history to Agent A.
    *   **Decision Point**:
        *   *Scenario 1 (Chat)*: Agent A returns a text response. The cycle ends, and the response is shown to the user.
        *   *Scenario 2 (Action)*: Agent A returns an **Intent** JSON (e.g., `{"tool_name": "run_command", "intent": "list files"}`).
4.  **Agent B (Manifest)**:
    *   If an Intent was generated, the Orchestrator sends it to Agent B.
    *   Agent B generates an **Execution Manifest** containing all necessary steps (e.g., `[{"tool": "run_command", "args": {"command": "ls -la"}}]`).
5.  **Persistence**: The Orchestrator saves the Intent and Manifest to the `task_state` table.
6.  **Execution Loop**:
    *   The Orchestrator iterates through the Manifest steps.
    *   **Variable Substitution**: Resolves placeholders like `$PREVIOUS_OUTPUT`.
    *   **Tool Execution**: Calls `ToolExecutor` to run the command.
    *   **Logging**: Saves the result to `step_outputs`.
7.  **Final Response**:
    *   The Orchestrator uses a narration template (provided by Agent B) or calls Agent A again to summarize the results for the user.
8.  **Completion**: The final response is displayed, and the cycle is marked as complete.

## Key Files

*   `main.py`: Entry point. Initializes the environment, config, and REPL loop.
*   `config.py`: Handles environment variables, model selection, and agent-specific settings.
*   `orchestrator/orchestrator.py`: Core logic for the dual-agent flow.
*   `orchestrator/prompts.py`: System prompts defining the personas for Agent A and Agent B.
*   `memory/schema.py`: Database schema definitions.
*   `tools.py`: Definitions of available tools (e.g., `run_command`, `read_file`).
*   `setup.py`: Interactive configuration wizard for creating `.env` files.

## Setup Wizard (`setup.py`)

The `setup.py` script provides an interactive CLI wizard to configure the AI Terminal environment. It simplifies the process of creating a secure `.env` file by guiding the user through:

1.  **Provider Selection**: Choose between supported backends (e.g., MiniMax, Kimi K2).
2.  **API Key Management**: Securely input API keys (masked input) or reuse existing ones.
3.  **Model Configuration**: Set default models and base URLs.
4.  **Parameter Tuning**: Configure global settings like `MAX_TOKENS`, `TEMPERATURE`, and `MAX_STEPS`.
5.  **Connection Testing**: Automatically validates the API connection before saving.

Run it with:
```bash
python setup.py
```

## Configuration (`.env`)

The application is configured via environment variables, typically stored in a `.env` file. These parameters control agent behavior, model selection, and system limits.

### Core Settings
*   `AGENT_TYPE`: Selects the backend provider (`minimax`, `kimi2`, `custom`).
*   `API_KEY` / `BASE_URL` / `MODEL`: Provider-specific credentials (e.g., `MINIMAX_M2_API_KEY`, `KIMI_2_MODEL`).

### Model Behavior
*   `TEMPERATURE`: Global creativity setting (0.0-2.0).
*   `AGENT_A_TEMPERATURE`: Overrides global temperature for the Planner/Narrator (usually higher for creativity).
*   `AGENT_B_TEMPERATURE`: Overrides global temperature for the Executor (usually near 0 for precision).
*   `MAX_TOKENS`: Maximum tokens per response.
*   `HIDE_THINKING`: Whether to suppress `<think>` blocks from the UI (`true`/`false`).

### Execution Limits
*   `MAX_STEPS`: Maximum number of tool calls allowed in a single cycle.
*   `SHOW_RAW_OUTPUT`: Whether to display raw tool output in the REPL (`true`/`false`).
*   `SAVE_LLM_TRACES`: Whether to log full prompts/responses to the database (`true`/`false`).

These settings are loaded by `config.py` at startup and can be overridden by CLI flags (e.g., `--temperature 0.1`).

## Design Principles

### 1. In AI We Trust
We design our system to leverage the reasoning capabilities of Large Language Models rather than constraining them with brittle heuristics. We provide agents with clear personas, robust tools, and full context, trusting them to make intelligent decisions. We avoid "router" classifiers or rigid state machines in favor of Agent A's natural language understanding to drive control flow.

### 2. Go Upstream
When bugs or limitations arise, we solve them at the source. We do not patch symptoms or add special-case logic to handle edge cases in downstream components. Instead, we improve the system prompts, refine tool schemas, or enhance the architecture itself. If an agent struggles to use a tool, we fix the tool's interface, not the agent's output.

### 3. We Hate Regex
Parsing natural language or semi-structured text with Regular Expressions is a last resort. We architect our agents to communicate in strict, structured formats (JSON) that can be reliably parsed and validated. Agent B's "Execution Manifest" and the `OutputParser`'s typed handling are prime examples of preferring deterministic data structures over pattern matching.

### 4. Always Test for Regressions
Reliability is paramount. Every architectural change or prompt adjustment must be verified against our comprehensive test suite. We maintain a rigorous set of integration and end-to-end tests (`tests/`) to ensure that improvements in one area do not degrade performance or accuracy in another. We treat our test suite as the ultimate source of truth for system stability.
