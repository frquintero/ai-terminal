# Oracle Prompt Review - get_context Usage Guidance

**Date:** 2025-11-06  
**Context:** Post-implementation review of enhanced get_context and system prompt  
**Oracle Consultation:** Evaluation of usage guidance and prompt optimization

---

## Questions Asked

1. **Usage Guidance**: Does the MiniAgent need explicit guidance on when to use enhanced get_context?
2. **Prompt Review**: Can the system prompt be improved or streamlined?

---

## Oracle Recommendations

### 1. Add Explicit Usage Triggers ✅ IMPLEMENTED

**Finding:** The brief mention of get_context was insufficient. LLMs often default to `pwd/ls/git status` without explicit triggers.

**Recommendation:** Add 4 concise triggers to Execution Rules:
- At the start of a task if session/repo/sandbox state is unclear
- After any failure or non-zero exit (to inspect recent_errors, tool_history, exit codes)
- When checking environment/project state (instead of pwd/ls/git status/env)
- Before run_python_sandbox to confirm sandbox limits and available interpreters

**Rationale:**
- Explicit, compact triggers increase the chance the agent fetches rich context at the right time
- Leverages the enhanced fields (tool_history, recent_errors, last exit code, repo, sandbox)
- High signal with minimal token overhead (5 lines)

### 2. Tighten get_context Description ✅ IMPLEMENTED

**Before:**
```
"Prefer this over redundant pwd/ls/git status commands."
```

**After:**
```
"Prefer this over pwd/ls/git status/env when you just need state."
```

**Improvement:** More precise about replacement scenario (state checks vs listings)

### 3. Fix Output Policy Contradiction ✅ IMPLEMENTED

**Finding:** Conflict between execution rules and rendering rules about tool output.

**Before (Execution Rules):**
```
"Do not duplicate tool output in responses - outputs are logged internally"
```

**Before (Rendering Rules):**
```
"Include relevant output directly in your response when the user asks to see something"
```

**After (Unified):**
```
"Output policy: summarize by default; paste command/file output only when 
it answers the user's request or is necessary to show results"
```

**Improvement:** Reconciles both sections with clear, actionable guidance

### 4. Add Explicit Listing Guard ✅ IMPLEMENTED

**Added:**
```
"Only run pwd/ls/git status/env when you need the actual listing/output"
```

**Rationale:** Prevents redundant shell commands when get_context suffices

---

## Implementation Changes

**Commit:** `f743931` - Refine system prompt with explicit get_context usage triggers

**Modified:** `agent.py` (system prompt)
- +8 lines (triggers and clarifications)
- -3 lines (removed/replaced contradictory text)
- Net: +5 lines of high-value guidance

**Token Impact:** Minimal (~50 tokens added for significant value)

---

## Design Trade-offs Considered

### ✅ Why Add Triggers (Not Examples)
- **Chosen:** 4 concise bullet points
- **Rejected:** Example calls with JSON
- **Rationale:** Examples add token cost and noise; triggers give high signal with minimal overhead

### ✅ Positioning
- **Chosen:** Keep detailed get_context description in "File access model"; add triggers to "Execution Rules"
- **Rationale:** Agent scans tool overview in File access model; decision moment governed by Execution Rules

### ✅ Summarize vs Paste Guidance
- **Chosen:** "Summarize by default; paste when relevant"
- **Rejected:** Absolute rules ("never paste" or "always paste")
- **Rationale:** Context-dependent; agent needs discretion

---

## Risk Mitigation

### Risk: Overuse of get_context every turn
**Guardrail:** "At the start" and "after failures" guidance, plus "when checking state"

### Risk: Agent still runs pwd/ls for listings
**Guardrail:** "Only run when you need the actual listing/output"

### Risk: Token bloat if agent pastes large outputs
**Guardrail:** "Summarize by default; paste only when it answers the request"

---

## Advanced Path (Not Implemented - Future Option)

If persistent underuse or overuse observed:

### Auto-trigger Heuristic
**Approach:** In `process_input`, after `run_command` with non-zero exit, automatically append an assistant tool call to `get_context` before the model's next turn.

**Benefit:** Removes reliance on prompt-following for error debugging

**Effort:** S-M (behind config flag)

**When to consider:**
- Agent frequently runs commands, sees failures, but doesn't check get_context
- Repeated debugging cycles without context awareness

---

## Success Metrics (Observational)

### Signs of Success ✅
- Agent calls get_context at task start for complex requests
- Agent checks get_context after command failures
- Agent uses get_context instead of redundant pwd/ls/git status
- Agent respects sandbox limits discovered via get_context

### Signs of Issues ❌
- Agent runs pwd/ls/git status before every command
- Agent ignores recent_errors after failures
- Agent runs run_python_sandbox without checking limits
- Agent calls get_context every turn regardless of need

---

## Final Assessment

### Before Oracle Review
- Enhanced get_context implemented ✅
- Brief mention in prompt ⚠️
- Unclear when agent should use it ❌
- Contradictory output guidance ❌

### After Oracle Review + Implementation
- Enhanced get_context implemented ✅
- Explicit usage triggers ✅
- Clear scenarios for when to call ✅
- Unified output policy ✅

**Status:** ✅ **Ready for production use**

**Next:** Monitor agent behavior to validate effectiveness of triggers

---

## Oracle Quote

> "Add a short, explicit 'When to call get_context' checklist to Execution Rules, and fix the minor contradiction about showing tool output. Keep the existing get_context description, but tighten the execution guidance so the agent uses it at the right moments without bloating tokens."

**Result:** 5-line addition with high signal-to-noise ratio

---

**Reviewed by:** Oracle (GPT-5 reasoning model)  
**Implemented by:** Amp (GPT-4.5 execution agent)  
**Status:** ✅ Complete and merged to feature branch
