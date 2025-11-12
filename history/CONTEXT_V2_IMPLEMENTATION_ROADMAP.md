# Context v2: Institutional Memory Implementation Roadmap

**Status**: Ready to implement  
**Architecture Reviewed**: ✅ Oracle-approved  
**Branch**: `feature/context-v2-institutional-memory`  
**Total Effort**: ~11–13 hours  
**Phases**: 11 (0-11)  
**Risk Level**: LOW (additive changes, feature-flagged, easy rollback)

---

## Quick Reference: Oracle's Recommendations

### ✅ Approved Approach
- **System Prompt** = Environmental context (date, OS, tools, interpreters, database schema)
- **User Messages** = Conversational context (chat history, step outputs, task state)
- **search_db Tool** = Enum-based (no raw SQL), FTS5-backed, session-scoped by default

### 📊 Expected Gains
- **Token Efficiency**: ~2.3k–3.9k tokens/cycle (~25–35% reduction)
- **Agent Learning**: Real institutional memory via FTS5 queries + Agent A trigger heuristics
- **Execution Speed**: No mandatory context tool overhead
- **Debuggability**: Clear separation of environment vs conversation

### ⚠️ Critical Guardrails
1. **Never expose raw SQL** in search_db
2. **Don't bloat system prompts** - hard cap, terse inventory
3. **Only include shell_cwd** if ToolExecutor maintains state
4. **Verify memory.log_interaction()** existence (hidden dependency)
5. **Default to session-scoped** searches, require explicit "global" flag
6. **No prompt injection** from DB content

---

## Phase Breakdown

### Phase 0: Dependency Verification (1 hour)
**Bead**: `ai-terminal-u26m`

**Task**: Verify foundational assumptions
- [ ] Check if `memory.log_interaction()` method exists in memory/api.py
- [ ] Check if `interactions` table exists in orchestrator.db schema
- [ ] Verify `sessions.system_info_json` field (or create new system_info table if needed)
- [ ] Check LLMClient calls to memory logging (verify method signature)

**Deliverable**: Verified dependencies or patches to add missing methods/tables

**Related**: All subsequent phases depend on this

---

### Phase 1a: Build SystemContextBuilder (4–5 hours)
**Bead**: `ai-terminal-i6ij`

**Task**: Create reusable context composition helper
- [ ] Create `orchestrator/system_context_builder.py`
- [ ] Implement `SystemContextBuilder` class that:
  - Retrieves session system_info_json from database (one-time snapshot per session)
  - Detects current system state: date, OS, working_directory
  - Reads tool registry (names + descriptions)
  - Detects available interpreters (python, node, ruby, bash, perl)
  - Includes sandbox configuration flags
  - Composes schema summary string (minimal, terse)
  - **Does NOT include**: Full DB schema, all tool schemas, long examples

**Code Structure**:
```python
class SystemContextBuilder:
    def __init__(self, memory: Memory):
        self.memory = memory
    
    def build_for_role(self, role: str, session_id: str, shell_cwd: Optional[str] = None) -> str:
        """Generate role-specific system context"""
        # Fetch cached session system_info_json
        # Compose context for role A, B, or C
        # Return formatted system message
```

**Testing**: Unit tests in tests/test_system_context_builder.py
- Verify all fields present
- Verify interpreter detection
- Verify no prompt bloat (< 1000 tokens)

**Deliverable**: SystemContextBuilder class, unit tests, ready for wiring

---

### Phase 1b: Wire SystemContextBuilder into Orchestrator (1 hour)
**Bead**: `ai-terminal-0sfh`  
**Depends on**: Phase 1a

**Task**: Update Orchestrator to use dynamic system prompts
- [ ] Update `orchestrator/orchestrator.py`:
  - In `_handle_chat_route()`, `_handle_shell_route()`, `_handle_planner_route()`:
    - Call SystemContextBuilder before LLM calls
    - Inject system context as first message
    - Remove get_context tool calls from agent prompts
- [ ] Update LLMClient calls to accept pre-built system prompt
- [ ] Ensure system context is consistent across A/B/C in same cycle

**Testing**: Integration tests in tests/test_orchestrator_context.py
- Verify system context injected in all routes
- Verify no get_context tool calls (for routes using new path)
- Verify context is correct

**Deliverable**: Orchestrator wired to use SystemContextBuilder

---

### Phase 2a: Add FTS5 Indexes (2–3 hours)
**Bead**: `ai-terminal-0uy5`

**Task**: Create FTS5 virtual tables for efficient searching
- [ ] Update `memory/schema.py`:
  - Create FTS5 virtual table `chat_history_fts` (mirrors chat_history with indexed query + response)
  - Create FTS5 virtual table `step_outputs_fts` (mirrors step_outputs with indexed output_preview + intent)
  - Add triggers to auto-sync inserts/updates to FTS tables
- [ ] Add indexes for common filters (session_id, cycle_id, created_at)
- [ ] Create migration script to add FTS tables to existing databases

**Testing**: Unit tests in tests/test_memory_fts.py
- Verify FTS tables created
- Verify triggers fire on insert/update
- Verify sync is correct

**Deliverable**: FTS tables, migration script, unit tests

---

### Phase 2b: Implement Memory Search Methods (2–3 hours)
**Bead**: `ai-terminal-uo0b`  
**Depends on**: Phase 2a

**Task**: Add query methods to Memory API
- [ ] Add to `memory/api.py`:
  - `memory.search_chat_history(session_id, query, limit=5, min_success=True)` → FTS5 on chat_history_fts
  - `memory.search_step_outputs(session_id, query, limit=5, success_only=True)` → FTS5 on step_outputs_fts
  - Both return structured dicts: `[{id, source_table, snippet, score, session_id, created_at}]`
- [ ] Reuse existing `search_intention_cache()` logic (already BM25-backed)

**Testing**: Unit tests in tests/test_memory_search.py
- Verify FTS queries return ranked results
- Verify session scoping works
- Verify success filtering works

**Deliverable**: Search methods, unit tests

---

### Phase 2c: Implement search_db Tool (3–4 hours)
**Bead**: `ai-terminal-q2sh`  
**Depends on**: Phase 2b

**Task**: Build safe, enum-based database query tool
- [ ] Create `tools/search_db_tool.py`:
  - Tool name: `search_db`
  - Params:
    - `query_type`: enum ("fts5" | "sql") → only FTS5 supported in MVP
    - `search_query`: sanitized FTS search string
    - `tables`: enum list of targets (intention_cache, chat_history, step_outputs, task_state)
    - `limit`: max results (clamped to 20)
    - `session_filter`: enum ("current" | "all" | "<session_id>") → default "current"
  - Calls Memory methods (search_intention_cache, search_chat_history, search_step_outputs)
  - Returns structured results with source + metadata
  - **Validates**: FTS strings are safe, no raw SQL injection
- [ ] Register in tools.py with proper schema

**Testing**: tests/test_search_db_tool.py
- Verify enum validation works
- Verify FTS queries are safe (no injection)
- Verify session scoping enforced
- Verify results are structured

**Deliverable**: search_db tool, schema, tests

---

### Phase 3: Add Agent A Heuristics (30 min)
**Bead**: `ai-terminal-729q`  
**Depends on**: Phase 2c

**Task**: Trigger Agent A to query institutional memory
- [ ] In Agent A prompt, add guidance:
  - "When planning unfamiliar task types, use search_db to learn from past successes"
  - "If confidence in approach < 60%, search for similar past executions"
  - "Query intention_cache for similar user requests"
- [ ] Add examples of good search_db queries in Agent A prompt
- [ ] Agents decide **when** to search (In AI We Trust approach)

**Testing**: Integration test in tests/test_agent_a_learning.py
- Verify Agent A can call search_db
- Verify heuristic triggers appropriately

**Deliverable**: Agent A prompt updates, integration tests

---

### Phase 4: Lean Agent Prompts (1–2 hours)
**Bead**: `ai-terminal-f5xj`

**Task**: Optimize prompt templates for token efficiency
- [ ] Update `orchestrator/prompts.py`:
  - **Agent A**: Remove long examples, keep 1 short example or none
  - **Agent B**: Include only **current step's tool schema**, not all tools
    - Use parameter `current_tool_only: bool = True`
    - Pass just the step's tool definition, not the full tool registry
  - **Agent C**: Remove redundant context (now in system prompt)
- [ ] Add constants for prompt token budgets (soft limits for monitoring)

**Testing**: Prompt validation in tests/test_lean_prompts.py
- Verify prompts are < 2000 tokens (without conversation)
- Verify Agent B gets correct tool schema for current step
- Verify all agents have necessary context

**Deliverable**: Lean prompts, tests

---

### Phase 5: Feature Flags (2 hours)
**Bead**: `ai-terminal-j22f`

**Task**: Add safe rollback path via configuration
- [ ] Update `config.py`:
  - Add env vars:
    - `CONTEXT_V2_ENABLED` (default: false)
    - `SEARCH_DB_ENABLED` (default: false)
    - `PROMPT_LEAN_MODE` (default: false)
- [ ] Update Orchestrator to check flags:
  - If `CONTEXT_V2_ENABLED=false`: Use old system prompts (backward compatible)
  - If `SEARCH_DB_ENABLED=false`: search_db tool not registered
  - If `PROMPT_LEAN_MODE=false`: Include all tool schemas in Agent B (old behavior)
- [ ] Rollout strategy: Enable CHAT route first, then SHELL, then PLANNER

**Testing**: Feature flag tests in tests/test_feature_flags.py
- Verify old behavior when flags off
- Verify new behavior when flags on
- Verify mixed scenarios

**Deliverable**: Feature flags, config updates, tests

---

### Phase 6: Metrics & Logging (1–2 hours)
**Bead**: `ai-terminal-quoa`  
**Depends on**: Phase 5

**Task**: Instrument for observability
- [ ] Update `orchestrator/metrics.py`:
  - Add `SearchDBMetrics` class:
    - search_db usage count
    - hit rate (queries → results returned)
    - avg result score
    - session scoping (cross-session queries logged separately)
  - Add search_db call logging
- [ ] Log system context composition time
- [ ] Log prompt token counts per role (compare before/after)

**Testing**: Metrics tests in tests/test_context_metrics.py
- Verify metrics are recorded
- Verify hit rate calculation correct

**Deliverable**: Metrics, logging, tests

---

### Phase 7: Database Migrations (1–2 hours)
**Bead**: `ai-terminal-9wwd`  
**Depends on**: Phase 2a

**Task**: Safe schema evolution
- [ ] Create `memory/migrations.py`:
  - Migration 001: Add FTS5 tables for chat_history, step_outputs
  - Migration 002: Add interactions table (if missing from Phase 0)
  - Migration 003: Add schema_versions tracking
- [ ] Implement rollback for each migration
- [ ] Add one-shot initialization in init_db()

**Testing**: Migration tests in tests/test_migrations.py
- Verify migrations apply cleanly
- Verify rollback works

**Deliverable**: Migrations, rollback scripts

---

### Phase 8: SystemContextBuilder & Prompts Testing (1–2 hours)
**Bead**: `ai-terminal-u3ma`  
**Depends on**: Phase 1b, 4

**Task**: Comprehensive testing of new context system
- [ ] Unit tests:
  - SystemContextBuilder composition
  - Context field accuracy
  - Prompt formatting
- [ ] Integration tests:
  - Full CHAT route with new context
  - Full SHELL route with new context
  - Full PLANNER route with new context
  - Verify agents don't call get_context (it's gone)
- [ ] Smoke tests:
  - Run 10 realistic queries
  - Verify no errors, correct responses

**Deliverable**: Passing tests, coverage report

---

### Phase 9: search_db Tool Testing (2 hours)
**Bead**: `ai-terminal-u4rt`  
**Depends on**: Phase 2c

**Task**: Comprehensive testing of institutional memory
- [ ] Unit tests:
  - Enum validation
  - FTS query safety
  - Session scoping
  - Result formatting
- [ ] Security tests:
  - Injection attempts blocked
  - Cross-session queries properly gated
  - Rate limiting (optional)
- [ ] Integration tests:
  - Agent A calls search_db and uses results
  - Results improve planning quality

**Deliverable**: Passing tests, security report

---

### Phase 10: End-to-End Regression Testing (2 hours)
**Bead**: `ai-terminal-zy3d`  
**Depends on**: Phases 1–9

**Task**: Verify 65/65 tests still pass
- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Verify zero regressions
- [ ] Verify new tests all pass
- [ ] Check token efficiency improvements (sampling)
- [ ] Check latency (search_db + SystemContextBuilder overhead)

**Success Criteria**:
- 65+ tests passing (new + old)
- Zero regressions
- Token usage down by ~25–35%
- Latency < 10% regression

**Deliverable**: Test report, metrics

---

### Phase 11: Documentation & Rollback (2 hours)
**Bead**: `ai-terminal-nl1a`  
**Depends on**: Phase 10

**Task**: Complete documentation and define escape hatch
- [ ] Update README.md:
  - Remove get_context from tool list
  - Explain dynamic system prompts
  - Document search_db tool
  - Add feature flag instructions
- [ ] Update AGENTS.md:
  - Document what context each agent receives
  - Remove get_context references
  - Add search_db examples
- [ ] Create CONTEXT_V2_MIGRATION.md:
  - Feature flags for safe rollout
  - Rollback procedure
  - Troubleshooting guide
  - Performance monitoring instructions

**Rollback Procedure** (if issues):
1. Disable all feature flags: `CONTEXT_V2_ENABLED=false`, `SEARCH_DB_ENABLED=false`, `PROMPT_LEAN_MODE=false`
2. Orchestrator reverts to old behavior (get_context tool still available)
3. search_db tool not registered (invisible to agents)
4. FTS tables remain in DB (harmless, or run migration rollback)
5. Can investigate issues with metrics/logging

**Deliverable**: Updated docs, migration guide, rollback procedure

---

## Dependencies & Critical Path

```
Phase 0 (verify)
  ↓
Phase 1a (SystemContextBuilder)
  ↓
Phase 1b (wire into Orchestrator)
  ↓ 
Phase 4 (lean prompts) [parallel with Phase 2]
Phase 2a (FTS indexes) [parallel with Phase 4]
  ↓
Phase 2b (Memory search methods)
  ↓
Phase 2c (search_db tool)
  ↓
Phase 3 (Agent A heuristics)
  ↓
Phase 5 (feature flags)
  ↓
Phase 6 (metrics)
Phase 7 (migrations)
  ↓
Phase 8 (context testing)
Phase 9 (search_db testing)
  ↓
Phase 10 (E2E regression)
  ↓
Phase 11 (docs + rollback)
```

**Critical Path**: 0 → 1a → 1b → 4, 2a → 2b → 2c → 3 → 5 → 6,7 → 8,9 → 10 → 11
**Parallelizable**: Phase 4 + Phase 2a can run in parallel; Phase 8 + Phase 9 can run in parallel

---

## Success Criteria

### Functional
- [ ] Agents receive environmental context in system prompt
- [ ] Agents can query institutional memory via search_db tool
- [ ] Agent A learns from past executions (search_db trigger heuristics)
- [ ] get_context tool disabled (but code preserved)
- [ ] All 65 tests pass, zero regressions

### Performance
- [ ] Token usage reduced by ~25–35% per cycle
- [ ] Latency impact < 10% (system context builder overhead)
- [ ] search_db queries return results in < 100ms

### Safety & Maintainability
- [ ] Feature flags allow safe rollout
- [ ] Rollback procedure verified
- [ ] No SQL injection in search_db
- [ ] Session scoping enforced by default
- [ ] Comprehensive logging/metrics

### Documentation
- [ ] README updated
- [ ] AGENTS.md updated
- [ ] Migration guide created
- [ ] Troubleshooting guide included

---

## Timeline Estimate

- **Phase 0**: 1h
- **Phase 1a–1b**: 5h
- **Phase 2a–2c**: 7–8h
- **Phase 3**: 0.5h
- **Phase 4**: 1–2h
- **Phase 5**: 2h
- **Phase 6**: 1–2h
- **Phase 7**: 1–2h
- **Phase 8–9**: 3–4h
- **Phase 10**: 2h
- **Phase 11**: 2h

**Total**: 11–13 hours (distributed across days)

---

## Rollout Strategy

### Stage 1: Dev/Test (All Phases)
- Implement all phases on feature branch
- Run full test suite
- Verify zero regressions

### Stage 2: Feature Flag Rollout (Internal Testing)
- Deploy with all flags OFF (backward compatible)
- Enable flags one route at a time: CHAT → SHELL → PLANNER
- Monitor metrics, gather feedback

### Stage 3: Production (if no issues)
- Enable CONTEXT_V2_ENABLED=true for trusted users
- Keep SEARCH_DB_ENABLED=false initially (agents can't call yet)
- Monitor for 1 week

### Stage 4: Institutional Memory (if stable)
- Enable SEARCH_DB_ENABLED=true
- Agents can now query historical context
- Monitor hit rate, quality of searches

### Emergency Rollback
- Set all feature flags to false
- Disable search_db tool
- Revert to old system prompts (still available)
- Investigate with metrics/logging

---

## Known Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Prompt bloat causing token explosion | Hard cap in SystemContextBuilder, terse inventory, no long examples |
| Stale shell_cwd misleading agent | Only include if ToolExecutor maintains state; otherwise omit |
| FTS queries too slow | Index step_outputs and chat_history on creation; test with realistic data |
| SQL injection via search_db | Enum-based targets only, sanitized FTS inputs, no raw SQL |
| Cross-session data leakage | Default session-scoped, explicit "all" requires trusted flag |
| memory.log_interaction missing | Phase 0 verification catches this early |
| Regression in test suite | Comprehensive testing in Phases 8–10 |

---

## Next Steps

1. **Claim Phase 0**: `bd update ai-terminal-u26m --status in_progress`
2. **Start verification**: Check dependencies
3. **Plan parallelization**: Phases 1a + 2a can run in parallel
4. **Daily commits**: After each phase, commit and push
5. **Track progress**: `bd ready` shows what's next

---

**Created**: 2025-11-12  
**By**: Amp (Rush Mode) + Oracle Review  
**Status**: Ready to implement
