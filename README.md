# AI-Powered Linux Shell Terminal — v2.0

**Version:** 2.0 (Multi-Role Orchestrator Architecture)

## Overview

This is an **AI-powered Linux terminal** using the **v2.0 Triple-Agent Orchestration Architecture**. A lightweight router classifies queries into four routes (SHELL/CACHED/CHAT/PLANNER), then dispatches to specialized LLM agents with fine-tuned roles:

- **Agent A (Planner)**: Decomposes complex tasks into high-level steps  
- **Agent B (Command Engineer)**: Generates precise tool arguments for each step  
- **Agent C (Narrator)**: Converts raw outputs into natural language for all routes

**Core Philosophy**: 
- **In AI We Trust**: Minimal guardrails, full system access
- **Shell-First**: Shell commands execute immediately (50%+ of interactions), not through planning layers  
- **Speed Through Intelligence**: Router uses fast regex rules + intention cache; only ambiguous queries hit the planner

---

## Architecture Overview

### v2.0 Routes (4-Level Precedence)

```
Query
  ↓
[SHELL] (160+ command patterns) → run_command/run_interactive immediately
  ↓ (if no match)
[CACHED] (FTS5 intention cache) → Cached tool args + Agent C narrator
  ↓ (if no cache hit)
[CHAT] (12 Q&A patterns) → Direct Agent C chat mode (no tools)
  ↓ (if ambiguous)
[PLANNER] (fallback) → Agent A→B loop for complex tasks
```

### Unified Memory System

**Single Database**: `logs/orchestrator.db` (120KB SQLite)

Tables:
- `sessions`: Session metadata and LLM model info
- `router_decisions`: Route classification with confidence scores
- `intention_cache`: FTS5-indexed cache of successful executions
- `task_state`: PLANNER route plans and status
- `step_outputs`: Individual step results with output previews
- `chat_history`: Conversation history for context injection
- `llm_traces`: Full prompt/response logs for debugging
- `route_metrics`, `step_metrics`, `llm_metrics`: Telemetry

All state is **transactional** with `session_id` + `cycle_id` tracking per orchestration cycle.

### Three-Role LLM System

| Role | Prompt | Input | Output | Example |
|------|--------|-------|--------|---------|
| **Agent A (Planner)** | Strategic task decomposer | User query + available tools | JSON plan: `{steps: [{id, tool_name, intent, description}]}` | "Create script → Design → Deploy" |
| **Agent B (Command Engineer)** | Precise tool executor | Plan step + tool schemas + previous outputs | JSON args: `{tool_name, tool_args}` | `{"command": "ls -lah | grep .py"}` |
| **Agent C (Narrator)** | Universal narrator | Raw outputs + context | Natural language response | "Found 3 Python files (42 KB total)" |

---

## Project Structure

### Core Modules

```
orchestrator/
├── orchestrator.py         # Main Orchestrator class, handle_query() entry point
├── prompts.py              # Agent A/B/C system prompts with context injection
├── metrics.py              # Telemetry collection (route distribution, latency, cache hits)
├── plan_validator.py       # JSON schema validation with retry logic

router/
├── router.py               # Main Router class, 4-level classification
├── rules.py                # RuleEngine with regex patterns + interactive detection
├── cli.py                  # Manual testing/debugging tool

memory/
├── api.py                  # Unified Memory API (CRUD for all tables)
├── schema.py               # Database schema and initialization

tools.py                     # Tool registry (run_command, run_interactive, write_file, http_request, etc.)
shell_integration.py         # Bash/zsh wrapper with cwd isolation
config.py                    # Multi-backend LLM configuration (OpenAI, MiniMax, Kimi, custom)
llm_client.py               # LLM client with role-specific prompts
tool_executor.py            # Tool invocation and validation
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

### Manual Router Testing

Use the Router CLI tool for debugging classification:

```bash
# Single query
python -m router.cli "What is Docker?"
# Output: CHAT route with confidence 0.95

# Batch test
python -m router.cli --test-file queries.txt

# Interactive REPL
python -m router.cli --interactive
```

---

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

### Tuning the Router

Router classification is controlled by regex patterns in `router/rules.py`:

- **SHELL_COMMAND_PATTERNS** (160+ patterns): File ops, package managers, build tools, etc.
- **CHAT_QUERY_PATTERNS** (12 patterns): "What is...", "Explain...", etc.
- **INTERACTIVE_COMMAND_PATTERNS** (20+ patterns): vim, nano, top, htop, etc.

To add a new SHELL command pattern:

```python
# In router/rules.py, add to SHELL_COMMAND_PATTERNS:
r'^mycommand\b',  # Matches: mycommand, mycommand -flags
```

Then test:

```bash
python -m router.cli "mycommand arg1 arg2"
# Should output: SHELL route
```

### Adjusting Cache Thresholds

Intention cache matching uses FTS5 BM25 scoring. Tuning:

```python
# In router/router.py, adjust threshold:
CACHE_THRESHOLD = 0.85  # Default: 85% similarity
```

Lower threshold → more cache hits but risk false positives  
Higher threshold → fewer cache hits but higher precision

### Debugging a Query

Enable verbose output:

```bash
python -m router.cli "complex query" --verbose --show-patterns
```

Output includes:
- Route classification
- Matched rules
- Confidence scores
- Pattern statistics
- Interactive command detection

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
- ✅ Agent A planning (JSON plan generation)
- ✅ Agent B execution (tool schema → precise args) **[Phase 4: Only current tool schema]**
- ✅ Agent C narration (conversational responses)
- ✅ CHAT route (simple queries)
- ✅ CACHED route (intention cache, zero-LLM execution)
- ✅ Cross-route context preservation
- ✅ Memory persistence (SQLite)
- ✅ Cycle tracking and state advancement

### Additional Tests

```bash
# Router tests (SHELL/CHAT/PLANNER classification)
$PYTHON -m pytest tests/test_router.py -v

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
- Custom agent roles beyond A/B/C

---

## v2.0 Documentation Index

All architecture and development docs are in the `history/` directory:

| File | Purpose |
|------|---------|
| **[IMPLEMENTATION_PLAN.md](history/IMPLEMENTATION_PLAN.md)** | Complete v2.0 design spec: 6 phases, success criteria, architecture decisions, risk mitigation |
| **[DOUBLE_AGENT_ARCHITECTURE.md](DOUBLE_AGENT_ARCHITECTURE.md)** | Core architectural vision: triple-agent system, unified memory, router design |
| **[PHASE_2_SIGN_OFF.md](history/PHASE_2_SIGN_OFF.md)** | Phase 2 final verification: 58 tests passing, all acceptance criteria met |
| **[PHASE_2_COMPLETION.md](history/PHASE_2_COMPLETION.md)** | Phase 2 detailed completion: cross-route integration, context handoff, step persistence |
| **[PHASE_2_ACCEPTANCE_CRITERIA.md](history/PHASE_2_ACCEPTANCE_CRITERIA.md)** | Phase 2 acceptance tests: specific test commands and success metrics |
| **[ROUTER_TUNING_GUIDE.md](history/ROUTER_TUNING_GUIDE.md)** | **Operators**: How to customize router patterns, adjust cache thresholds, debug routing decisions |
| **[DEBUGGING_V2.md](history/DEBUGGING_V2.md)** | **Developers**: Layer-by-layer debugging strategies, LLM tracing, performance profiling, database forensics |
| **[cycles_debug_guide.md](cycles_debug_guide.md)** | **Cycle Analysis**: Step-by-step guide to debug any execution cycle using database forensics and debug_cycle.py tool |
| **[ROUTER_CLI_COMPLETE.md](history/ROUTER_CLI_COMPLETE.md)** | Router CLI tool docs: manual testing, batch classification, interactive REPL, JSON output |
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
3. **Make changes**: New code in v2.0 modules (orchestrator/, router/, memory/)
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

For debugging issues, see [DEBUGGING_V2.md](history/DEBUGGING_V2.md). For analyzing execution cycles, see [cycles_debug_guide.md](cycles_debug_guide.md). For router customization, see [ROUTER_TUNING_GUIDE.md](history/ROUTER_TUNING_GUIDE.md).

---

**Built with [Amp](https://ampcode.com) using GPT-4 Turbo + Oracle reasoning.**
