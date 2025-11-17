# AI-Powered Linux Shell Terminal — v2.0

**Version:** 2.0 (Routerless Dual-Agent Orchestrator)

## Overview

This is an **AI-powered Linux terminal** built on a dual-agent orchestrator. Every query is handled by Agent A first; it either answers directly or produces a structured execution plan that Agent B carries out via ToolExecutor. Agent A also renders the final narration, so there is no router shortcut or extra narrator role.

- **Agent A (Planner / Narrator / Chat):** First hop for every request. Emits either a direct response or a structured plan with `steps[]` + `narration_template`, then renders the final narration after execution.
- **Agent B (Command Engineer):** Called per step to generate precise shell commands (or tool arguments for non-shell tools) plus an `output_format` that explains how to interpret stdout.

**Core Philosophy**:
- **In AI We Trust**: Minimal guardrails, full system access
- **Shell-First**: Favor single, precise shell commands; multi-step plans are opt-in
- **Speed Through Intelligence**: On-device classifier + cache keep literal shell commands under ~500 ms without sacrificing narration quality

---

## Architecture Overview

### Routerless Flow (Agent A-first)

```
Query
    ↓
Agent A (plan or direct response)
    ├─ Direct response → saved to chat history → returned to REPL
    └─ Execution plan  → Agent B engineers commands per step → ToolExecutor runs them → typed outputs hydrate Agent A's narration template
```

The legacy router and classifier are gone; all telemetry now comes from Agent A’s decisions and the resulting plan execution.

### Unified Memory System

**Single Database**: `logs/orchestrator.db` (120KB SQLite)

Tables:
- `sessions`: Session metadata and LLM model info
- `router_decisions`: Route classification with confidence scores
- `intention_cache`: FTS5-indexed cache of successful executions
- `task_state`: PLANNER route plans and status
- `step_outputs`: Individual step results with stdout/stderr snapshots, raw blobs, `output_format`, and JSON-encoded `parsed_outputs`
- `chat_history`: Conversation history for context injection
- `llm_traces`: Full prompt/response logs for debugging
- `cycle_metrics`, `step_metrics`, `llm_metrics`: Telemetry

All state is **transactional** with `session_id` + `cycle_id` tracking per orchestration cycle. The orchestrator now wraps every cycle in `Memory.cycle_transaction()`, committing only after a successful response so partial plans/step outputs never touch disk. Need a clean slate? Run `python -m memory.purge_db --yes --include-sessions --include-cache` to wipe orchestrator state before starting a new upgrade.

### Dual-Role LLM System

| Role | Prompt | Input | Output | Example |
|------|--------|-------|--------|---------|
| **Agent A (Planner / Narrator)** | Strategic planner + narrator instructions | User query, tool list, prior chat context | `{"response": ...}` or `{"steps": [...], "narration_template": "..."}` | `"steps": [{"tool_name": "run_command", ...}], "narration_template": "Files: {files}"` |
| **Agent B (Command Engineer)** | Precise tool executor | Current step metadata + schemas + previous outputs | Shell steps → `{"command": "...", "output_format": {...}}`; other tools → `{"tool_args": {...}}` | `{"command": "ls -lah", "output_format": {"files": "list"}}` |

After ToolExecutor runs a command, the orchestrator captures full stdout/stderr (normalized + raw), computes a 1 KB preview, and runs it through `orchestrator/output_parser.py`. The parser materializes Agent B’s declared `output_format` into typed Python values (`int`, `float`, `list`, `raw`, `table`, `json`, `str`). Those parsed values are persisted to `memory.step_outputs` and fed into Agent A’s `narration_template`, so templates can safely reference `{count}`, `{files}`, etc. without brittle string slicing.

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
├── output_parser.py        # Typed stdout parser for Agent B output_format payloads
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

### Deprecated v1.3 Code

The following are **deprecated and not used in v2.0**. They are kept for historical reference:

- `agent.py` – Old ReAct single-agent (replaced by Orchestrator + 3-role LLM)
- `db_logger.py` – Old fragmented session logger (replaced by unified Memory)
- `history_store.py`, `history_sql.py` – Old fragmented memory stores (replaced by orchestrator.db)
- `filesystem_context.py` – Old filesystem tracking (replaced by tool outputs + session state)
- `event_memory.py` – Old event journal (replaced by llm_traces + metrics tables)

Tests that reference v1.3 code will be skipped. **New development should only use v2.0 modules.**

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

## REPL Experience

- **Dynamic prompt & status line** – The prompt mirrors the AI shell’s cwd (`user@host ~/repo ❯`). A single in-place status line cycles through `Planning…`, `Executing commands…`, and `Preparing response…` with elapsed seconds so you always know what the orchestrator is doing.
- **Narration-first layout** – Agent A’s narration prints as plain text; scalar placeholders (e.g., `{count}`) interpolate inline so sentences stay readable, and Cycle IDs appear as plain text in the lower-right corner of each pane.
- **Structured blocks when needed** – When a step returns structured data, the REPL inserts fenced blocks (```output```, ```json```, ```md```, language fences, etc.) that contain the tool’s stdout exactly as captured—no nested panels or duplicate headers—matching `history/ai_terminal_spec_v1.5 (1).md`.
- **Sequential streaming** – Narration and any fenced blocks show up in execution order, so mixed prompts (“explain Tokyo” + “list *.txt”) appear naturally as `narration → fenced block → narration`, mirroring the dual-agent plan.

## Telemetry & Metrics

Metrics are automatically collected and persisted to `orchestrator.db`.

### View Metrics

```python
from orchestrator.metrics import get_metrics

metrics = get_metrics()

# Resolution breakdown (last 24h)
print(metrics.get_resolution_breakdown())
# Output: {'execution_plan': 12, 'direct_response': 33}

# Latency stats
print(metrics.get_latency_stats())
# Output: {avg: 250ms, p95: 450ms, ...}

# Interactive rate
print(metrics.get_interactive_rate())
# Output: {interactive_cycles: 4, total_cycles: 25, interactive_rate_percent: 16.0}

# Full report
report = metrics.get_summary_report()
print(f"Plans avg latency: {report['latency_stats']['execution_plan']['avg_ms']}ms")
```

### Metrics Dashboard (Future)

Telemetry can be exported for visualization:

```bash
# Export to CSV for charting
python -c "
from orchestrator.metrics import get_metrics
import json
metrics = get_metrics()
print(json.dumps(metrics.get_summary_report(), indent=2))
" > metrics.json
```

---

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

## v2.0 Documentation Index

All architecture and development docs are in the `history/` directory:

| File | Purpose |
|------|---------|
| **[ai_terminal_spec_v1.5](history/ai_terminal_spec_v1.5%20(1).md)** | Canonical REPL specification (pane structure, status line, plain text + fenced-block rendering) |
| **[IMPLEMENTATION_PLAN.md](history/IMPLEMENTATION_PLAN.md)** | Complete v2.0 design spec: 6 phases, success criteria, architecture decisions, risk mitigation |
| **[DOUBLE_AGENT_ARCHITECTURE.md](DOUBLE_AGENT_ARCHITECTURE.md)** | Historical doc outlining the original triple-agent concept (pre-upgrade) |
| **[PHASE_2_SIGN_OFF.md](history/PHASE_2_SIGN_OFF.md)** | Phase 2 final verification: 58 tests passing, all acceptance criteria met |
| **[PHASE_2_COMPLETION.md](history/PHASE_2_COMPLETION.md)** | Phase 2 detailed completion: cross-route integration, context handoff, step persistence |
| **[PHASE_2_ACCEPTANCE_CRITERIA.md](history/PHASE_2_ACCEPTANCE_CRITERIA.md)** | Phase 2 acceptance tests: specific test commands and success metrics |
| **[architectural_upgrade.md](history/architectural_upgrade.md)** | Dual-agent upgrade plan with phased rollout, acceptance criteria, and testing strategy |
| **[DEBUGGING_V2.md](history/DEBUGGING_V2.md)** | **Developers**: Layer-by-layer debugging strategies, LLM tracing, performance profiling, database forensics |
| **[cycles_debug_guide.md](cycles_debug_guide.md)** | **Cycle Analysis**: Step-by-step guide to debug any execution cycle using database forensics and debug_cycle.py tool |
| **[PHASE_5_COMPLETION.md](history/PHASE_5_COMPLETION.md)** | Phase 5 final: telemetry integration, docs complete, 65/65 tests passing, production ready |
| **[PRODUCTION_READY_FIXES.md](history/PRODUCTION_READY_FIXES.md)** | **Production**: Oracle review fixes - config env names, metrics wiring, safe variable substitution, cross-platform venv, legacy tool gating |

### Quick Navigation

- **Getting Started**: README.md (this file) + [IMPLEMENTATION_PLAN.md](history/IMPLEMENTATION_PLAN.md) overview
- **Understand Architecture**: [DOUBLE_AGENT_ARCHITECTURE.md](DOUBLE_AGENT_ARCHITECTURE.md) + [IMPLEMENTATION_PLAN.md](history/IMPLEMENTATION_PLAN.md) sections 3-5
- **Tune Router**: [ROUTER_TUNING_GUIDE.md](history/ROUTER_TUNING_GUIDE.md)
- **Debug Issues**: [DEBUGGING_V2.md](history/DEBUGGING_V2.md)
- **Debug Execution Cycles**: [cycles_debug_guide.md](cycles_debug_guide.md) - analyze any cycle with database queries and debug_cycle.py
- **Test Router Manually**: [ROUTER_CLI_COMPLETE.md](history/ROUTER_CLI_COMPLETE.md)
- **Production Deployment**: [PRODUCTION_READY_FIXES.md](history/PRODUCTION_READY_FIXES.md)
- **Track Progress**: [PHASE_2_SIGN_OFF.md](history/PHASE_2_SIGN_OFF.md), [PHASE_5_COMPLETION.md](history/PHASE_5_COMPLETION.md)

---

## Contributing

1. **Check ready work**: `bd ready --json` to see unblocked issues
2. **Claim your task**: `bd update bd-XXX --status in_progress`
3. **Make changes**: New code in v2.0 modules (orchestrator/, memory/, tools/)
4. **Test**: Run `pytest` to ensure all tests pass
5. **Commit**: Always commit `.beads/issues.jsonl` with code changes
6. **Close issue**: `bd close bd-XXX --reason "Done"` when complete

---

## License

(Add your license here)

---

## Support

For questions, file a new bead:

```bash
bd create "Question: How do I...?" -t task -p 2 --json
```

For debugging issues, see [DEBUGGING_V2.md](history/DEBUGGING_V2.md). For analyzing execution cycles, see [cycles_debug_guide.md](cycles_debug_guide.md). For classifier or architecture details, read [history/architectural_upgrade.md](history/architectural_upgrade.md).

---
