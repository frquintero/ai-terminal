# AI-Powered Linux Shell Terminal — v3.0

**Version:** 3.0 (Routerless Dual-Agent Orchestrator)

## Overview

**AI-Terminal** is an intelligent command-line interface that translates natural language user queries into precise shell commands. It solves the problem of complex shell syntax and multi-step workflows by using a **Routerless Dual-Agent Orchestrator** to plan, execute, and narrate system operations.

- **Agent A (Planner / Narrator / Chat):** First hop for every request. Emits either a direct response or a structured plan with `steps[]` + `narration_template`, then renders the final narration after execution.
- **Agent B (Command Engineer):** Called per step to generate precise shell commands (or tool arguments for non-shell tools) plus an `output_format` that explains how to interpret stdout.

**Core Philosophy**:
- **In AI We Trust**: Minimal guardrails, full system access
- **Shell-First**: Favor single, precise shell commands; multi-step plans are opt-in
- **Speed Through Intelligence**: On-device classifier + cache keep literal shell commands under ~500 ms without sacrificing narration quality

---

## Architecture Overview

### Routerless Dual-Agent System

The Version 3 architecture represents a shift from a router-based control flow to a **Routerless, Dual-Agent** system powered by **Native Tool Calling**. This design separates high-level reasoning ("Intent") from low-level execution ("Action"), improving reliability and simplifying the orchestration logic.

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
       - `respond_to_user(segments, policy_contract, policy_summary)`: For simple questions/chat or final status updates. Returns structured segments plus the enforced policy verdicts.
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
     - Completion: When satisfied, Agent B must call the real `respond_to_user` tool with the final segments + policy contract. No narrator fallback exists; the call itself becomes the user-facing response.

### Memory System

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

### Dual-Role LLM System

The system uses two distinct agent personas, which can be powered by the same or different LLM models.

*   **Agent A (Intent & Narration)**
    *   **Role**: Product Manager / User Liaison.
    *   **Input**: User query, Chat History, System Context (OS, CWD, Time).
    *   **Tools**:
        *   `delegate_to_agent_b(intent, success_criteria, todos)`: Used for tasks requiring system access, with a structured TODO list (including descriptions, success criteria, and optional subtasks) to enforce execution boundaries and prevent scope creep.
        *   `respond_to_user(segments, policy_contract, policy_summary)`: Used for direct conversational answers. Returns structured segments plus the deterministic policy verdict so downstream logging stays factual.
    *   **Configuration**: Uses a higher temperature for more natural conversation.
    *   **SQLite3 Guidance**: Explicitly directs TODOs to use proper SQLite3 patterns (`-batch`, inline SQL, piped stdin) to keep commands in the non-interactive path.

*   **Agent B (Execution)**
    *   **Role**: Senior DevOps Engineer.
    *   **Input**: Agent A's "Intent", "Success Criteria", and structured TODO list.
    *   **Tools**: Native system tools (`run_command`, `read_file`, `write_file`, etc.) plus the `respond_to_user` function tool for final user-facing summaries.
    *   **Execution**: Operates in a loop (Think -> Tool Call -> Observation -> Think) until the intent is satisfied, adhering strictly to the TODO list for plan fidelity and resource efficiency.
    *   **Configuration**: Uses a low temperature (near 0) for precise, deterministic code generation.
    *   **SQLite3 Guidance**: Always includes `-batch` or inline SQL (or feeds stdin) for SQLite3 commands to ensure they exit immediately; otherwise switches to `run_interactive`.

### Interactive Sessions (PTY-backed)

For pagers, REPLs, or TUI apps that cannot be coerced into plain stdout, Agent B uses `run_interactive`. The tool spins up a PTY-backed session (powered by `pexpect`), streams output in real time, and emits structured JSON describing each prompt (`status`, `session_id`, `events`, suggested actions). Agent B reads that JSON in the next turn and decides whether to send input (`run_interactive(session_id=..., input_text='q\\n')`), continue reading, or abort—keeping Agent A out of the loop while still honoring the routerless design.

### Command Parser (`command_parser.py`)

A robust shell command analysis system that safely determines whether commands are interactive or non-interactive using a deterministic, policy-driven approach.
*   **Features**:
    *   **Shell Lexer**: Tokenizes shell syntax including quoting, operators, line continuations, and heredocs.
    *   **AST Parser**: Builds abstract syntax trees for commands, understanding pipelines, redirections, and control structures.
    *   **Context Analysis**: Extracts command contexts with executable, arguments, environment variables, and I/O binding information.
    *   **Policy-Driven Interactive Detection**: Uses explicit policies (not heuristics or regex) to classify commands as interactive or non-interactive based on structured rules for each executable type.
    *   **Special Handlers**: Includes deterministic handlers for complex cases like SQLite3, which allows batch execution with `-batch` flags, inline SQL arguments, or bound stdin while blocking interactive sessions with parameter-consuming options. Agent prompts provide explicit guidance to both planners and executors on proper SQLite3 usage patterns.
    *   **Fail-Safe Design**: Blocks ambiguous or malformed commands to prevent security risks.
*   **Policy Engine**: Implements `PolicyEngine.evaluate()` that applies explicit allow/block rules for interpreters (Python, Node, Ruby, Perl, PHP, Lua, Shell) and database CLIs (MySQL, PostgreSQL, Redis, Mongo, SQLite3) based on required flags, script extensions, and stdin requirements. SQLite3 has a special deterministic handler that allows execution only when `-batch` is present, stdin is bound, or inline SQL arguments are provided, while blocking interactive sessions with parameter-consuming options.
*   **Philosophy**: "Go upstream" - solves parsing at the source rather than adding downstream patches, enabling complex shell scripts while maintaining safety through deterministic policies rather than guesswork.

### Command Policy Hints (sqlite3 & friends)

The deterministic command parser keeps most interpreters in `run_command` as long as they are clearly non-interactive. For `sqlite3`, supply one of these patterns:

- `sqlite3 -batch my.db 'select 1;'` (preferred)
- `sqlite3 my.db "select count(*) from users;"` (inline SQL argument)
- `printf 'select 1;\\n' | sqlite3 my.db` (stdin already populated)

Options like `-cmd` or `-init` alone do NOT exit the shell; Agent A should call out the need for `-batch`/inline SQL/STDIN in TODOs, and Agent B must implement commands accordingly. Bare `sqlite3 my.db` remains blocked—use `run_interactive` only when you want the REPL.

Database CLIs (MySQL, PostgreSQL, Redis, Mongo) now support non-interactive execution via execute flags (`-e`, `-c`, `--eval`) or piped input, while SQLite3 has deterministic policies allowing batch execution with `-batch` flags, inline SQL arguments, or bound stdin while blocking interactive sessions.

---

## Project Structure

### Core Modules

```
orchestrator/
├── orchestrator.py         # Main Orchestrator class, handle_query() entry point
├── intention_cache.py      # FTS5-backed cache shared across routes
├── prompts.py              # Agent A/B system prompts with context injection
├── plan_schema.py          # Schema + helpers for narration templates/output_keys
├── plan_validator.py       # JSON schema validation with retry logic
├── output_parser.py        # Typed stdout parser for narration templates
├── metrics.py              # Telemetry collection (cycle breakdowns, latency, tool stats)

memory/
├── api.py                  # Unified Memory API (CRUD for all tables)
├── schema.py               # Database schema and initialization

tools.py                     # Tool registry (run_command, run_interactive, write_file, http_request, etc.)
shell_integration.py         # Bash/zsh wrapper with cwd isolation
config.py                    # Multi-backend LLM configuration (OpenAI, MiniMax, Kimi, custom)
llm_client.py                # LLM client with role-specific prompts
tool_executor.py             # Tool invocation and validation
main.py                      # CLI entry point (REPL)
```

### Main Components

### 1. Orchestrator (`orchestrator/orchestrator.py`)
The central controller of the application. It manages the lifecycle of a "Cycle" (a single user query resolution).
*   **Responsibilities**:
    *   Session and Cycle management.
    *   Invoking Agent A and routing based on the tool called (`delegate_to_agent_b` vs `respond_to_user`).
    *   Invoking Agent B to execute the plan in a tool-use loop.
    *   Logging all events to the Memory system.
    *   Rendering the final response to the user.

### 2. Tool Executor (`tool_executor.py`)
A dedicated component for safely executing the steps defined by Agent B.
*   **Responsibilities**:
    *   Validating tool names and arguments.
    *   Executes native function calls from the LLM.
    *   Capturing `stdout`, `stderr`, and exit codes.
    *   Formatting outputs for the database.

### 3. Memory System (`memory/api.py`, `memory/schema.py`)
A unified interface for persistent state, backed by SQLite (`logs/orchestrator.db`).
*   **Key Tables**:
    *   `sessions`: Tracks global session metadata.
    *   `task_state`: Stores the "Plan" (Agent A's Intent).
    *   `step_outputs`: Stores the actual results of every executed step.
    *   `interactions`: Logs raw LLM prompts and responses for debugging and auditing.
    *   `chat_history`: Stores the user-facing conversation log.
    *   `cycle_metrics`, `step_metrics`, `llm_metrics`: Telemetry data.

### 4. LLM Client (`llm_client.py`)
A standardized wrapper for OpenAI-compatible API calls.
*   **Features**:
    *   Native support for `tools` and `tool_calls`.
    *   Automatic retries with exponential backoff.
    *   Role-based logging (tagging calls as 'A' or 'B').
    *   Token usage tracking.

### 5. User Interface (`ui_formatter.py`)
Handles the rendering of the terminal interface.
*   **Features**:
    *   Dynamic prompt with user, host, and current working directory.
    *   Rich Markdown rendering for AI responses (bold, tables, code blocks).
    *   Live status updates during execution (Planning -> Executing -> Responding).
    *   Collapsible tool output panels.

---

## Running the Terminal

### Quick Start

```bash
# Activate venv
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run interactive terminal
python main.py
```

### Configuration

Set via `.env`, environment variables, or CLI flags (in order of precedence):

```bash
# .env file
AGENT_TYPE=custom                    # minimax, kimi2, custom
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL=gpt-4-turbo
MAX_TOKENS=2048
TEMPERATURE=0.7
SAVE_LLM_TRACES=true              # turn off only if storage is a concern

# CLI override
python main.py --agent kimi2 --max-tokens 4096 --temperature 0.9
```

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

### Hard Limits and Recovery Mechanisms

The system implements multiple layers of hard limits to prevent runaway resource consumption while allowing reasonable recovery from transient issues:

1. **Agent B Execution Loop Limit** (`orchestrator.py`):
   - **Limit**: `max_loops = 15` (hardcoded)
   - **Purpose**: Caps the number of tool execution iterations in Agent B's ReAct loop
   - **Impact**: Each iteration can make one LLM call + tool execution
   - **Behavior**: After 15 iterations, the loop terminates regardless of completion status

2. **LLM API Retry Limit** (`llm_client.py`):
   - **Limit**: `max_retries = 3` (hardcoded, default parameter)
   - **Purpose**: Limits retries for failed LLM API calls with exponential backoff
   - **Backoff Schedule**: 1s, 2s, 4s delays between attempts
   - **Retryable Errors**: timeout, rate_limit, 429, connection, 503, service unavailable
   - **Non-Retryable Errors**: auth errors (401/403), malformed requests (400), unknown errors
   - **Impact**: A single Agent B step can consume up to 3 LLM calls before failing

3. **Combined Impact**:
   - **Worst Case**: Agent B loop could make up to **15 × 3 = 45 LLM calls** before giving up
   - **Recovery**: System gracefully degrades - failed cycles are logged but don't crash the application
   - **Fallback**: On persistent failures, Agent A generates user-friendly error explanations

These limits ensure system stability while providing robust error recovery for transient network/API issues.

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

## Error Handling and Differentiation in the Orchestrator

The orchestrator (`orchestrator/orchestrator.py`) is designed with robust error handling to ensure reliability, user safety, and debuggability. It differentiates between various error types based on context, stage, and source, preventing conflation of issues (e.g., a JSON parsing error vs. a command execution failure). This chapter documents the error taxonomy, detection mechanisms, handling strategies, logging, and recovery processes.

### Error Taxonomy
Errors are categorized by **type**, **stage**, and **source** for precise differentiation:

1. **By Type**:
   - **JSON Parsing Errors**: Invalid JSON in tool arguments or responses (e.g., malformed `{"file_path": }`).
   - **Tool Execution Errors**: Failures during tool invocation (e.g., file not found in `read_file`, command syntax errors in `run_command`).
   - **Command Exit Code Errors**: Non-zero exit codes from shell commands (e.g., `ls` on non-existent directory, `grep` with no matches).
   - **LLM Call Errors**: API failures, timeouts, or invalid responses from the LLM provider.
   - **Orchestrator Internal Errors**: Exceptions in the orchestrator logic (e.g., database errors, invalid plan structures).
   - **Validation Errors**: Plan or response validation failures (e.g., missing required fields in Agent A's output).

2. **By Stage**:
   - **Planning (Agent A)**: Errors during intent analysis or tool calling.
   - **Execution (Agent B Loop)**: Errors in tool calls, observations, or loop logic.
   - **Narration/Finalization**: Errors in response formatting or segment generation.
   - **Orchestrator Lifecycle**: Errors in session/cycle management or database operations.

3. **By Source**:
   - **User Input**: Invalid queries or malformed data.
   - **LLM Output**: Hallucinations, incomplete responses, or tool misuse.
   - **System/External**: File system issues, network failures, or tool executor bugs.
   - **Internal Logic**: Code bugs in orchestrator, prompts, or tools.

### Detection Mechanisms
The orchestrator uses layered detection to identify and classify errors early:

1. **JSON Parsing**:
   - In `_run_agent_b_tool_loop`, tool arguments are parsed with `json.loads(tc.function.arguments)`.
   - Failure: Catches `json.JSONDecodeError`, logs as `JSONDecodeError`, and defaults `args` to `{}` to continue gracefully.

2. **Tool Execution**:
   - Wrapped in `try-except` around `self.tool_executor.execute()`.
   - Detects: Exceptions from tools (e.g., `FileNotFoundError` for `read_file`, `OSError` for permissions).
   - Also checks `exec_result.get("error")` for tool-reported errors.

3. **Command Exit Codes**:
   - After execution, inspects `exit_code`:
     - `0`: Success.
     - Non-zero: Analyzes `stderr` and `stdout` for informativeness.
     - Uses `_is_informative_negative()` to treat codes like 1/2/127 with diagnostic output as "successful failures" (e.g., "command not found" with suggestions).

4. **LLM Call Errors**:
   - In `llm_client.call()`, checks `response["error"]`.
   - Types: API errors, rate limits, malformed responses.

5. **Validation Errors**:
   - Uses `PlanValidator` for Agent A responses.
   - Detects missing tools, invalid JSON, or unknown response types.

6. **Orchestrator Exceptions**:
   - Top-level `try-except` in `handle_query()` catches all unhandled errors.
   - Differentiates by `e.__class__.__name__` (e.g., `PlanValidationError`, `sqlite3.Error`).

### Handling Strategies
Errors are handled with a "fail gracefully, log thoroughly, recover if possible" approach:

1. **Graceful Degradation**:
   - JSON errors: Continue with empty args; tool may fail but doesn't crash the loop.
   - Command errors: If informative (e.g., "file not found"), treat as success and include output in response.
   - LLM errors: Retry with backoff; if persistent, fall back to Agent A for error explanation.

2. **Recovery Mechanisms**:
   - **Tool Failures**: Surface structured telemetry (tool name, args, stderr) and stop the cycle; no automatic narration.
   - **Loop Continuation**: On step failure, log and continue if not critical; abort on max failures.
   - **Fatal Errors**: Record the issue in `cycle_failures` and return a minimal user notice pointing to the logged cycle.
   - **Partial Success**: Save completed steps even if the cycle fails overall.

3. **User Communication**:
   - Users receive a short notice (e.g., "Cycle `<id>` failed. See cycle_failures for details.") instead of AI-generated explanations.
   - Investigation details live exclusively in telemetry tables.

4. **Safety Measures**:
   - Never expose internal errors to users.
   - Sanitize outputs (e.g., no raw stack traces).
   - Rollback DB transactions on failures to prevent corruption.

### Logging and Persistence
All errors are logged for debugging and improvement:

1. **Database Logging**:
   - `cycle_failures` table: Stores structured telemetry (`process`, `stage`, `error_type`, `error_code`, `facts_json`) for each failed cycle.
   - `llm_call_fails` table: Captures every failed LLM invocation (role, provider/model, parameters, full prompt, raw provider error) for debugging outages.
   - `step_outputs`: Logs per-step errors, including `stderr`, `exit_code`, and parsed errors.
   - `interactions`: Raw LLM responses for auditing.

2. **Event Emission**:
   - `_emit_tool_output()`: Sends error details to UI callbacks.
   - Status updates: "Planning failed", "Execution error".

3. **Failure Snapshots**:
   - Failure context is stored as structured `facts_json` instead of narrated summaries; Agent A is never invoked for fallbacks.
4. **Metrics**:
   - Tracks error rates in `cycle_metrics` and `step_metrics`.

### Recovery and Adaptation
- **Short-Term**: Retry alternates (e.g., for empty output: try `ls -a` after `ls`).
- **Long-Term**: Use logged errors to refine prompts (e.g., add rules for common failures) or improve tools.
- **Agent Involvement**: Agent A explains errors; Agent B can adapt (e.g., modify TODO on failures, as discussed in TODO technique).

### Examples from Cycles
- **JSON Error**: In a cycle, invalid tool args → Logged as `JSONDecodeError`, args defaulted, tool fails → Agent A explains "Invalid arguments provided".
- **File Error**: `read_file` on missing file → `FileNotFoundError` → Step failed, logged with `stderr`, cycle continues if not critical.
- **Command Error**: `ls /nonexistent` → Exit code 2, stderr: "No such file" → Treated as informative success, output included.
- **LLM Error**: API timeout → Retried, if fails → Fallback to Agent A narration.

This error handling ensures the system is resilient, debuggable, and user-friendly, differentiating issues to enable targeted fixes. Future changes (e.g., TODO enforcement) will build on this foundation.

## Information Flow

1.  **User Query**: The user types a command or question into the terminal.
2.  **Cycle Start**: The Orchestrator creates a unique `cycle_id`.
3.  **Agent A (Intent)**:
    *   The Orchestrator calls Agent A with the query and history.
    *   **Decision Point (Native Tool Call)**:
        *   *Scenario 1 (Chat)*: Agent A calls `respond_to_user`. The cycle ends, and the text is shown.
        *   *Scenario 2 (Action)*: Agent A calls `delegate_to_agent_b` with an `intent`, `success_criteria`, and structured `todos` list for precise execution planning.
4.  **Agent B (Execution Loop)**:
    *   If delegated, the Orchestrator starts the Agent B loop.
    *   **Loop**:
        *   Agent B analyzes the intent, validates against the current TODO item, and calls a tool (e.g., `run_command`).
        *   `ToolExecutor` runs the tool and returns the output.
        *   Agent B observes the output, updates TODO progress, and decides the next step.
5.  **Final Response**:
    *   The final response is displayed to the user with full Markdown formatting.
6.  **Persistence**: All steps, tool outputs, and metrics are saved to the database.

## Key Files

*   `README.md`: User documentation including command policy hints for SQLite3 and database CLIs, with guidance on proper usage patterns to stay in the non-interactive execution path.
*   `config.py`: Handles environment variables, model selection, and agent-specific settings.
*   `orchestrator/orchestrator.py`: Core logic for the dual-agent flow and loop management.
*   **Agent Prompts**: Updated for both Agent A and Agent B roles to provide explicit guidance on SQLite3 usage patterns (batch flags, inline SQL, piped stdin) and reinforce that bare `sqlite3 <db>` should use `run_interactive`.
*   `memory/schema.py`: Database schema definitions.
*   `tools.py`: Definitions of available tools (e.g., `run_command`, `read_file`).
*   `command_parser.py`: Advanced shell command parser with lexer and AST analysis for policy-driven interactive command detection.
*   `ui_formatter.py`: UI rendering logic using `rich`.

## Development Guide

### Adding a New Tool

1. Create a class in `tools.py` inheriting from `BaseTool`
2. Implement `name`, `description`, `schema`, `execute()` properties
3. Register in `TOOLS` dict
4. Test with a simple query

Example:

```python
class MyTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_tool"
    
    @property
    def description(self) -> str:
        return "Does something useful"
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "my_tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "arg1": {"type": "string"}
                    },
                    "required": ["arg1"]
                }
            }
        }
    
    def execute(self, arg1: str) -> str:
        return f"Executed with {arg1}"
```

### Guiding Agent A Decisions

With the classifier removed, Agent A’s prompt is the primary lever for influencing routing behavior. Update `orchestrator/prompts.py` to remind Agent A when to issue a direct response versus a one-step plan, and to flag interactive work explicitly by setting `tool_name` to `run_interactive`. Any prompt tweaks should be accompanied by new fixtures in `tests/test_orchestrator.py` or `tests/test_e2e_planner.py` so regressions are caught automatically.

### Adjusting Cache Thresholds

`orchestrator/intention_cache.py` still exposes `IntentionCache.DEFAULT_MIN_SCORE`, `DEFAULT_MIN_USAGE`, and `DEFAULT_SEARCH_LIMIT`. Lowering `min_score` increases cache hits but risks false positives; raising it makes cache hits rarer but safer. After changing these values, add or update targeted tests (for example in `tests/test_orchestrator.py`) to confirm the new thresholds behave as expected.

### LLM Tracing

All LLM calls are logged to `orchestrator.db` for debugging:

```python
from memory.api import Memory

mem = Memory()
traces = mem.get_llm_traces(limit=5)

for trace in traces:
    print(f"Role: {trace['role']}")
    print(f"Prompt (first 200 chars): {trace['full_prompt'][:200]}")
    print(f"Response (first 200 chars): {trace['full_response'][:200]}")
```

---

## Testing

**Status: 241 tests pass** (verified Nov 12, 2025 after Phase 4 token optimization)

### Core Integration Tests (Recommended)

These tests validate the routerless orchestrator with the dual-agent loop:

```bash
# Use venv python to run tests
PYTHON=.venv/bin/python

# Core suites (ALL PASS ✅)
$PYTHON -m pytest tests/test_orchestrator.py -v        # Agent A prompts, handle_query, Agent B payloads
$PYTHON -m pytest tests/test_e2e_planner.py -v         # Plan execution + narration templates
$PYTHON -m pytest tests/test_output_parser.py -v       # Typed stdout parsing for narration templates
```
# Run all core tests together
$PYTHON -m pytest tests/test_e2e_*.py tests/test_cross_*.py -v
```

**What's Tested:**
- ✅ Agent A planning + narration (JSON plan generation + templated summaries)
- ✅ Agent B execution (tool schema → precise args)
- ✅ Plan → ToolExecutor → OutputParser handshake (typed values for narration templates)
- ✅ Memory persistence (SQLite)
- ✅ Cycle tracking and session bookkeeping
- ✅ Step output storage + structured previews

### Additional Tests

```bash
# Memory API tests (database operations)
$PYTHON -m pytest tests/test_memory.py -v

### Why FTS5 for Cache?

SQLite FTS5 is zero-dependency, fast enough for MVP, and improves naturally with data. ML classifier deferred to Phase 6.

### Why Conservative Fallback?

Better to over-plan an ambiguous query than misroute it. PLANNER confidence defaults to 0.6; user can always interrupt.

---


---

## License

(Add your license here)

---

## Support

For questions, file a new bead:

```bash
bd create "Question: How do I...?" -t task -p 2 --json
```

For debugging issues, see [DEBUGGING_V2.md](history/DEBUGGING_V2.md). For analyzing execution cycles, see [cycles_debug_guide.md](cycles_debug_guide.md). For architecture details, read [version-3-architecture.md](history/version-3-architecture.md).

---
