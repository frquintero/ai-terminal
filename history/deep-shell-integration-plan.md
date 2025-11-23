# Deep Shell Integration Enhancement Plan

## Objectives
- Ensure Agents A and B consistently leverage the improved shell lexer/parser and stdin reference plumbing.
- Provide fast feedback when tool usage ignores available stdin data.
- Reduce prompt bloat by enabling reusable stdin references (`input_data_ref`, future helpers).
- Back the changes with regression coverage so retries stay low.

## Work Breakdown
1. **Prompt + Contract Refresh**
   - Expand Agent B’s toolbelt description with explicit `input_data_ref` guidance and a concrete `read_file → run_command` example.
   - Add TODO enforcement copy nudging reuse of previous outputs via references.
   - Update Agent A’s delegation instructions so TODOs mention piping/refs when subtasks depend on earlier outputs.
2. **Telemetry + Tooling Enhancements**
   - Detect `read_file` → `run_command` sequences that fail with empty stdin and surface a warning via `agent_message`.
   - Persist lightweight metadata about each tool call’s stdout/stderr (hash + length) when caching `tool_outputs_by_call_id` for debugging.
   - Introduce a `pipe_from` helper tool that writes provided data to a temp file and returns an `input_data_ref` object Agent B can feed into `run_command`.
3. **Shell / Tool Documentation Updates**
   - Refresh `run_command` schema docs and inline usage examples so the new behavior is obvious to both humans and LLMs.
   - Document the telemetry/warning expectations for troubleshooting.
4. **Regression Coverage**
   - Extend orchestrator tests to cover the warning path and the `pipe_from` helper.
   - Re-run or update shell+planner suites so heredoc/stdin behaviors remain stable after prompt changes.

## Done When
- Prompts clearly describe stdin references and TODOs encourage data reuse.
- Empty-stdin misuse emits actionable warnings with references to prior tool_call_ids.
- `pipe_from` exists and returns usable `input_data_ref` payloads.
- Tests cover input_data_ref + pipe_from flows and pass locally.
