# AI-Powered Linux Shell Terminal (v3.0 Architecture)

**AI-Terminal** is an intelligent command-line interface that translates natural language user queries into precise shell commands. It solves the problem of complex shell syntax and multi-step workflows by using a **Routerless Dual-Agent Orchestrator** to plan, execute, and narrate system operations.

### Detailed Process Flow

1. **REPL & Entry Point** (`main.py`)
   - User Input: Loop waits for `input()`.
   - Orchestrator Call: Passed to `orchestrator.handle_query(user_input)`.

2. **Orchestrator & Agent A** (`orchestrator.py`)
   - Initialization: Creates `cycle_id`, logs start.
   - Agent A (Planner):
     - Prompt built with `AGENT_A_SYSTEM_PROMPT`.
     - Goal: Analyze query & history to decide strategy.
     - Decision (Tool Call): Must call one of:
       - `respond_to_user(response)`: For simple questions/chat.
       - `delegate_to_agent_b(intent, success_criteria)`: For system execution tasks.

3. **Agent B Execution Loop** (If Delegated)
   - If delegated, orchestrator starts Agent B (Executor) loop:
     - Setup: Agent B initialized with intent & success_criteria from Agent A.
     - ReAct Loop: `while` loop (max 15 steps):
       1. Think: Agent B (LLM) called with current history.
       2. Tool Call: Agent B calls native tool (e.g., `run_command`, `read_file`).
       3. Execute: ToolExecutor runs command on system.
       4. Observation: Tool output (`stdout`/`stderr`) fed back as "tool" role message.
       5. Repeat: Analyzes result vs success_criteria, decides next step.
     - Completion: When satisfied, stops calling tools.
     - Final Narration: Orchestrator makes one final, tool-free call to Agent B for structured JSON response with final summary & output segments.


## Memory System

1. **FTS5 Semantic Search** (`memory/schema.py`)
SQLite FTS5 virtual tables (synced via triggers) enable fast natural-language search over history:
- `intention_cache_fts`: Successful query-to-tool mappings.
- `step_outputs_fts`: Actual tool outputs (e.g., "grep" results, errors).
- `chat_history_fts`: All past conversations.

2. **The search_db Tool** (`tools.py`)
Exposes memory via SearchDBTool (lines 663-932):
- **Name**: `search_db`
- **Description**: "Search institutional memory (chat history, tool executions, LLM logs) via FTS5."
- **Function**: Allows Agent to query past experiences. For example, an agent can query the `step_outputs` table for a specific error message like 'connection refused' to see successful past solutions.

3. **Memory API** (`memory/api.py`)
Memory class provides search methods:
- `search_chat_history`: Recall user instructions/context.
- `search_step_outputs`: Find technical solutions/command patterns.
- `search_interactions`: Analyze past reasoning.

Database acts as active Long-Term Memory layer. Indexes every interaction/result, enabling Agent to:
- Recall correct tool use from past successes (`intention_cache`).
- Retrieve old code snippets/file contents (`step_outputs`).
- Contextualize problems against history.

This turns a simple debug log into a growing knowledge base.

## Context & Prompts

In this architecture, agents are stateless entities. Continuity between the user and the AI terminal is maintained solely by injecting past interactions into the "Context Window" (the total prompt sent to the LLM) for each request. There is no hidden internal memory inside the model itself; it only knows what is presented in the current prompt.

### Prompt Structure

Every prompt consists of two main parts:

1.  **System Prompt (Principles & Behavior)**:
    *   Defines the **Persona** (e.g., "You are Agent A...").
    *   Sets **Rules** (e.g., "Do NOT output XML").
    *   This part remains static or semantically stable across calls.

2.  **User Message (History & Tracking)**:
    *   Generated dynamically for each cycle.
    *   Contains the **Variable Context**, such as:
        *   Recent Chat History (User query + Agent response).
        *   Current Intent/Task.
    *   This allows the stateless model to "see" the past and maintain conversational continuity.

### Agent B's Loopy Context

Agent B (the Executor) operates in a ReAct loop (`orchestrator.py`), and its context window is managed dynamically to simulate state:

*   **Seed**: It starts with Agent A's plan injected into its User Message.
*   **Rolling History**: As Agent B executes tools, the "conversation" grows:
    *   `Assistant`: "I need to run `ls`."
    *   `Tool`: (Output of `ls` injected by Orchestrator).
    *   `Assistant`: "Now I will read `file.txt`."
*   This **Loop History** is injected into the prompt at every step, allowing Agent B to "remember" its own previous actions and their results, despite being stateless.

### Quick Start
To get started, set up a virtual environment, install the dependencies listed in `requirements.txt`, and run the `main.py` script.

### Debugging & Development
- **Debug a Cycle**: Developers can inspect specific interaction cycles using the `debug_cycle.py` utility with a cycle ID (visible in the REPL status line).
  
- **Issue Tracking**: This project uses **bd (beads)** for issue tracking.
  - Check work: `bd ready`
  - Create issue: `bd create "Title" -t bug|feature`
  - Update status: `bd update <id> --status in_progress`
  - Close issue: `bd close <id> --reason "Done"`

- **Database Management**: To reset the system state, the `memory.purge_db` module can be executed to clear all sessions and logs while preserving the schema.

---

# Version 3 Architecture: Routerless Dual-Agent System

## Overview

The Version 3 architecture represents a shift from a router-based control flow to a **Routerless, Dual-Agent** system powered by **Native Tool Calling**. This design separates high-level reasoning ("Intent") from low-level execution ("Action"), improving reliability and simplifying the orchestration logic.

## Core Philosophy

1.  **Routerless Entry**: Every user query is processed by **Agent A** first. There is no separate "Router" or "Classifier" step. Agent A implicitly routes by choosing the appropriate tool: `delegate_to_agent_b` for tasks or `respond_to_user` for chat.
2.  **Native Tool Calling**: We leverage the native function-calling capabilities of modern LLMs (like GPT-4, Kimi k1.5, MiniMax) instead of relying on fragile JSON parsing from text. This ensures structured, deterministic outputs.
3.  **Separation of Concerns**:
    *   **Agent A (The Planner/Narrator)**: Focuses on *what* the user wants and *why*. Handles conversation and high-level strategy.
    *   **Agent B (The Executor)**: Focuses on *how* to achieve the goal. Handles tool syntax, command flags, and technical implementation in a **ReAct loop**.
4.  **ReAct Execution Loop**: Agent B operates in a dynamic loop, executing tools and observing outputs step-by-step, allowing it to adapt to errors or unexpected command results.

## Main Components

### 1. Orchestrator (`orchestrator/orchestrator.py`)
The central controller of the application. It manages the lifecycle of a "Cycle" (a single user query resolution).
*   **Responsibilities**:
    *   Session and Cycle management.
    *   Invoking Agent A and routing based on the tool called (`delegate_to_agent_b` vs `respond_to_user`).
    *   Invoking Agent B to execute the plan in a tool-use loop.
    *   Logging all events to the Memory system.
    *   Rendering the final response to the user.

### 2. Agent Roles
The system uses two distinct agent personas, which can be powered by the same or different LLM models.

*   **Agent A (Intent & Narration)**
    *   **Role**: Product Manager / User Liaison.
    *   **Input**: User query, Chat History, System Context (OS, CWD, Time).
    *   **Tools**:
        *   `delegate_to_agent_b(intent, success_criteria)`: Used for tasks requiring system access.
        *   `respond_to_user(response)`: Used for direct conversational answers.
    *   **Configuration**: Uses a higher temperature for more natural conversation.

*   **Agent B (Execution)**
    *   **Role**: Senior DevOps Engineer.
    *   **Input**: Agent A's "Intent", "Success Criteria", and available system tools.
    *   **Tools**: Native system tools (`run_command`, `read_file`, `write_file`, etc.).
    *   **Execution**: Operates in a loop (Think -> Tool Call -> Observation -> Think) until the intent is satisfied.
    *   **Configuration**: Uses a low temperature (near 0) for precise, deterministic code generation.

### 3. Tool Executor (`tool_executor.py`)
A dedicated component for safely executing the steps defined by Agent B.
*   **Responsibilities**:
    *   Validating tool names and arguments.
    *   Executes native function calls from the LLM.
    *   Capturing `stdout`, `stderr`, and exit codes.
    *   Formatting outputs for the database.

#### PTY-Backed Interactive Sessions

Version 3 adds a PTY-backed execution path for commands that expect live dialogue (`man`, pagers, password prompts, repls). `run_interactive` (see `tools.py`) now launches an `InteractiveSession` powered by `pexpect`, which streams output incrementally, detects prompts with regex patterns, and keeps a `session_id` so the Tool Executor and orchestrator can resume the same conversation. The orchestrator forwards those structured prompt events directly to Agent B, allowing it to decide when to send keystrokes, exit, or continue piping additional commands without involving Agent A. The command parser also understands env overrides such as `MANPAGER=cat`, ensuring non-interactive variants continue to flow through the standard `run_command` path. This tighter integration eliminates TTY deadlocks and gives users real-time feedback during complex interactive workflows.

### 4. Memory System (`memory/api.py`, `memory/schema.py`)
A unified interface for persistent state, backed by SQLite (`logs/orchestrator.db`).
*   **Key Tables**:
    *   `sessions`: Tracks global session metadata.
    *   `task_state`: Stores the "Plan" (Agent A's Intent).
    *   `step_outputs`: Stores the actual results of every executed step.
    *   `interactions`: Logs raw LLM prompts and responses for debugging and auditing.
    *   `chat_history`: Stores the user-facing conversation log.
    *   `cycle_metrics`, `step_metrics`, `llm_metrics`: Telemetry data.

### 5. LLM Client (`llm_client.py`)
A standardized wrapper for OpenAI-compatible API calls.
*   **Features**:
    *   Native support for `tools` and `tool_calls`.
    *   Automatic retries with exponential backoff.
    *   Role-based logging (tagging calls as 'A' or 'B').
    *   Token usage tracking.

### 6. User Interface (`ui_formatter.py`)
Handles the rendering of the terminal interface.
*   **Features**:
    *   Dynamic prompt with user, host, and current working directory.
    *   Rich Markdown rendering for AI responses (bold, tables, code blocks).
    *   Live status updates during execution (Planning -> Executing -> Responding).
    *   Collapsible tool output panels.

## Information Flow

1.  **User Query**: The user types a command or question into the terminal.
2.  **Cycle Start**: The Orchestrator creates a unique `cycle_id`.
3.  **Agent A (Intent)**:
    *   The Orchestrator calls Agent A with the query and history.
    *   **Decision Point (Native Tool Call)**:
        *   *Scenario 1 (Chat)*: Agent A calls `respond_to_user`. The cycle ends, and the text is shown.
        *   *Scenario 2 (Action)*: Agent A calls `delegate_to_agent_b` with an `intent` and `success_criteria`.
4.  **Agent B (Execution Loop)**:
    *   If delegated, the Orchestrator starts the Agent B loop.
    *   **Loop**:
        *   Agent B analyzes the intent and calls a tool (e.g., `run_command`).
        *   `ToolExecutor` runs the tool and returns the output.
        *   Agent B observes the output and decides the next step.
    *   **Completion**: Agent B provides a final response summarizing the actions.
5.  **Final Response**:
    *   The final response is displayed to the user with full Markdown formatting.
6.  **Persistence**: All steps, tool outputs, and metrics are saved to the database.

## Key Files

*   `main.py`: Entry point. Initializes the environment, config, and REPL loop.
*   `config.py`: Handles environment variables, model selection, and agent-specific settings.
*   `orchestrator/orchestrator.py`: Core logic for the dual-agent flow and loop management.
*   `orchestrator/prompts.py`: System prompts and tool definitions for Agent A and Agent B.
*   `memory/schema.py`: Database schema definitions.
*   `tools.py`: Definitions of available tools (e.g., `run_command`, `read_file`).
*   `ui_formatter.py`: UI rendering logic using `rich`.

## Configuration (`.env`)

The application is configured via environment variables, typically stored in a `.env` file.

### Core Settings
*   `AGENT_TYPE`: Selects the backend provider (`minimax`, `kimi2`, `custom`).
*   `API_KEY` / `BASE_URL` / `MODEL`: Provider-specific credentials.

### Model Behavior
*   `TEMPERATURE`: Global creativity setting (0.0-2.0).
*   `AGENT_A_TEMPERATURE`: Overrides global temperature for the Planner/Narrator.
*   `AGENT_B_TEMPERATURE`: Overrides global temperature for the Executor.
*   `MAX_TOKENS`: Maximum tokens per response.

### Execution Limits
*   `MAX_STEPS`: Maximum number of tool calls allowed in a single cycle.
*   `SHOW_RAW_OUTPUT`: Whether to display raw tool output in the REPL (`true`/`false`).
*   `SAVE_LLM_TRACES`: Whether to log full prompts/responses to the database (`true`/`false`).

## Design Principles

### 1. In AI We Trust
We design our system to leverage the reasoning capabilities of Large Language Models rather than constraining them with brittle heuristics. We provide agents with clear personas, robust tools, and full context, trusting them to make intelligent decisions.

### 2. Go Upstream
When bugs or limitations arise, we solve them at the source. We do not patch symptoms or add special-case logic to handle edge cases in downstream components. Instead, we improve the system prompts, refine tool schemas, or enhance the architecture itself.

### 3. We Hate Regex (Structured Output)
Parsing natural language or semi-structured text with Regular Expressions is a last resort. We architect our agents to communicate in strict, structured formats (JSON via Native Tool Calling) that can be reliably parsed and validated.

### 4. Always Test for Regressions
Reliability is paramount. Every architectural change or prompt adjustment must be verified against our comprehensive test suite. We maintain a rigorous set of integration and end-to-end tests (`tests/`) to ensure that improvements in one area do not degrade performance or accuracy in another.

### Engineering Principle
Prefer piping commands together instead of multiple separate tool calls. Agent B should default to composing rich shell pipelines (e.g., `awk ... | sort | uniq -c | head`) so each execution step captures the full data flow, reserving multi-command sequences only for cases where a single pipeline cannot express the intent. This keeps the system instructions aligned with the Agent B prompt and reinforces our emphasis on efficient, atomic tool usage.
