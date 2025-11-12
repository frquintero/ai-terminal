# v2.0 Orchestrator Upgrade: Readiness Checklist

**Status**: ✅ READY FOR PHASE 0 (with critical P0 task first)  
**Last Updated**: 2025-11-11  
**Branch**: `feature/v2-orchestrator-upgrade`

---

## Pre-Implementation Checklist

### Architecture & Specifications ✅
- [x] DOUBLE_AGENT_ARCHITECTURE.md complete (42KB, all agent roles specified)
- [x] IMPLEMENTATION_PLAN.md with 6 phases + detailed schemas (61 sections)
- [x] HANDOFF_VERIFICATION.md mapping architecture → implementation
- [x] Oracle verification report with gap analysis (ORACLE_VERIFICATION_REPORT.md)

### BD Issue Tracking ✅
- [x] Epic created: v2.0 Multi-Role Orchestrator (ai-terminal-0b7, P0)
- [x] 6 Phase features created (299, ckz, 5r7, 4zb, owj, 6g0)
- [x] 50+ sub-tasks created across all phases
- [x] 10 critical gap-fix issues created:
  - [x] Cross-route handoff tasks (3): ai-terminal-t0e, cnc, inu
  - [x] Agent C prompts: ai-terminal-n4c
  - [x] Router CLI: ai-terminal-pi97
  - [x] LLMClient/ToolExecutor: ai-terminal-56xd
  - [x] Schema decision: ai-terminal-dqve
  - [x] Phase 0 acceptance: ai-terminal-rizw
  - [x] **P0 BLOCKER**: ai-terminal-pzea (fill acceptance criteria)

### Documentation ✅
- [x] history/ directory organized with ephemeral planning docs
- [x] All architecture specs stored permanently (repo root)
- [x] Links verified between documents
- [x] Cross-references to bd issues included

---

## Critical Blockers (MUST DO BEFORE PHASE 0)

### 🔴 **BLOCKING TASK: ai-terminal-pzea (P0)**
**Task**: "Fill acceptance criteria for all Phase features (test commands, success metrics)"

**What**: Every Phase feature (0, 1, 2, 3, 4, 5, 6) must have:
- ✓ Testable acceptance criteria (specific, measurable)
- ✓ Test commands (how to verify)
- ✓ Doc references (which IMPLEMENTATION_PLAN section)
- ✓ Success metrics (from §9 of plan)

**Example Template** (see ORACLE_VERIFICATION_REPORT.md for full details):
```
Phase 0 Acceptance:
- Single orchestrator.db at logs/orchestrator.db
- 8 tables created (sessions, router_decisions, etc.)
- Full CRUD API working
- All unit tests pass

Test commands:
  python -m pytest tests/test_memory.py -v
  ls -la logs/orchestrator.db
```

**Effort**: ~2 hours (1–2 hours per Phase feature)  
**Owner**: Any team member (can parallelize across 2 people)  
**Deadline**: BEFORE anyone starts Phase 0  
**Status**: ❌ NOT YET STARTED

---

### 🟡 **DECISION TASK: ai-terminal-dqve (P1, Non-Blocking)**
**Task**: "Schema decision: orchestrator_state vs cycle_id"

**What**: DOUBLE_AGENT_ARCHITECTURE.md lists `orchestrator_state` table;  
IMPLEMENTATION_PLAN.md omits it (relies on cycle_id + timestamps).

**Decision Options**:
1. **Option A (Simpler)**: Drop orchestrator_state. Use cycle_id as foreign key on all tables.
   - Pros: Simpler schema, faster queries with indexed cycle_id
   - Cons: Lose some orchestrator control signals
2. **Option B (Richer State)**: Keep orchestrator_state for orchestrator-level state tracking.
   - Pros: Better for complex orchestration, easier cycle status lookups
   - Cons: Additional table + more writes

**Action**: Task owner decides, updates both IMPLEMENTATION_PLAN.md and DOUBLE_AGENT_ARCHITECTURE.md to match.

**Effort**: <1 hour  
**Blocking**: No (Phase 0 proceeds with cycle_id approach; can retrofit later if Option B chosen)  
**Status**: ❌ NOT YET STARTED

---

## Phase Readiness Matrix

| Phase | Feature | Status | Blockers | Ready Date | Notes |
|---|---|---|---|---|---|
| 0 | Memory module (ai-terminal-299) | ✅ Tracked | ai-terminal-pzea | Immediate | Waiting on acceptance criteria task |
| 1 | Router MVP (ai-terminal-ckz) | ✅ Tracked | ai-terminal-pzea, Phase 0 complete | After Phase 0 | FTS5 MVP, defer ML to Phase 6 |
| 2 | Orchestrator + Agent C (ai-terminal-5r7) | ✅ Tracked | ai-terminal-pzea, Phase 1 complete | After Phase 1 | Includes cross-route handoff tasks |
| 3 | Planner (ai-terminal-4zb) | ✅ Tracked | ai-terminal-pzea, Phase 2 complete | After Phase 2 | JSON schema + validation |
| 4 | Executor (ai-terminal-owj) | ✅ Tracked | ai-terminal-pzea, Phase 3 complete | After Phase 3 | ToolRunner + step loop |
| 5 | Polish (ai-terminal-6g0) | ✅ Tracked | Phases 2–4 complete | After Phase 4 | Cleanup + telemetry |
| 6 | ML Router (ai-terminal-pg0) | ✅ Tracked | Phase 1 data collected | Deferred | Backlog; optional |

---

## Handoff Verification ✅

All cross-route context handoffs have explicit tasks:
- [x] Chat → Planner (ai-terminal-t0e)
- [x] Planner → Chat (ai-terminal-cnc)
- [x] Integration tests (ai-terminal-inu) covering 3 examples
- [x] Agent C universal narrator (ai-terminal-n4c covers all modes)

**Status**: All handoff requirements from DOUBLE_AGENT_ARCHITECTURE.md mapped to bd.

---

## Implementation Ready Checklist

Before **any team member** starts work:

1. **ai-terminal-pzea completed** ✅
   - [ ] Phase 0 acceptance criteria filled
   - [ ] Phase 1 acceptance criteria filled
   - [ ] Phase 2 acceptance criteria filled
   - [ ] Phase 3 acceptance criteria filled
   - [ ] Phase 4 acceptance criteria filled
   - [ ] Phase 5 acceptance criteria filled
   - [ ] All test commands verified as runnable

2. **Phase 0 environment ready** ✅
   - [ ] logs/ directory writable
   - [ ] sqlite3 available (system package)
   - [ ] tests/ directory ready for unit tests

3. **bd dependencies wired** (optional, for advanced teams)
   - [ ] Phase 1 `blocks` Phase 2
   - [ ] Phase 2 `blocks` Phase 3
   - [ ] Phase 3 `blocks` Phase 4
   - [ ] `bd ready` shows Phase 0 tasks and nothing else
   
   **Command** (after pzea done):
   ```bash
   bd update ai-terminal-ckz --deps "blocks:ai-terminal-5r7" --json
   bd update ai-terminal-5r7 --deps "blocks:ai-terminal-4zb" --json
   bd update ai-terminal-4zb --deps "blocks:ai-terminal-owj" --json
   bd ready  # Should show Phase 0 + pzea only
   ```

4. **Git environment ready** ✅
   - [ ] On feature branch: `git branch` → `* feature/v2-orchestrator-upgrade`
   - [ ] .beads/issues.jsonl in git tracking

---

## Starting Phase 0 (Memory Module)

Once **ai-terminal-pzea is complete**:

1. **Claim Phase 0 feature**:
   ```bash
   bd update ai-terminal-299 --status in_progress --json
   ```

2. **Start with tasks in order**:
   - [ ] ai-terminal-dqve (schema decision, ~1h)
   - [ ] ai-terminal-wjt (unified memory system, ~8-10h)
   - [ ] ai-terminal-nns (migrations, ~4-6h)
   - [ ] ai-terminal-56xd (LLMClient/ToolExecutor, ~4h)
   - [ ] ai-terminal-ulv + ai-terminal-e3a (extraction, ~2-3h)
   - [ ] ai-terminal-7un (unit tests, ~3-4h)
   - [ ] ai-terminal-rizw (acceptance test, ~1h)

3. **Commit workflow**:
   - Every completed task: `git commit` with `.beads/issues.jsonl`
   - Link commits to bd: include "bd-NNN" in commit message
   - Example: "feat: implement unified memory system (bd-wjt)"

4. **Before moving to Phase 1**:
   - [ ] Run: `python -m pytest tests/test_memory.py -v`
   - [ ] Verify: `ls -la logs/orchestrator.db` exists with all tables
   - [ ] Verify: No imports from v1.3 legacy stores in new code
   - [ ] Update: `bd close ai-terminal-299 --reason "Phase 0 complete"`

---

## Team Coordination

### For Parallel Work
If multiple team members:
- **Person A**: ai-terminal-pzea (acceptance criteria) - blocks nothing, priority
- **Person B** (after A done): Phase 0 memory module (ai-terminal-wjt)
- **Person C** (after A done): Phase 1 router (ai-terminal-ckz subtasks)

### For Sequential Work
- Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5

---

## Success Signals

✅ **Phase 0 Complete When**:
- Single logs/orchestrator.db file exists with 8 tables
- Memory CRUD API fully tested
- Zero legacy (v1.3) code in memory module
- All Phase 0 subtasks closed in bd

✅ **Phase 1 Complete When**:
- Router CLI works: `python -m router.cli "ls -la"`
- Test corpus accuracy: 95% CHAT, 90% shell, 80% cache precision
- All router tests pass

✅ **Phase 2 Complete When**:
- Main.py wired to Orchestrator
- Shell commands execute immediately
- Chat queries work end-to-end
- Cross-route handoff tests pass

...and so on for Phases 3–5.

---

## Risk Mitigation Summary

| Risk | Mitigation | Status |
|---|---|---|
| Missing acceptance criteria | P0 task ai-terminal-pzea | ✅ Created |
| Cross-route context forgotten | 3 explicit tasks + 1 integration test task | ✅ Created |
| Schema drift | Decision task ai-terminal-dqve | ✅ Created |
| Phase dependency confusion | Documented in bd (manual verify step optional) | ✅ Documented |
| Team starts wrong phase | bd ready only shows Phase 0 (once deps wired) | ✅ Can setup |
| Non-testable acceptance | Test commands in ORACLE_VERIFICATION_REPORT.md | ✅ Documented |

---

## Next Immediate Actions (DO FIRST)

1. **Start ai-terminal-pzea** (P0 blocker)
   ```bash
   bd update ai-terminal-pzea --status in_progress --json
   git add .beads/issues.jsonl
   ```

2. **Fill acceptance criteria for all 6 Phase features** (use template in ORACLE_VERIFICATION_REPORT.md)
   - Phase 0 (ai-terminal-299): memory CRUD
   - Phase 1 (ai-terminal-ckz): router accuracy
   - Phase 2 (ai-terminal-5r7): orchestrator e2e
   - Phase 3 (ai-terminal-4zb): planner JSON
   - Phase 4 (ai-terminal-owj): executor step loop
   - Phase 5 (ai-terminal-6g0): polish/cleanup

3. **Mark ai-terminal-pzea complete** once all acceptance criteria are in bd/docs
   ```bash
   bd close ai-terminal-pzea --reason "All Phase features have testable acceptance criteria and test commands" --json
   git add .beads/issues.jsonl
   git commit -m "chore: acceptance criteria filled for all phases (ai-terminal-pzea complete)"
   ```

4. **Then start Phase 0 implementation**
   ```bash
   bd update ai-terminal-299 --status in_progress --json
   ```

---

## Files Reference

- **Architecture**: DOUBLE_AGENT_ARCHITECTURE.md (permanent, repo root)
- **Implementation Plan**: history/IMPLEMENTATION_PLAN.md (ephemeral design doc)
- **Handoff Spec**: history/HANDOFF_VERIFICATION.md (verification matrix)
- **Oracle Feedback**: history/ORACLE_VERIFICATION_REPORT.md (gap analysis + templates)
- **This Checklist**: history/READINESS_CHECKLIST.md (you are here)
- **Issue Tracking**: .beads/issues.jsonl (git-synced)

---

**Status**: 🟢 **READY TO BEGIN** (after ai-terminal-pzea is complete)

**Estimated Total Duration**: 7.5–11.5 days (6 phases + cleanup)

**Start Date**: Once ai-terminal-pzea acceptance criteria are filled (~2h to complete)

---

*This checklist is the single source of truth for implementation readiness. Keep it updated as phases complete.*
