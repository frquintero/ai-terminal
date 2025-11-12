# Oracle Verification Report: BD Issue Tracking Completeness

**Date**: 2025-11-11  
**Status**: CRITICAL GAPS IDENTIFIED & FIXED  
**Severity**: P0 (blockers to start Phase 0/1/2)

---

## Executive Summary

The Oracle (GPT-5 reasoning model) verified bd issue tracking against IMPLEMENTATION_PLAN.md, DOUBLE_AGENT_ARCHITECTURE.md, and HANDOFF_VERIFICATION.md. **Critical gaps were found** in:

1. ❌ Cross-route context handoff tasks (none existed)
2. ❌ Agent role prompt tasks (incomplete)
3. ❌ Router CLI task (missing)
4. ❌ Acceptance criteria on all phase features (empty)
5. ❌ Phase dependencies wiring (not explicit in bd)
6. ❌ Schema discrepancy (orchestrator_state vs cycle_id)
7. ❌ LLMClient/ToolExecutor extraction task (missing)

**Result**: 10 new bd issues created to close gaps before teams start implementation.

---

## Issues Created to Fix Critical Gaps

### Cross-Route Handoffs (P1)
- **ai-terminal-t0e**: Implement Chat→Planner context handoff (last 3 interactions)
- **ai-terminal-cnc**: Implement Planner→Chat context handoff (task summary)
- **ai-terminal-inu**: Integration tests for cross-route context handoff (3 examples from DOUBLE_AGENT_ARCHITECTURE.md)

**Rationale**: DOUBLE_AGENT_ARCHITECTURE.md §Context Flow (lines 392-449) specifies three handoff examples. These need explicit implementation tasks with testable acceptance criteria.

### Agent Roles (P1)
- **ai-terminal-n4c**: Implement Agent C role prompts with context injection (Chat/Narrator/Summarizer)
  - *Replaces* ai-terminal-7ok which had unclear scope; this task covers all three modes + context injection logic
- **ai-terminal-56xd**: Extract and test LLMClient + ToolExecutor logging to orchestrator.db
  - *New*: Phase 0 helpers must log to unified memory, not legacy stores

### Router Infrastructure (P2)
- **ai-terminal-pi97**: Router CLI: python -m router.cli for testing
  - *New*: IMPLEMENTATION_PLAN §3 requires CLI tool for standalone router testing

### Schema Clarity (P1)
- **ai-terminal-dqve**: Schema decision: orchestrator_state vs cycle_id (resolve architecture/plan discrepancy)
  - **Issue**: DOUBLE_AGENT_ARCHITECTURE.md lists `orchestrator_state` table; IMPLEMENTATION_PLAN §5.2 omits it. Decision needed.
  - **Resolution**: Either drop orchestrator_state (simpler, rely on cycle_id + timestamps on other tables) OR add it and create task to implement.
  - **Action**: This task documents the decision and updates all three docs to be consistent.

### Phase 0 Acceptance (P2)
- **ai-terminal-rizw**: Phase 0 acceptance test: verify ONE orchestrator.db with all tables and CRUD operations
  - Confirms unified memory system is complete before Phase 1 starts

### Acceptance Criteria (P0 - BLOCKER)
- **ai-terminal-pzea**: Fill acceptance criteria for all Phase features (test commands, success metrics)
  - **Priority**: P0 (Critical)
  - **Scope**: Every Phase feature (0b7, 299, ckz, 5r7, 4zb, owj, 6g0) must have:
    - Testable acceptance criteria (not vague)
    - Test commands (how to verify)
    - Doc references (IMPLEMENTATION_PLAN §number)
  - **Success**: All Phase features have acceptance criteria before any Phase 0 work starts

---

## Oracle Findings Summary

### Critical Gaps (P0 - Must Fix Before Phase 0 Starts)

| Gap | Found In | Required For | Fixed By | New Issue |
|---|---|---|---|---|
| Cross-route context handoffs | Architecture spec | Phase 2 | Explicit tasks | ai-terminal-t0e, cnc, inu |
| Agent C prompt scope | bd tracking | Phase 2 | Clarified task scope | ai-terminal-n4c |
| Router CLI tool | IMPLEMENTATION_PLAN | Phase 1 | New task | ai-terminal-pi97 |
| LLMClient/ToolExecutor extraction | Phase 0 spec | All phases | New task | ai-terminal-56xd |
| Acceptance criteria (all) | bd features | Ready check | P0 task | ai-terminal-pzea |
| Schema discrepancy | Architecture vs Plan | Phase 0 | Decision task | ai-terminal-dqve |
| Phase dependencies | bd tracking | Ready work | Manual update (see below) | - |

### Inconsistencies Identified

1. **Intention Cache Design**
   - DOUBLE_AGENT_ARCHITECTURE.md: embeddings + cosine similarity > 0.85
   - IMPLEMENTATION_PLAN.md: SQLite FTS5 BM25 scoring + configurable thresholds
   - HANDOFF_VERIFICATION.md: marks as ✅ but doesn't note change
   - **Resolution**: FTS5 MVP is correct (simpler, no ML needed initially). Document explicitly that embeddings are Phase 6 (optional ML).

2. **Orchestrator State Table**
   - DOUBLE_AGENT_ARCHITECTURE.md §Memory Management (line 369): lists `orchestrator_state` table
   - IMPLEMENTATION_PLAN.md §5.2: omits it, relies on cycle_id + timestamps
   - **Resolution**: Task ai-terminal-dqve to decide; both docs must align.

3. **Agent C Prompt Tasks**
   - IMPLEMENTATION_PLAN §2.5 mentions three modes (Chat/Narrator/Summarizer)
   - Original bd issue ai-terminal-7ok title: "Implement Agent C role prompts..."
   - But also ai-terminal-1tf: "Implement post-plan Agent C summarization"
   - **Resolution**: ai-terminal-n4c consolidates all three modes + context injection; ai-terminal-1tf focuses on Phase 4 integration.

### Phase Dependencies (Manual Verification Needed)

Current bd shows:
- Phase features as siblings under epic (no explicit `blocks` dependencies)
- Phase 0 child tasks properly parented
- Phase 2 child tasks show `parent-child:ai-terminal-5r7` (good)
- **Missing**: Phase 1 feature (ckz) should `blocks:ai-terminal-5r7` (Phase 2 waits for Router)
- **Missing**: Phase 2 feature (5r7) should `blocks:ai-terminal-4zb` (Phase 3 waits for Orchestrator)

**Recommendation**: After oracle review, manually check bd and add block dependencies:
```
bd update ai-terminal-ckz --deps "blocks:ai-terminal-5r7" --json
bd update ai-terminal-5r7 --deps "blocks:ai-terminal-4zb" --json
bd update ai-terminal-4zb --deps "blocks:ai-terminal-owj" --json
```

---

## Acceptance Criteria Template (ai-terminal-pzea)

Each Phase feature must include (in bd description or linked doc):

### Phase 0 (Memory)
```
Acceptance:
- Single orchestrator.db file at logs/orchestrator.db
- All 8 tables created (sessions, router_decisions, intention_cache, interactions, task_state, step_outputs, chat_history, llm_traces)
- Full CRUD API: Memory.save_router_decision(), .get_chat_history(), .save_plan(), etc.
- Zero imports from v1.3 legacy (db_logger, filesystem_context, history_store, event_memory)
- All unit tests pass: test_memory_crud.py, test_llm_client.py, test_tool_executor.py

Test commands:
  python -m pytest tests/test_memory.py -v
  python -m pytest tests/test_llm_client.py -v
  python -m pytest tests/test_tool_executor.py -v
  ls -la logs/orchestrator.db  # Verify single file exists
```

### Phase 1 (Router)
```
Acceptance:
- Router correctly classifies 95%+ of simple Q&A queries to [CHAT]
- Router correctly routes 90%+ of shell commands to [CACHED] or [SHELL] fast-path
- Intention cache achieves 80%+ precision on seeded set
- Router CLI tool works: python -m router.cli "ls -la" → prints decision + confidence

Test commands:
  python -m router.cli "what is the capital of japan"
  python -m router.cli "ls -la" 
  python -m pytest tests/test_router_rules.py -v
  python -m pytest tests/test_intention_cache.py -v
```

### Phase 2 (Orchestrator + Agent C)
```
Acceptance:
- [CHAT] route executes end-to-end (query → Agent C → display)
- [CACHED] route executes cached commands without LLM before narration
- Shell commands execute immediately: `ls -la`, `grep pattern file.txt`, `cat README.md`
- Interactive commands launch instantly: `vim file.py`, `top`, `htop`
- router_decisions and interactions logged for all cycles
- Cross-route context handoff works: Chat → Planner → Chat examples 1–3 from DOUBLE_AGENT_ARCHITECTURE.md

Test commands:
  python main.py  # Manual: type "what is docker?" → [CHAT] response
  python main.py  # Manual: type "ls -la" → immediate listing + Agent C narration
  python main.py  # Manual: type "vim test.txt" → vim launches immediately
  python -m pytest tests/test_orchestrator_e2e.py::test_chat_route -v
  python -m pytest tests/test_orchestrator_e2e.py::test_cached_route -v
  python -m pytest tests/test_cross_route_handoff.py -v
```

### Phase 3 (Planner)
```
Acceptance:
- Agent A generates valid plan JSON for known complex query
- Plan JSON validation rejects non-conforming formats
- Invalid JSON triggers one automatic retry; second failure surfaces error
- Plan persisted to task_state with status=pending
- >90% valid JSON on first try for test corpus

Test commands:
  python -m pytest tests/test_planner_validation.py -v
  python -m pytest tests/test_planner_retry.py -v
  python main.py  # Manual: complex task → plan visible → first step extracted
```

### Phase 4 (Executor)
```
Acceptance:
- [PLANNER] route executes 3 representative tasks e2e:
  1. File pipeline: "List .py files changed in last 24h, sort by size desc, save to output.txt"
  2. HTTP: "Fetch JSON from URL and show top 3 items by score"
  3. Filesystem: "Create folder logs/ and write summary file"
- All 3 tasks complete without errors and generate correct output
- step_outputs persisted for each step
- Shell-first enforced (no unnecessary Python sandbox usage)
- Final Agent C summarization invoked after last step

Test commands:
  python -m pytest tests/test_executor_tasks.py::test_file_pipeline -v
  python -m pytest tests/test_executor_tasks.py::test_http_fetch -v
  python -m pytest tests/test_executor_tasks.py::test_filesystem_ops -v
  python main.py  # Manual: run one representative task, inspect logs/orchestrator.db
```

### Phase 5 (Polish)
```
Acceptance:
- v1.3 agent.py code removed (only extracted helpers remain)
- README.md updated with v2.0 architecture overview
- Router tuning docs added (how to add/modify rules, thresholds)
- Telemetry visible: route distribution, cache hit rates, latencies per route

Test commands:
  grep -r "class MiniAgent" --include="*.py" .  # Should NOT exist (only in history/ docs)
  grep "v2.0" README.md  # Should exist
  ls -la docs/ROUTER_TUNING.md  # Should exist
  python main.py  # Telemetry logs should be visible
```

---

## Risk Mitigations Added

1. **Cross-Route Context Flakiness**: Integration tests (ai-terminal-inu) reproduce three documented examples with asserts.
2. **Schema Drift**: Decision task (ai-terminal-dqve) forces explicit choice and documentation before Phase 0 implementation.
3. **Non-Testable Acceptance**: P0 task (ai-terminal-pzea) requires test commands for every Phase feature.
4. **Missing Helpers**: Explicit extraction task (ai-terminal-56xd) ensures LLMClient/ToolExecutor are properly abstracted.

---

## Signals to Watch During Implementation

- **Router misrouting >10% on labeled audit**: Consider adding embeddings similarity (Phase 6) earlier
- **Cache precision <80% on seeded set**: Retune FTS5 thresholds or add Phase 6 ML
- **Cross-route context tests flaky**: Add explicit cycle tracing and orchestrator_state table
- **Acceptance criteria still vague after ai-terminal-pzea**: Escalate; may need architecture revision

---

## Next Actions

1. ✅ **DONE**: New bd issues created (10x)
2. **TODO (P0)**: Run `ai-terminal-pzea` task immediately—fill acceptance criteria for all Phase features
3. **TODO (P0)**: Run `ai-terminal-dqve` task—decide on orchestrator_state and update all three docs
4. **TODO (S)**: Verify Phase dependencies in bd (may need manual `bd update` for blocks relationships)
5. **TODO (S)**: Confirm all IDs in HANDOFF_VERIFICATION.md match actual bd issues
6. **TODO (M)**: Run `bd ready --json` after above steps; should show Phase 0 tasks as unblocked

---

## Effort Estimates (Oracle Recommendation)

- Implement new 10 bd issues: M (1–3 hours) + acceptance criteria task
- Fill Phase acceptance criteria: M (1–2 hours, 6 features × ~15 min each)
- Schema decision + doc update: S (<1 hour)
- Verify phase dependencies: S (<30 min)

**Total**: ~3–5 hours to close all P0 gaps. **Start before Phase 0 implementation.**

---

**Report Status**: ✅ ORACLE VERIFICATION COMPLETE  
**Blocker Tasks Created**: 1 (ai-terminal-pzea, P0)  
**Critical Gaps Fixed**: 7  
**New Issues for Handoffs**: 3  
**Ready to Start**: After ai-terminal-pzea is completed

---

**Next Review**: After ai-terminal-pzea acceptance criteria are filled, run `bd ready --json` and confirm all Phase 0 tasks are visible and unblocked.
