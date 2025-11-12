# Schema Decision: cycle_id Pattern (No orchestrator_state Table)

**Decision Date**: 2025-11-11  
**Status**: ✅ APPROVED  
**Issue**: ai-terminal-dqve

## Decision

**Use cycle_id as primary orchestration coordinator. Do NOT create orchestrator_state table.**

## Schema Pattern

Every user query generates a unique `cycle_id` (UUID). All tables reference this ID:

```sql
-- Core cycle tracking
sessions (id, session_id, created_at, model, system_info_json, last_activity_at)
router_decisions (id, session_id, cycle_id, query_text, route, confidence, ...)

-- Interaction logging (all roles A/B/C)
interactions (id, cycle_id, role, system_prompt_checksum, response_preview, ...)

-- Route-specific state
task_state (id, cycle_id, plan_json, status, current_step_id, ...)
step_outputs (id, cycle_id, step_id, tool_name, output_preview, ...)
chat_history (id, cycle_id, user_query, agent_response, timestamp)
intention_cache (id, user_query_text, tool_name, tool_args_json, ...)
```

## Orchestration State Queries

**Current cycle phase:**
```sql
SELECT rd.route, ts.status 
FROM router_decisions rd
LEFT JOIN task_state ts ON rd.cycle_id = ts.cycle_id
WHERE rd.cycle_id = ?
```

**Session idle state:**
```sql
SELECT last_activity_at FROM sessions WHERE id = ?
```

**Multi-step progress:**
```sql
SELECT current_step_id, status FROM task_state WHERE cycle_id = ?
```

## Rationale

### Why NOT orchestrator_state:

1. **Redundant**: cycle_id + timestamps already track flow
2. **IMPLEMENTATION_PLAN doesn't include it**: Section 5.2 unified schema omits the table
3. **Simpler queries**: No JOIN needed for basic state lookups
4. **Indexed cycle_id**: Fast lookups across all tables
5. **Transactional integrity**: Less write contention (no central state table lock)

### Benefits of cycle_id pattern:

- ✅ Immutable cycle tracking (UUID never changes)
- ✅ Distributed state (each table owns its concern)
- ✅ Simpler schema (8 tables instead of 9)
- ✅ Faster writes (no orchestrator_state bottleneck)
- ✅ Natural partitioning (route-specific tables only written when needed)

### When to add orchestrator_state (future):

If we need:
- Complex orchestration state machines (pause/resume/cancel)
- Multi-tenancy with cycle ownership
- Distributed orchestrator nodes (horizontal scaling)

**For MVP: cycle_id pattern is sufficient.**

## Implementation Impact

### Memory Module (ai-terminal-wjt)
- Create 8 tables (not 9): sessions, router_decisions, intention_cache, interactions, task_state, step_outputs, chat_history, llm_traces
- Index cycle_id on all relevant tables for fast queries
- Orchestrator.get_cycle_state() queries router_decisions + task_state

### Orchestrator (Phase 2)
- Generate cycle_id at start of Orchestrator.handle_query()
- Pass cycle_id to all Memory API calls
- Query current state via Memory.get_router_decision(cycle_id) + Memory.get_task_state(cycle_id)

### Cross-Route Context (Phase 2)
- Chat → Planner: Query chat_history WHERE session_id = ? ORDER BY timestamp DESC LIMIT 3
- Planner → Chat: Query task_state + step_outputs WHERE cycle_id = ? (previous cycle)

## Documentation Updates

- ✅ IMPLEMENTATION_PLAN.md §5.2: Already uses cycle_id pattern (no change needed)
- ⚠️ DOUBLE_AGENT_ARCHITECTURE.md §Memory Management (line 369): Remove orchestrator_state reference
- ✅ This decision doc (SCHEMA_DECISION.md): Created

## Next Steps

1. Close ai-terminal-dqve with this decision doc
2. Proceed to ai-terminal-wjt (unified memory implementation)
3. Implement 8-table schema with cycle_id indexes
4. Update DOUBLE_AGENT_ARCHITECTURE.md to align with this decision

---

**Approved By**: Implementation Lead (AI)  
**Reviewed**: Oracle verification (GPT-5 reasoning) recommended this decision  
**Status**: Ready for implementation
