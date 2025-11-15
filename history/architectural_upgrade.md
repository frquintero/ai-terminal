# Architectural Upgrade Plan (Routerless Dual-Agent Flow)

## Guiding Principles
- **In AI we trust**: keep intelligent agents in control of planning, narration, and shell access without manual babysitting.
- **Shell-first execution**: Agent B is the sole gateway for every command, including trivial `ls`-style probes.
- **Remove obsolete/deprecated layers**: retire the Router cascade, Agent C narration, and any schema branches that reference them.
- **Single source of truth**: Orchestrator + Memory own cycle/step data; ToolExecutor stays stateless.

## Reality Check (v2.0)
- Router + intention cache still gate every query, fragmenting context across CHAT/SHELL/CACHED/PLANNER flows.
- Agent A can only emit plan/clarify/delegate → can’t narrate or describe desired outputs.
- Agent B occasionally bypassed (SHELL route) and lacks a structured return format for results.
- Agent C handles narration even when redundant, inflating token+latency budgets.
- Memory schema (`router_decisions`, `step_outputs`, `chat_history`) assumes the old multi-route lifecycle.

## Target End State
- **Two-role stack**: Agent A (planner+narrator) or direct response, Agent B (per-step command engineer).
- **Unified entry path**: every REPL query invokes Agent A; Router/Agent C code becomes dead weight.
- **Declarative narration**: Agent A supplies `steps[]` + `narration_template` with explicit `output_keys`.
- **Structured execution**: Agent B emits `{command, output_format}`; Orchestrator parses stdout into typed values, stores them, and renders the final template.
- **Clean memory contract**: cycle metadata records plan template, per-step outputs, and final narration; router- and Agent C-specific tables go away or become no-ops.

## Phased Implementation

### Phase 0 – Environment & Context Integrity (and transitional hotfixes)
1. Finish plumbing `_get_effective_shell_cwd()` through `SystemContextBuilder.build_for_role` so prompts reflect the actual sandbox (`run_command.get_effective_cwd()` or `/workspace`).
2. Keep `RunCommandTool` / `RunInteractiveCommandTool` free of host-path `cd` when isolation is active; ensure ToolExecutor propels that information upstream for logs/Memory snapshots.
3. Add regression tests (unit or lightweight integration) proving the orchestrator and ToolExecutor agree on cwd under both isolated and non-isolated shells.
4. Transitional only (if we ship before removing Agent C): fix the Agent C summarizer UnboundLocalError in `orchestrator/orchestrator.py` by constructing system_context/messages after accumulating the full step context. If we immediately remove Agent C per Phase 1, this hotfix is skipped.

### Phase 1 – Remove Router + Agent C, preserve safeguards and latency
1. Excise `Router` construction from `Orchestrator.__init__` and delete CHAT/SHELL/CACHED route handlers; `handle_query` becomes: create cycle → call Agent A → either respond or execute plan.
2. Archive or delete router modules (`router/` package, intention cache, regex rule engine) and drop associated Memory tables/migrations (`router_decisions`, `intention_cache`) as obsolete.
3. Remove Agent C prompt generation, LLM client instantiation, and narration handoffs. Any shared utilities (metrics, system context) should be re-scoped to Agents A/B only.
4. Update REPL/front-end entry point (`main.py` or CLI harness) so it no longer expects route metadata or Agent C strings; it should display Agent A’s final narration verbatim.
5. Interactive-command safeguards: retain and reuse the existing `parse_command` / `RuleEngine.is_interactive_command` logic inside the Orchestrator execution path so steps targeting interactive programs are routed to `run_interactive` and everything else to `run_command`. Both Agents get explicit instructions: Agent A flags interactive steps via `tool_name: "run_interactive"`; Agent B’s prompt reinforces “choose run_interactive for commands requiring TTY (vim, top, ssh, etc.).”
6. Latency for literal shell queries (sub‑500 ms target): **always** pass through Agent A so the narrator owns every response. Encourage Agent A (via prompt guidance and cached exemplars) to emit single-step plans with minimal narration when the intent is an obvious shell command, keeping token use low without sacrificing narrative quality. Optimize prompt size, reuse plan skeletons, and keep ToolExecutor warm so the extra hop stays within budget while preserving the “Agent A narrates everything” principle.
7. Acceptance criteria: identical or better latency than v2.0 for `ls`, `cat`, `rg`, etc. while still delivering an Agent A-authored narration; correct `run_interactive` selection for interactive commands; zero regressions in safety guards.

### Phase 2 – Rebuild Agent A (Planner + Narrator)
1. Replace `get_agent_a_prompt` with a new template that enforces exactly two outputs: `{"response": ...}` or `{steps: [...], narration_template: "..."}`. Remove references to delegation/clarification branches that are no longer valid.
2. Extend `PlanValidator` (and `plan_schema.detect_response_type`) to validate:
   - Every step has `tool_name`, `intent`, optional `description`, and `output_keys` (non-empty array of unique strings).
   - `narration_template` exists when `steps` exist and only references declared keys.
   - `response` strings appear only when `steps` is absent.
3. Adjust Orchestrator logging so cycles capture the entire plan payload (steps + template) for future auditing.
4. Update docs/tests to describe the new schema, emphasizing that Agent A never emits commands or placeholders not backed by `output_keys`.
5. Encode interactive-command requirements directly into the new Agent A prompt (explicit list of TTY-requiring commands, expectation to set `tool_name` to `run_interactive` whenever the intent involves them). Plan validation should fail when interactive steps are mis-labeled; add fixtures covering both `run_command` and `run_interactive` paths.

Migration/testing checklist for consumers expecting v2.0 schemas:
- Update `plan_validator` and its fixtures to remove acceptance of `clarify` and `delegate_to_chat`; add coverage for `output_keys`/`narration_template` alignment.
- Update `test_e2e_planner.py` to reflect the two-output contract; add cases for “no-tools response” and for multi-step plans with lists/raw/table outputs.
- Adjust `debug_cycle.py` (or equivalent) to render steps, `output_keys`, and the final hydrated narration instead of Agent C summaries.

### Phase 3 – Redesign Agent B (Command Engineer)
1. Write a new Agent B prompt that ingests a single step, its `output_keys`, and any available prior outputs; instruct it to return JSON:
   ```json
   {
     "command": "…",
     "output_format": { "files": "list", "count": "int" }
   }
   ```
   (extendable with future tool types)
2. Update orchestrator → Agent B call sites to loop over steps sequentially, persisting each LLM call + tool invocation separately in Memory.
3. Expand `PlanValidator` or a new runtime validator to ensure Agent B’s `output_format` covers all declared keys for the step and only uses supported types (`int`, `float`, `str`, `list`, `raw`, `table`).
4. Introduce error handling / retry policy specific to Agent B mis-specifying commands or formats, with structured error messages saved for debugging.

Migration/testing checklist:
- Update any tests/fixtures that assumed `{"tool_name","tool_args"}` output to now expect `{command, output_format}`.
- Add unit tests ensuring `output_format` covers all declared `output_keys` and rejects unknown types.
- Verify interactive-command decisions in prompts lead B to select `run_interactive` when appropriate.

### Phase 4 – Structured Tool Execution & Parsing
1. Enhance `ToolExecutor.execute` to optionally return structured payloads: raw stdout, stderr, exit code, and truncated preview for Memory.
2. Add a parsing layer in Orchestrator (or a new `OutputParser`) that converts stdout into the types requested by Agent B:
   - `int`/`float`: parse numeric tokens (with validation and error reporting).
   - `list`: split by newlines, trim empties.
   - `raw`: preserve exact text with ANSI/spacing.
   - `table`: detect and preserve box-drawing/spacing (no stripping).
3. Persist parsed values in `memory.step_outputs` keyed by `(cycle_id, step_id, output_key)` and store full stdout/stderr in blob columns for replay/debug.
4. After all steps complete, hydrate `narration_template` with the parsed data, respecting formatting (lists/joined lines, raw calendar blocks, etc.), then send final narration to the REPL.

- **Status: ✅** ToolExecutor now emits stdout/stderr/raw previews, `memory.step_outputs` stores structured blobs + `parsed_outputs`, `orchestrator/output_parser.py` materializes Agent B’s `output_format`, and template hydration is covered by parser + orchestrator tests.
- **REPL rendering: ✅** The REPL keeps Agent A’s narration as plain text, replaces placeholders inline, and only emits fenced blocks (```output```, ```json```, ```md```, language fences) when a step returns structured stdout—exactly as mandated in `history/ai_terminal_spec_v1.5 (1).md`. No command headers or duplicate “stdout” labels are injected.
- **Zero-output narration: ✅** Shell integrations now preserve truly empty stdout instead of returning “Command executed successfully,” and the orchestrator replaces those placeholders with an explicit message (`Tool run_command (command: …) completed with no output…`) so Agent A’s narration stays coherent without phantom data. The REPL detects the `no_output` flag and keeps the whole response inline (no redundant ANSI blocks).

Migration/testing checklist:
- Add golden-output tests that compare hydrated narrations versus templates for combinations of `int`, `list`, and `raw`.
- Ensure `debug_cycle.py` and any dashboard viewers can display preserved ANSI/table outputs without stripping spacing.

### Phase 5 – Memory, Metrics, and DB Wiring
1. Update the Memory API and migrations:
   - Drop router-specific tables.
   - Introduce `plans` (steps + narration template), `step_calls` (Agent B metadata), and richer `step_outputs`.
   - Ensure `chat_history` now reflects only direct `response`-type replies from Agent A (no Agent C echoes).
   - **Status: ✅** Enforce “success-only” retention via `Memory.cycle_transaction()` so failed cycles roll back automatically, and expose a purge utility for clean snapshots before upgrades.
   - **Status: ✅** Add `cycle_failures` table + `Memory.record_cycle_failure` so unsuccessful runs are snapshotted outside the main transaction for debugging/telemetry.
2. Revise metrics (`RouteMetrics`, `LLMMetrics`) to track Agent A/B latency, success/failure counts, retries, and parsing errors instead of route hit-rates.
3. Ensure the unified SQLite schema keeps backward compatibility or offers a migration path that rewrites old sessions into the new format.
4. Update Memory import/export routines so bd issues and orchestration history stay aligned after schema changes.

Migration/testing checklist:
- Write migrations to drop router tables and add `plans`, `step_calls`, expanded `step_outputs`; include data-transform scripts where feasible.
- Update metrics dashboards to remove route charts and add A/B latency, success, retry, and parse-error panels.
- Update `debug_cycle.py` to query and display new tables.

### Phase 6 – Cleanup, Tests, and Documentation
1. Remove any dead code paths (Agent C prompts, router cache utilities, unused config flags) to honor the “remove obsolete” directive.
2. Refresh developer docs: `AGENTS.md`, `README`, tool reference, and existing plans in `history/` to describe the dual-agent loop, narration templates, and output parsing.
3. Expand automated coverage:
   - Unit tests for Agent A/B validators.
   - Parser tests for each output type.
   - Integration smoke tests that simulate a multi-step plan and verify the final narration matches the template.
4. Communicate the upgrade path (release notes or bd issue) so downstream tooling knows Router/Agent C artifacts are gone.

## Immediate Next Actions
1. Capture bd issue(s) for Phase 0+1 to keep work tracked.
2. Stand up feature flags or a migration branch if we need to keep v2.0 alive during the transition; otherwise, purge the old stack once Phase 3 lands.
3. Keep aggressive logging during rollout to ensure the new typed-output parsing doesn’t silently mangle shell results.

This plan keeps the orchestrator lean, respects the “in AI we trust” ethos, and eliminates obsolete routing/narration layers so every query flows through a predictable, auditable dual-agent pipeline.
