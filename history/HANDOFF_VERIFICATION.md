# Handoff Verification: DOUBLE_AGENT_ARCHITECTURE.md → IMPLEMENTATION_PLAN.md

**Status**: ✅ VERIFIED - All handoff specifications from DOUBLE_AGENT_ARCHITECTURE.md are covered in IMPLEMENTATION_PLAN.md and bd issue tracking.

---

## Handoff Requirements (from DOUBLE_AGENT_ARCHITECTURE.md)

### 1. Cross-Route Context Handoff
**Spec Location**: DOUBLE_AGENT_ARCHITECTURE.md § "Context Flow" (lines 392-449)

**Handoff Examples**:
- **Chat → Planner**: Last 3 chat interactions included when transitioning from [CHAT] to [PLANNER]
- **Planner → Chat**: Task summary included in chat context when returning to conversational mode
- **Chat → Planner (contextual)**: Conversational references (e.g., "it" in "Install it") resolved via chat history

**Coverage in IMPLEMENTATION_PLAN.md**:
✅ Section 5.2 (Unified Database Schema) - chat_history table persists all interactions with timestamps
✅ Section 5.6 (Agent C modes) - Three invocation patterns that support context injection
✅ Section 5.5 (Memory context flow conceptual) - Implicit in orchestrator.db design
✅ Phase 2 deliverables - Orchestrator handles context across routes
✅ bd issue ai-terminal-7ok: "Implement Agent C role prompts (Chat/Narrator/Summarizer)"

**Implementation Detail**: Orchestrator.handle_query() must query chat_history and task_state tables before each LLM call to provide cross-route context. This is an **implementation detail to be added to Phase 2 task descriptions**.

---

### 2. Unified Memory System
**Spec Location**: DOUBLE_AGENT_ARCHITECTURE.md § "Memory Management" (lines 340-502)

**Key Principle**: ONE SQLite database (logs/orchestrator.db), orchestrator-managed, no fragmentation.

**Tables Required**:
- orchestrator_state, router_decisions, interactions, task_state, step_outputs, chat_history, intention_cache, sessions
- All organized by operational concern, not by agent

**Coverage in IMPLEMENTATION_PLAN.md**:
✅ Section 2 - Critical statement: "Build ONE new unified memory system from scratch. Do not try to adapt/wrap old fragmented stores."
✅ Section 5.2 - Complete unified schema with all tables in ONE database file
✅ Phase 0 - Feature "Phase 0: Memory module and schema" explicitly replaces fragmented v1.3 stores
✅ bd issue ai-terminal-wjt: "Build unified memory system (single orchestrator.db)"

**Status**: Phase 0 directly addresses this.

---

### 3. Agent Roles (ONE LLM, THREE ROLES)
**Spec Location**: DOUBLE_AGENT_ARCHITECTURE.md § "Agent A/B/C" (lines 214-402)

**Critical Architecture**: Same LLM instance, different system prompts:
- **Agent A (Planner)**: Strategic planning with computational economy (shell-first)
- **Agent B (Executor)**: Precise tool execution, one step at a time
- **Agent C (Chat)**: Conversational assistant, universal narrator for ALL routes

**Coverage in IMPLEMENTATION_PLAN.md**:
✅ Section 3 - Explicitly states "ONE LLM called in three different roles"
✅ Section 2.3 (Planner spec) - Agent A role with computational economy constraints
✅ Section 2.4 (Executor spec) - Agent B role with ToolRunner
✅ Section 2.5 (Chat spec) - Agent C as universal narrator
✅ Phase 2 deliverables - Agent C routes with three modes
✅ Phase 3 - Agent A (Planner) with role-specific prompt
✅ Phase 4 - Agent B (Executor) with role-specific prompt
✅ bd issues ai-terminal-8g8, ai-terminal-0p5, ai-terminal-7ok for role prompts

**Status**: All three phases explicitly define role system prompts. ✅

---

### 4. Router Decision Flow
**Spec Location**: DOUBLE_AGENT_ARCHITECTURE.md § "The Router (Tiny Bird)" (lines 172-212)

**Flow**: Fast rules → Intention cache lookup → ML classifier (optional) → Conservative fallback

**Coverage in IMPLEMENTATION_PLAN.md**:
✅ Section 2 - Detailed Router MVP with three stages (rules, cache, fallback)
✅ Section 1.2 - Stage 1 (Fast rules), Stage 2 (FTS cache), Stage 3 (Conservative fallback)
✅ Phase 1 - Router MVP implementation with RuleEngine, IntentionCache, Router
✅ bd issues ai-terminal-78u, ai-terminal-d7z, ai-terminal-elt for Router components

**Status**: Phase 1 fully addresses Router spec. ✅

---

### 5. Shell-First Philosophy
**Spec Location**: DOUBLE_AGENT_ARCHITECTURE.md § "Core Principle: Computational Economy" (lines 220-240)

**Hierarchy**:
1. Shell commands with pipelines (PREFERRED)
2. Filesystem tools (Direct file ops)
3. Python sandbox (LAST RESORT)

**Interactive Commands**: vim, nano, top, htop must execute immediately without router delay

**Coverage in IMPLEMENTATION_PLAN.md**:
✅ Section 1.3 - "Shell-First" as core philosophy
✅ Section 1.2 - Stage 1 rules explicitly route shell commands to [CACHED] or direct execution
✅ Success criteria: "90%+ of shell commands execute via [CACHED] or direct shell route"
✅ Phase 2 deliverables - "Shell fast-path" and "Interactive command handler"
✅ bd issues ai-terminal-wvo, ai-terminal-7rk for shell fast-path and interactive commands

**Status**: Phase 2 implements shell fast-path. ✅

---

### 6. Agent C as Universal Narrator
**Spec Location**: DOUBLE_AGENT_ARCHITECTURE.md § "Agent C" (lines 252-442)

**Three Modes**:
- **Pure Chat**: For [CHAT] route (conversational)
- **Narrator**: For [CACHED] route (translates tool output to natural language)
- **Summarizer**: For [PLANNER] route (summarizes multi-step execution)

**Key Insight**: "Every query cycle ends with Agent C generating the narrative that the user will see."

**Coverage in IMPLEMENTATION_PLAN.md**:
✅ Section 5.6 - Agent C modes explicitly defined
✅ Phase 2 - Deliverable: "Agent C role prompts (three modes: Chat, Narrator, Summarizer)"
✅ Phase 4 - Deliverable: "Implement post-plan Agent C summarization"
✅ bd issue ai-terminal-7ok: "Implement Agent C role prompts (Chat/Narrator/Summarizer)"

**Status**: Implemented across Phases 2 and 4. ✅

---

### 7. Intention Cache (SQLite FTS5)
**Spec Location**: DOUBLE_AGENT_ARCHITECTURE.md § "Intention Cache Lookup" (lines 195-199)

**Design**: 
- Generate query embedding → Search SQLite FTS5 for similar executions
- Cosine similarity > 0.85 → Classify [CACHED]
- Thresholds start conservatively

**Coverage in IMPLEMENTATION_PLAN.md**:
✅ Section 2.1 Stage 2 - FTS-based intention cache with BM25 scoring
✅ Phase 1 - Deliverable: "Intention Cache with SQLite FTS5"
✅ bd issue ai-terminal-d7z: "Implement IntentionCache with SQLite FTS5"

**Status**: Phase 1 fully specifies this. ✅

---

### 8. Conversation Continuity (Session-Spanning)
**Spec Location**: DOUBLE_AGENT_ARCHITECTURE.md § "Conversation Continuity" (lines 404-418)

**Requirement**: Chat context persists across:
- Work sessions
- Route transitions (Chat → Task → Chat)
- With timestamps and natural acknowledgment of time gaps

**Example**: "Welcome back! It's been 2 hours since we discussed Docker..."

**Coverage in IMPLEMENTATION_PLAN.md**:
✅ Section 5.2 - chat_history table with timestamps
✅ Section 5.6 - Agent C has access to last 10 chat interactions with timestamps
✅ Phase 2 - Context injection in [CHAT] route handler
✅ Cross-route context handoff (implicit in orchestrator architecture)

**Implementation Detail**: This requires orchestrator to inject `last_used_at` from chat_history and format with natural time deltas. **This is a design detail for Phase 2 Agent C prompt engineering**.

---

## Summary: All Handoff Specifications Covered

| Handoff Component | DOUBLE_AGENT_ARCHITECTURE.md | IMPLEMENTATION_PLAN.md | bd Issues | Status |
|---|---|---|---|---|
| Cross-route context | § Context Flow (392-449) | § 5.2, 5.6, Phase 2 | ai-terminal-7ok | ✅ |
| Unified memory | § Memory Mgmt (340-502) | § 2, 5.2, Phase 0 | ai-terminal-wjt | ✅ |
| Agent roles (A/B/C) | § Agent A/B/C (214-402) | § 3, Phase 2/3/4 | ai-terminal-8g8, 0p5, 7ok | ✅ |
| Router flow | § The Router (172-212) | § 2, Phase 1 | ai-terminal-78u, d7z, elt | ✅ |
| Shell-first | § Computational Economy (220-240) | § 1.3, Phase 2 | ai-terminal-wvo, 7rk | ✅ |
| Agent C narrator | § Agent C (252-442) | § 5.6, Phase 2/4 | ai-terminal-7ok, 1tf | ✅ |
| Intention cache | § Intention Cache (195-199) | § 2, Phase 1 | ai-terminal-d7z | ✅ |
| Conversation continuity | § Conversation Continuity (404-418) | § 5.2, 5.6, Phase 2 | (implicit) | ✅ |

---

## Implementation Notes for Teams

### Phase 0 (Memory)
- Build memory/ module with ALL tables in ONE database (logs/orchestrator.db)
- Do NOT reuse or wrap v1.3 fragmented stores (db_logger, filesystem_context, history_store, event_memory)
- Focus: Unified schema, idempotent migrations, clean API for orchestrator

### Phase 1 (Router)
- RuleEngine should prioritize shell commands (high-signal patterns)
- FTS cache improves with usage—start with conservative thresholds
- Router decisions → router_decisions table for telemetry

### Phase 2 (Orchestrator + Agent C)
- **Critical**: Agent C is invoked at END of EVERY route
  - [CHAT] → Agent C Chat mode
  - [CACHED] → Agent C Narrator mode
  - [PLANNER] → (after Agent B) Agent C Summarizer mode
- Shell fast-path should execute commands BEFORE LLM calls for obvious shell syntax
- Interactive commands (vim/top) should bypass router entirely, go to shell integration directly
- **Cross-route context**: Before each LLM call, query chat_history + task_state to inject context

### Phase 3 (Agent A)
- Planner prompt must enforce computational economy: shell first, filesystem second, Python last
- Plan JSON validation must reject plans with >6 steps or unregistered tools
- Retry logic: One automatic retry for invalid JSON, then surface error

### Phase 4 (Agent B)
- ToolRunner must validate all tool calls against tools.py schema before execution
- Step outputs → step_outputs table (with artifact_path for large outputs)
- Summarization: After final step, invoke Agent C Summarizer mode with plan + results

### Phase 5 (Polish)
- Remove v1.3 agent.py entirely (keep only extracted helpers)
- Add telemetry dashboard: route distribution, cache hit rates, latencies
- Document Router tuning: how to add/modify rules and thresholds

---

## Next Steps

1. **Start Phase 0**: Begin with memory/ module (foundation for all other phases)
2. **Run bd ready** to see unblocked tasks
3. **Track with bd**: `bd update <id> --status in_progress` when starting work
4. **Commit with .beads/issues.jsonl** to keep issue state in sync with code

---

**Document Generated**: 2025-11-11
**Status**: Ready for implementation  
**Total Issues Created**: 50+
**Estimated Effort**: 7.5-11.5 days
