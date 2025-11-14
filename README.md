# AI-Powered Linux Shell Terminal — v2.0

**Version:** 2.0 (Routerless Dual-Agent Orchestrator)

## Overview

This is an **AI-powered Linux terminal** built on a dual-agent orchestrator. A lightweight command classifier (regex heuristics + intention cache) decides whether a query should run through the SHELL, CACHED, CHAT, or PLANNER path, and Agent A always narrates the final answer.

- **Agent A (Planner / Narrator / Chat):** First hop for every request. Emits either a direct response or a structured plan with `steps[]` + `narration_template`, then renders the final narration after execution.
- **Agent B (Command Engineer):** Called per step to generate precise shell commands (or tool arguments for non-shell tools) plus an `output_format` that explains how to interpret stdout.

**Core Philosophy**:
- **In AI We Trust**: Minimal guardrails, full system access
- **Shell-First**: Favor single, precise shell commands; multi-step plans are opt-in
- **Speed Through Intelligence**: On-device classifier + cache keep literal shell commands under ~500 ms without sacrificing narration quality

---

## Architecture Overview

### Routerless Flow (Classifier + Cache)

```
Query
  ↓
[Classifier + Intention Cache]
  ├─ SHELL   → Agent A emits single-step plan → Agent B runs run_command/run_interactive → narration
  ├─ CACHED  → ToolExecutor replays cached tool args → Agent A narrates result
  ├─ CHAT    → Agent A responds directly (no tools)
  └─ PLANNER → Agent A issues multi-step plan → Agent B executes each step → template rendered
```

The classifier mirrors the legacy router’s precedence but is embedded in `orchestrator/command_classifier.py`, so there is no standalone router service or CLI anymore.

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
- `route_metrics`, `step_metrics`, `llm_metrics`: Telemetry

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
├── command_classifier.py   # Routerless classifier + heuristics
├── command_patterns.py     # Regex bundles for shell/chat/interactive detection
├── intention_cache.py      # FTS5-backed cache shared across routes
├── prompts.py              # Agent A/B system prompts with context injection
├── plan_schema.py          # Schema + helpers for narration templates/output_keys
├── plan_validator.py       # JSON schema validation with retry logic
├── output_parser.py        # Typed stdout parser for Agent B output_format payloads
├── metrics.py              # Telemetry collection (route distribution, latency, cache hits)

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

# CLI override
python main.py --agent kimi2 --max-tokens 4096 --temperature 0.9
```

## REPL Experience

- **Dynamic prompt & status line** – The prompt mirrors the AI shell’s cwd (`user@host ~/repo ❯`). A single in-place status line cycles through `Planning…`, `Executing commands…`, and `Preparing response…` with elapsed seconds so you always know what the orchestrator is doing.
- **Narration stays human** – Agent A’s final narration is rendered as a Rich panel (Markdown supported) outside any ANSI block, keeping the conversation readable even when commands run in between.
- **Command panels for raw output** – Every shell or planner step streams into an ANSI-styled panel that shows the command header, success state, and stdout/stderr. JSON payloads are auto-prettified, and `read_file` steps render Markdown/code with syntax highlighting plus truncation notices for huge files.
- **Sequential streaming** – Narration and panels arrive in execution order, so prompts that mix reasoning (“explain Tokyo”) and shell work (“list *.txt”) naturally display as `narration → command panel → narration → command panel`, matching the dual-agent plan.

## Telemetry & Metrics

Metrics are automatically collected and persisted to `orchestrator.db`.

### View Metrics

```python
from orchestrator.metrics import get_metrics

metrics = get_metrics()

# Route distribution (last 24h)
print(metrics.get_route_distribution())
# Output: {'SHELL': 45, 'CHAT': 28, 'CACHED': 12, 'PLANNER': 5}

# Latency stats
print(metrics.get_latency_stats())
# Output: {avg: 250ms, p95: 450ms, ...}

# Cache hit rate
print(metrics.get_cache_hit_rate())
# Output: {hits: 12, total: 100, hit_rate_percent: 12.0}

# Full report
report = metrics.get_summary_report()
print(f"SHELL avg latency: {report['latency_stats']['shell']['avg_ms']}ms")
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

### Tuning the Classifier

Regex heuristics now live in `orchestrator/command_patterns.py`:

- `SHELL_PATTERNS`: 160+ single-line shell commands (git, npm, ls, etc.)
- `CHAT_PATTERNS`: Informational prompts such as “What is…”
- `INTERACTIVE_PATTERNS`: vim, nano, top, ssh, mysql, etc.

To add a new shell command, edit `SHELL_PATTERNS` and re-run `python -m pytest tests/test_command_classifier.py`. Interactive commands should go into `INTERACTIVE_PATTERNS` so Agent B selects `run_interactive`.

### Adjusting Cache Thresholds

`orchestrator/intention_cache.py` exposes `IntentionCache.DEFAULT_MIN_SCORE`, `DEFAULT_MIN_USAGE`, and `DEFAULT_SEARCH_LIMIT`. Lowering `min_score` increases cache hits but risks false positives; raising it makes cache hits rarer but safer. After changing these values, run `python -m pytest tests/test_e2e_chat_cached.py -k cached` to confirm behavior.

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

These tests validate the complete v2.0 orchestrator with Agent A/B/C coordination:

```bash
# Use venv python to run tests
PYTHON=.venv/bin/python

# Core end-to-end tests (42 tests - ALL PASS ✅)
$PYTHON -m pytest tests/test_e2e_planner.py -v              # 16 tests: PLANNER route, Agent A/B
$PYTHON -m pytest tests/test_cross_route_integration.py -v  # 11 tests: Cross-route workflows
$PYTHON -m pytest tests/test_e2e_chat_cached.py -v          # 15 tests: CHAT, CACHED routes

# Run all core tests together
$PYTHON -m pytest tests/test_e2e_*.py tests/test_cross_*.py -v
```

**What's Tested:**
- ✅ PLANNER route (multi-step task decomposition)
- ✅ Agent A planning + narration (JSON plan generation + templated summaries)
- ✅ Agent B execution (tool schema → precise args)
- ✅ CHAT route (simple queries)
- ✅ CACHED route (intention cache, zero-LLM execution)
- ✅ Cross-route context preservation
- ✅ Memory persistence (SQLite)
- ✅ Cycle tracking and state advancement

### Additional Tests

```bash
# Command-classifier heuristics
$PYTHON -m pytest tests/test_command_classifier.py -v

# Memory API tests (database operations)
$PYTHON -m pytest tests/test_memory.py -v

# System context builder (Phase 4: Lean prompts)
$PYTHON -m pytest tests/test_system_context_builder.py -v
```

**Note:** Some legacy v1.3 tests and environment-specific tests may fail. Focus on the core integration tests above for v2.0 validation.

---

## Architecture Decisions

### Why Unified Memory?

v1.3 had fragmented memory stores (5+ files, multiple databases). v2.0 uses **one orchestrator.db** for:
- Single source of truth
- Transactional consistency
- Easier debugging and metrics
- No data sync issues

### Why Shell-First?

Shell commands are ~50% of real interactions. Executing them immediately (not through planner) preserves the feel of a real terminal. Interactive commands (vim, top) must have TTY access anyway.

### Why FTS5 for Cache?

SQLite FTS5 is zero-dependency, fast enough for MVP, and improves naturally with data. ML classifier deferred to Phase 6.

### Why Conservative Fallback?

Better to over-plan an ambiguous query than misroute it. PLANNER confidence defaults to 0.6; user can always interrupt.

---

## Known Limitations

### Phase 2 (Current)

- ⏭️ **Streaming**: Long-running commands not yet streamed (full output returned)
- ⏭️ **Session Persistence**: Each orchestrator instance creates a new session (no resumption)
- ⏭️ **Artifact Storage**: Large outputs (>1000 chars) stored as preview only
- ⏭️ **ML Router**: Regex+cache only; ML classifier deferred to Phase 6

### Not in Scope

- Multi-user or tenant support
- Distributed execution
- Background/scheduled tasks
- Custom agent roles beyond A/B

---

## v2.0 Documentation Index

All architecture and development docs are in the `history/` directory:

| File | Purpose |
|------|---------|
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

**Built with [Amp](https://ampcode.com) using GPT-4 Turbo + Oracle reasoning.**
