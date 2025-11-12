# v2.0 Multi-Role Orchestration Upgrade — Implementation Plan

Status: Draft for bd issue breakdown
Owners: Core CLI team
Last updated: 2025-11-11

TL;DR
- **Clean refactor**: v1.3 is not in production, so we can rebuild without backward compatibility constraints.
- MVP Router = regex rules + SQLite intention cache (FTS) + conservative fallback to Planner; defer ML until we have data.
- Incremental phases: memory/router foundation → Agent C routes → Agent A/B orchestration → polish. All tracked via bd with clear success criteria.

Scope
- Goal: Upgrade from single ReAct agent (v1.3) to multi-role (A/B/C) orchestrated by a Router with intelligent routing and a single orchestrator-managed memory.
- Approach: Direct refactor without feature flags or compatibility layers - v1.3 code will be replaced, not wrapped.
- Non-goals (for v2.0): New external services, multi-tenant infra, distributed state, prompt experimentation beyond role separation, long-running background workflows.

**Core Philosophy**
- **In AI We Trust**: Minimal guardrails. The AI has full system access (filesystem, network, sudo). No artificial restrictions on tool usage.
- **Shell-First**: Shell commands are 50%+ of interactions. Shell integration (interactive and non-interactive) is a first-class citizen, not an afterthought.
- **Speed Through Intelligence**: Route simple shell commands instantly; don't over-orchestrate direct command execution.

---

## 1) Decision: Refactor vs Rebuild

**Recommendation: Direct refactor - v1.3 is not in production, so we can rebuild cleanly without compatibility layers.**

### Approach
- Replace v1.3 MiniAgent with new Orchestrator as the main entry point
- Introduce new modules: orchestrator/, router/, memory/
- Refactor agent.py into role-specific components (extract reusable LLM calling logic)
- Keep main.py as the CLI entry point but wire it to the new Orchestrator
- No feature flags needed - we'll build incrementally but replace as we go

### Code reuse potential
- **Reuse as-is** (zero changes):
  - tools.py (tool registry, ShellIntegration, HTTP client)
  - shell_integration.py (invoked via tools.run_command)
  - config.py (LLM backend handling)
  - ui_formatter.py (terminal output formatting)
  
- **Extract and refactor**:
  - agent.py → Extract LLMClient helper (handles OpenAI calls, trace logging, message formatting)
  - agent.py → Extract ToolExecutor (invoke tools by name with validated args)
  - Keep ReAct parsing utils as they may be useful for plan validation
  
- **Replace completely**:
  - agent.py `MiniAgent.process_input()` → orchestrator.py `Orchestrator.handle_query()`
  - Message history management → Router + memory facade per route
  - **OLD FRAGMENTED MEMORY** (db_logger.py, filesystem_context.py, history_sql/history_store, event_memory.py) → **NEW UNIFIED memory/ module with single orchestrator.db**
  
**Critical**: Build ONE new unified memory system from scratch. Do not try to adapt/wrap old fragmented stores. Reference old schemas for ideas, but implement fresh unified tables.

### Development velocity
- **Faster** than compatibility layers - no dual-write, no feature flags, no shadow mode complexity
- Phased delivery still works: build Router → Agent C routes → Agent A/B, testing each phase before moving on
- Can test new code in isolation before wiring to main.py

### Testing strategy
- Unit tests: router regex rules, FTS intention cache scoring, schema validators for Planner JSON plan and Executor instructions
- Integration tests: end-to-end for each route ([CHAT], [CACHED], [PLANNER]), golden outputs for Agent C narration
- Manual testing after each phase before moving to next
- Keep a git branch checkpoint before major refactors for easy rollback

Effort: M for foundation + router, M for Agent C, L for A/B loop, S for polish = ~10-12 days total

---

## 2) Clarifying the "Tiny Bird" Router

### What it is
- A lightweight classifier with three stages in order: rules → intention cache → fallback (MVP), with an optional ML classifier later when we have data.
- Always logs decision, confidence, and evidence to router_decisions.

### MVP implementation (no ML)

#### Stage 1: Fast rules (regex/heuristics)
- Examples mapped to [CHAT]:
  - /^(what|who|when|where|why|how)\s/i
  - /\b(explain|define|difference between|overview of)\b/i
  
- **Shell commands → [CACHED] or direct execution** (highest priority):
  - Direct shell syntax: starts with command names (ls, grep, find, cat, cd, etc.)
  - Pipeline indicators: contains |, &&, ||, >, >>
  - Shell builtins: pwd, echo, export, alias
  - **Strategy**: Shell commands should execute immediately via cached route or fast-path, NOT through multi-step [PLANNER]
  
- Candidates for [CACHED] (requires cache hit to convert):
  - /\b(list|show|print)\s+(files|history|processes|ports)\b/i
  - /\b(last|recent)\b.*\b(files|logs|changes)\b/i

#### Stage 2: Intention cache lookup (SQLite, FTS-based)
- Create intention_cache table with columns:
  - id (pk), user_query_text, normalized_intent, tool_name, tool_args_json, success_flag, last_used_at, usage_count
  - search_index via SQLite FTS5 on user_query_text + normalized_intent
- On new query:
  - Normalize text (lowercase, strip punctuation).
  - FTS search top-N; compute simple similarity score (bm25) + optional string ratio for tie-break.
  - If score exceeds threshold and success_flag=1 → classify [CACHED], return tool_name + tool_args_json.
- Thresholds start conservatively (e.g., bm25 rank within top-1 and string ratio >= 0.85 for short queries; more permissive for exact token overlap).

#### Stage 3: Conservative fallback
- If rules yield [CHAT] with high certainty (e.g., matches and no obvious tool keyword), return [CHAT] with confidence ~0.9.
- Else if intention cache hit qualifies → [CACHED] with confidence proportional to score.
- Else default to [PLANNER] with confidence 0.6 and log ambiguity.

### ML classifier (later, optional)
- Only after we have a few hundred labeled router_decisions with outcomes.
- DistilBERT or light logistic regression on hand-crafted features as a plug-in Stage 3 before fallback.
- Training data: user_query_text, token/verb features, tool keywords, measured complexity (length, punctuation density), and labels (CHAT/CACHED/PLANNER) validated by outcome.
- This is not needed for MVP; router quality likely strong with rules+cache.

### Router API contract
- Input: user_query_text, session_id
- Output: { route: "CHAT" | "CACHED" | "PLANNER", confidence: float, cache_hit?: {tool_name, tool_args_json}, rules_matched?: [string] }
- Side effects: Insert row into router_decisions with route, confidence, rules matched, cache evidence.

### Developer steps (MVP)
1. Add memory/ schema migration script to create:
   - router_decisions (id, session_id, query_text, route, confidence, rules, cache_hit_tool, cache_hit_args_json, created_at)
   - intention_cache (see columns above) + FTS index
2. Implement router/ module with:
   - RuleEngine (compiled regexes, return rule IDs)
   - IntentionCache (SQLite FTS search, scoring, and upsert on successful executions)
   - Router (compose stages, compute final decision)
3. Wire orchestrator entrypoint to:
   - Log query
   - Call Router
   - Branch to route handlers
4. Add bd acceptance tests for representative queries

### Success criteria (MVP)
- 95%+ of simple Q&A queries routed to [CHAT] in test corpus
- Zero tool executions triggered in [CHAT] route
- **90%+ of shell commands execute via [CACHED] or direct shell route (fast path, no planning overhead)**
- 80%+ precision for [CACHED] route on a seeded set of cached queries
- Unroutable/ambiguous queries reliably default to [PLANNER]
- **Interactive commands (vim, nano, top, htop) execute immediately without router delay**

---

## 3) High-Level Implementation Plan

### Phases overview
- Phase 0: Foundations and schemas
- Phase 1: Router MVP (rules + intention cache)
- Phase 2: Agent C (Chat/Narrator/Summarizer) path and orchestrator shell
- Phase 3: Planner (Agent A) plan JSON + validation
- Phase 4: Executor (Agent B) step loop + tool runner
- Phase 5: Integration, migration flags, and parity verification
- Phase 6: Optional ML router and single-DB consolidation

Each phase includes: dependencies, deliverables, success criteria, and bd issue seeds.

### Phase 0 — Foundations and Memory (Effort: M)
- **Dependencies**: None
- **Deliverables**:
  - **memory/ module** - NEW unified memory system (not adapter to old systems)
    - Single database: `logs/orchestrator.db` (replaces all fragmented stores)
    - Clean API: Memory.save_router_decision(), Memory.get_chat_history(), Memory.save_plan(), etc.
    - All tables in ONE database: router_decisions, intention_cache, task_state, step_outputs, interactions, chat_history, sessions
  - Schema migration script (idempotent)
  - Extract LLMClient from agent.py (handles OpenAI calls, trace logging to orchestrator.db)
  - Extract ToolExecutor from agent.py (invoke tools by name/args)
- **Success criteria**:
  - Single orchestrator.db file created with all tables
  - Memory API can CRUD all record types (router decisions, interactions, plans, steps, chat)
  - LLMClient can make calls with role-specific system prompts and log to orchestrator.db
  - ToolExecutor can invoke existing tools.py tools by name
  - Zero dependencies on old db_logger, filesystem_context, history_store, event_memory
- **bd seeds**:
  - feature: "Build unified memory system with single orchestrator.db" (p1). 
    - Acceptance: ONE database file; all tables created; CRUD operations tested; no old memory code used
  - task: "Extract LLMClient and ToolExecutor helpers" (p2). 
    - Acceptance: unit tests pass; can invoke LLM and tools; logs go to orchestrator.db

### Phase 1 — Router MVP (Effort: S-M)
- **Dependencies**: Phase 0
- **Deliverables**:
  - router/ module with RuleEngine + IntentionCache + Router
  - Standalone router CLI tool for testing: `python -m router.cli "query text"` prints decision
  - Unit tests for regex rules and FTS cache
- **Success criteria**:
  - Unit tests covering rule matches and false positives
  - Intention cache can be populated and queried with configurable thresholds
  - CLI tool can classify test queries and show confidence/evidence
- **bd seeds**:
  - feature: "Implement Router MVP (rules + FTS intention cache)" (p1). Acceptance: routes computed and stored; CLI tool works; tests pass.

### Phase 2 — Agent C and Orchestrator Shell (Effort: M)
- **Dependencies**: Phase 1
- **Deliverables**:
  - orchestrator/ module with Orchestrator class
  - Orchestrator.handle_query() entry point (replaces MiniAgent.process_input)
  - Agent C role prompts (three modes: Chat, Narrator, Summarizer)
  - Route handlers for [CHAT] and [CACHED] paths
  - **Shell fast-path**: Direct shell command execution for obvious commands (no LLM call before execution)
  - **Interactive command handler**: Immediate TTY forwarding for vim/nano/top/etc.
  - Wire to main.py (replace MiniAgent with Orchestrator)
- **Success criteria**:
  - [CHAT] route works end-to-end: Router → LLMClient(Agent C Chat mode) → UI display
  - [CACHED] route works: Router → ToolExecutor → LLMClient(Agent C Narrator) → UI display
  - **Shell commands execute immediately: `ls -la`, `grep pattern file.txt`, `cat README.md`**
  - **Interactive commands launch instantly: `vim file.py`, `top`, `htop`**
  - router_decisions and interactions logged for all cycles
  - Can run terminal and handle both chat and shell commands
- **bd seeds**:
  - feature: "Create Orchestrator with Agent C routes + shell fast-path" (p1). Acceptance: [CHAT] and [CACHED] e2e working; shell commands execute fast; interactive commands work; main.py wired.

### Phase 3 — Planner (Agent A) JSON plan + validation (Effort: M)
- **Dependencies**: Phase 2
- **Deliverables**:
  - Agent A role prompt: strategic planner with "computational economy" constraints
  - Plan JSON schema (spec only; no code): fields include steps[], step.id, step.type, rationale, tool hints, and explicit next-step criteria
  - Validator: reject non-conforming JSON; automatic retry with "return valid JSON only" guardrail prompt
  - task_state table usage to store plan and status
- **Success criteria**:
  - Agent A produces valid plan JSON for a known complex query
  - Orchestrator parses and persists plan; extracts first step
- **bd seeds**:
  - feature: "Implement Planner role and plan schema validation" (p1). Acceptance: >90% valid JSON in test corpus; invalid JSON triggers one retry.

### Phase 4 — Executor (Agent B) step loop + ToolRunner (Effort: L)
- **Dependencies**: Phase 3
- **Deliverables**:
  - Agent B role prompt: precise tool executor; one step at a time; strong schema adherence to available tools
  - ToolRunner adapter: invoke tools.py by name with validated args; capture outputs, exit_code, error messages
  - Retry policy on execution failure (bounded)
  - step_outputs persistence; plan advancement; end-of-plan summarization via Agent C
- **Success criteria**:
  - End-to-end [PLANNER] flow for 3 representative tasks:
    - Shell-first pipeline (list/sort files with filters)
    - Filesystem read/write task
    - HTTP API fetch + jq filter
  - No accidental Python sandbox usage when shell suffices (asserted in prompts and validated in outputs)
- **bd seeds**:
  - feature: "Agent B executor + ToolRunner + step loop" (p1). Acceptance: e2e for three tasks passes + logs persisted.

### Phase 5 — Polish and Documentation (Effort: S-M)
- **Dependencies**: Phases 2–4
- **Deliverables**:
  - Remove old agent.py code (keep only extracted helpers if useful)
  - Update README with v2.0 architecture overview
  - Add docs in history/ for Router tuning, adding new routes, debugging
  - Add telemetry/metrics for route distribution, latencies, cache hit rates
- **Success criteria**:
  - Clean codebase with no dead v1.3 code
  - README accurately describes new architecture
  - Telemetry shows route distribution and performance metrics
- **bd seeds**:
  - task: "Remove legacy v1.3 code and polish codebase" (p2). Acceptance: no unused code; git history clean.
  - task: "Update documentation for v2.0 architecture" (p2). Acceptance: README + history/ docs updated.

### Phase 6 — Optional ML Router + Single-DB consolidation (Effort: M–L, optional)
- **Dependencies**: Phase 1+ data accumulation
- **Deliverables**:
  - Lightweight classifier integration (if data supports it), A/B with threshold comparison
  - Consolidate legacy history/event stores into the unified DB: migrate or virtualize via views
- **Success criteria**:
  - Demonstrated routing accuracy improvement ≥5–10% on ambiguous set, with negligible latency increase
- **bd seeds**:
  - feature: "Add ML classifier to Router (optional)" (p3). Acceptance: measurable lift on held-out set.
  - task: "Consolidate memory into single SQLite file" (p2). Acceptance: all tables co-reside; old code paths removed.

### Incremental build strategy
- Phase 0: Foundation (memory, helpers) - can test in isolation
- Phase 1: Router - test with CLI tool before integration
- Phase 2: Agent C routes + Orchestrator - replace main.py, can now handle simple queries
- Phase 3: Agent A - can create plans but not execute yet
- Phase 4: Agent B - full [PLANNER] route works
- Phase 5: Polish and cleanup

Each phase is a working checkpoint that can be tested before moving to next.

### Development workflow
- Create git branch: `git checkout -b v2-orchestrator`
- Implement phases incrementally
- Test each phase thoroughly before next
- Tag major checkpoints: `v2.0-phase2`, `v2.0-phase3`, etc.
- When complete and tested: merge to main and tag `v2.0`

### Testing and validation checkpoints
- Router corpus tests: 50–100 queries labeled; track precision/recall per route.
- Plan schema compliance rate: target >90% valid on first try; retry success >98%.
- Executor safety: no sandbox when shell suffices; enforce via prompt plus post-hoc heuristic checks (tool usage distribution).
- E2E benchmarks: latency and token cost per route vs v1.3.
- Persistence verification: interactions, task_state, step_outputs, router_decisions records present and consistent.

### Risk mitigation strategies
- Feature flags, shadow logging, conservative defaults (PLANNER fallback).
- Strict validators for plan JSON and tool instruction schemas.
- Bounded retries with clear user-facing errors and rollbacks.
- Keep v1.3 as hot fallback through initial v2 release.
- Add telemetry to identify misroutes and failed steps for quick iteration.

---

## 4) Concerns and Gotchas

- **Clean break from fragmented memory**
  - Today v1.3 has: db_logger.py (session_logs.db), filesystem_context.py, history_store.py (history.db), event_memory.py (JSONL files)
  - v2.0 approach: Build ONE new memory/ module with ONE orchestrator.db database
  - Old systems: Reference for schema ideas only, do NOT reuse code
  - Migration: Old v1.3 data remains in old DBs for historical reference; v2.0 starts fresh
  - Rationale: Clean unified architecture is more important than preserving old fragmented data

- **Tool schema drift**
  - Agent B depends on accurate tool schemas. tools.py is large and evolving; subtle changes can break LLM assumptions.
  - Guardrail: Generate tool schema snapshot for prompts; add schema checksum to interactions for traceability.

- **Planner JSON complexity**
  - Overly complex schemas encourage invalid outputs. Keep plan schema very small and constrained.
  - Guardrail: Provide examples in system prompt; enforce short rationales; single-step pilot allowed when obvious.

- **Intention cache false positives**
  - FTS matching can spuriously hit. Threshold must be conservative; prefer "no cache" to bad cache.
  - Guardrail: Require success_flag=1, high score, and stable tool args; log near-miss candidates for offline review.

- **Role cross-contamination**
  - Using one LLM across roles risks prompt bleed if context not carefully isolated.
  - Guardrail: Fresh per-call messages with role-specific system prompts; minimal and targeted context injection via MemoryFacade; no reuse of previous role messages.

- **Token and latency budgets**
  - Planner/Executor loops can inflate costs.
  - Guardrail: Limit steps, compress context (last 3 step outputs), emphasize shell-first in prompts.

- **Shell integration is critical**
  - Philosophy: "In AI We Trust" - minimize restrictions on shell execution
  - The AI has full filesystem, network, and sudo access by design
  - Shell commands are 50%+ of user interactions - must be fast and unrestricted
  - Interactive commands (vim, top, etc.) must work seamlessly with TTY forwarding
  - Working directory: Tools execute in ai-terminal-wd/ but can access entire filesystem if needed

- **Backend heterogeneity (MiniMax/Kimi/custom)**
  - Ensure embeddings/ML optional; no dependency on providers that may not be available.
  - Guardrail: MVP avoids embeddings; FTS-based intention cache only.

- **Error handling loops**
  - Infinite "retry for valid JSON" loops.
  - Guardrail: Single retry for invalid JSON, then surface error.

- **Concurrency**
  - Concurrent orchestration cycles could collide in memory tables.
  - Guardrail: Use orchestration cycle IDs; include session_id and cycle_id on all records; keep updates transactional.

---

## 5) Specifications and Contracts

### 5.1 Orchestration cycle
- OrchestrationCycle
  - cycle_id: UUID
  - session_id: from DBLogger/MiniAgent
  - created_at, route, status: pending|running|completed|failed

### 5.2 Unified Database Schema (orchestrator.db)

All tables in ONE database file: `logs/orchestrator.db`

**Session tracking:**
- sessions
  - id (pk), created_at, system_info_json, model, last_activity_at

**Router tables:**
- router_decisions
  - id (pk), session_id, cycle_id, query_text, route, confidence (real), rules (json), cache_hit_tool (text), cache_hit_args_json (text), created_at
- intention_cache
  - id (pk), user_query_text (text), normalized_intent (text), tool_name (text), tool_args_json (text), success_flag (int), usage_count (int), last_used_at (timestamp)
  - FTS5 index on (user_query_text, normalized_intent)

**Interaction logging (all roles):**
- interactions
  - id (pk), cycle_id, role (A|B|C), system_prompt_checksum, prompt_preview, response_preview, token_usage_json, latency_ms, created_at

**Route-specific tables:**
- task_state (for [PLANNER] route)
  - id (pk), cycle_id, plan_json, status (pending|in_progress|done|error), current_step_id, created_at, updated_at
- step_outputs (for [PLANNER] route)
  - id (pk), cycle_id, step_id, tool_name, tool_args_json, success (int), exit_code (int), output_preview, artifact_path (nullable), created_at
- chat_history (for [CHAT] route)
  - id (pk), session_id, timestamp, user_text, agent_text, cycle_id (nullable)

**Trace logging (replaces old openai_traces):**
- llm_traces
  - id (pk), trace_id, cycle_id, role, request_json, response_json, created_at

### 5.4 Planner (Agent A) — plan JSON schema (conceptual)
```json
{
  "objective": "string",
  "steps": [
    {
      "id": "string",
      "title": "string",
      "rationale": "string",
      "expected_output": "string",
      "constraints": ["string"],
      "tool_hint": "string"
    }
  ]
}
```
- Constraints:
  - ≤ 6 steps, short titles/rationales
  - tool_hint limited to known tool names or "shell pipeline"

### 5.5 Executor (Agent B) — instruction contract
```json
{
  "tool": "string (must exist in TOOLS)",
  "arguments": "object (keys must match tool schema)",
  "notes": "string (≤ 200 chars)"
}
```
- On failure, Agent B may return "correction" instruction once, otherwise stop.

### 5.6 Agent C modes
- **Chat Mode**: input = user query + last 10 chat messages (MemoryFacade), output = answer string
- **Narrator Mode**: input = user query + raw tool output preview, output = narrative
- **Summarizer Mode**: input = user query + plan summary + step_outputs summaries, output = summary string

### 5.7 Configuration (env)
- ROUTER_CACHE_THRESHOLD=0.85 (similarity threshold for intention cache hits)
- ORCHESTRATOR_VERBOSE=0|1 (log detailed routing decisions)
- ROUTER_MAX_PLAN_STEPS=6 (limit plan complexity)

### 5.8 Success metrics to monitor
- Router route distribution and accuracy (manual labeled set)
- Plan JSON validity rate
- Executor success rate per step
- Token and latency per route
- Cache hit rate and correctness

---

## 6) bd Issue Breakdown (Seeds)

Create these as top-level epic with features/tasks:

- **epic**: "v2.0 Multi-Role Orchestrator Architecture" (p0)
  - **feature**: "Phase 0: Memory module and schema" (p1)
    - Deliverables: memory/ module, schema migrations, LLMClient, ToolExecutor
    - Success: migrations run; memory CRUD works; helpers tested
    - Tests: unit tests for memory operations, LLM client, tool executor
  
  - **feature**: "Phase 1: Router MVP implementation" (p1)
    - Deliverables: router/ module, RuleEngine, IntentionCache, Router, CLI tool
    - Success: router classifies queries correctly; CLI tool works; tests pass
    - Tests: regex rule tests, FTS cache tests, integration tests with sample queries
  
  - **feature**: "Phase 2: Orchestrator with Agent C routes" (p1)
    - Deliverables: orchestrator/ module, Agent C prompts, [CHAT]/[CACHED] handlers, main.py integration
    - Success: terminal works with simple queries; router → LLM → display pipeline functional
    - Tests: e2e tests for chat queries, cached command execution
  
  - **feature**: "Phase 3: Planner (Agent A) with plan validation" (p1)
    - Deliverables: Agent A prompt, plan JSON schema, validator, task_state persistence
    - Success: >90% valid plans on first try; retry works; plans stored correctly
    - Tests: plan generation tests, validation tests, retry logic tests
  
  - **feature**: "Phase 4: Executor (Agent B) with step loop" (p1)
    - Deliverables: Agent B prompt, step execution loop, retry policy, step_outputs persistence
    - Success: 3 representative complex tasks work e2e; shell-first enforced; no unnecessary Python sandbox
    - Tests: e2e tests for file operations, HTTP requests, shell pipelines
  
  - **task**: "Phase 5: Cleanup and documentation" (p2)
    - Deliverables: remove old agent.py code, update README, add Router tuning docs, telemetry
    - Success: clean codebase; documentation accurate; metrics visible
    - Tests: manual review of codebase; documentation review
  
  - **feature**: "Phase 6: Optional ML router classifier" (p3, deferred)
    - Deliverables: ML classifier integration, training pipeline, A/B comparison
    - Success: ≥5–10% accuracy improvement on ambiguous queries
    - Tests: held-out test set evaluation

Each bd issue should include:
- Dependencies: links to prior phase issues (use `--deps` flag)
- Acceptance criteria: specific, testable outcomes
- Test commands: how to verify the feature works
- Implementation notes: reference to IMPLEMENTATION_PLAN.md sections

---

## 7) Rationale and Trade-offs

### Why minimal guardrails ("In AI We Trust")?
- The AI is the trusted agent executing on behalf of the user
- Artificial restrictions create friction and reduce utility
- User has full control via their prompts; AI should not second-guess
- Philosophy: Enable, don't restrict

### Why shell-first architecture?
- Shell commands are 50%+ of real-world usage
- Users expect shell commands to execute immediately, not through planning layers
- Fast-path shell execution preserves the feel of a real terminal
- Interactive commands (vim, top) must work seamlessly with TTY

### Why FTS-based intention cache first?
- Zero new dependencies; good precision with conservative thresholds; improves with data
- Shell commands naturally cache well (repeated patterns)

### Why a single LLM in roles?
- Aligns with architecture doc, reduces complexity and cost; prompts can be tightly tailored per role

### Alternative (not chosen now)
- Full rewrite around a new orchestrator core extracting all logic out of agent.py.
  - Pros: cleaner separation from day one.
  - Cons: high regression risk and slower delivery; unnecessary until v2 is validated.

---

## 8) Risks and Guardrails

- **Misroutes causing wrong behavior**
  - Guardrail: conservative default to [PLANNER]; telemetry on misroutes; review loops.
- **Invalid Planner JSON**
  - Guardrail: schema validation + single retry + rollback to v1.3 for that cycle.
- **Tool misuse by Agent B**
  - Guardrail: strict schema enforcement; block unregistered tools; sandbox guardrails.
- **Cost/latency creep**
  - Guardrail: role-specific minimal contexts; limit steps; cache wins: [CACHED] requires zero LLM calls.
- **Memory inconsistency**
  - Guardrail: cycle_id everywhere; transactional writes; dual-write toggles during transition.

---

## 9) When to Consider the Advanced Path

Trigger points for ML router and deeper refactors:
- ≥2–3% of queries misrouted in labeled audits or substantial ambiguity in domains the rules can't capture.
- Sub-80% first-try plan validity despite prompt tuning.
- Significant cache growth with diminishing FTS precision.
- Need for parallel executions, long-running tasks, or streaming tool outputs requiring richer orchestrator state machines.

### Optional advanced path (brief)
- ML router: DistilBERT fine-tune with router_decisions data; integrate as Stage 3 before fallback.
- Single-DB enforcement: migrate event/history/db_logger into one schema, add views for backward compatibility, then remove legacy writers.
- Parallel step execution: orchestrator DAG support with explicit dependencies; out of scope for v2.0.

---

## 10) Acceptance Test Matrix (initial)

### Router
- Q: "What is the capital of Japan?" → [CHAT], confidence > 0.9
- Q: "ls -la" → [CACHED] or shell fast-path, executes immediately
- Q: "grep TODO *.py | wc -l" → [CACHED] or shell fast-path, executes immediately
- Q: "vim main.py" → Interactive handler, launches immediately
- Q: "Show command history" with seeded cache → [CACHED], correct tool args run, zero LLM calls pre-narration
- Q: "Show newest 5 .txt files in /docs sorted by size" → [PLANNER] (only if complex interpretation needed)

### Agent C
- Chat: simple Q&A; last 10 messages injected; no tools used.
- Narrator: convert ls output into a human summary with counts.
- Summarizer: summarize multi-step execution with key results.

### Planner/Executor
- Files pipeline: "List .py files changed in last 24h and sort by size desc; save to output.txt"
- HTTP: "Fetch JSON from URL and show top 3 items by score"
- Filesystem: "Create folder logs/ and write a summary file"

### Persistence
- router_decisions, interactions, task_state, step_outputs populated; cycle_id consistent.

---

## Effort Summary
- Phase 0: M (1.5–2d) - Foundation (unified memory system, helpers)
- Phase 1: S-M (0.5–1d) - Router
- Phase 2: M (1–2d) - Orchestrator + Agent C
- Phase 3: M (1–2d) - Agent A Planner
- Phase 4: L (2–3d) - Agent B Executor
- Phase 5: S-M (0.5–1d) - Polish
- **Total: ~7.5–11.5 days**

Phase 6 (ML router) is optional and deferred.

**Note**: Phase 0 is critical - building ONE unified memory system correctly sets the foundation for everything else. Do not rush this phase.

### Signals to revisit design
- High misrouting rates after threshold tuning (>10% misclassified)
- Persistent invalid plan outputs (>10% failure rate after retry)
- Tool misuse not fixed by prompt/schema enforcement
- Performance worse than v1.3 for simple queries

---

**End of document.**
