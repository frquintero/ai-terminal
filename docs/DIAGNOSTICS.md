# Diagnostics & Telemetry

This guide explains how to inspect agent runs, debug OpenAI failures, and keep work coordinated with the bd issue tracker.

## OpenAI Traces

- Every call to `chat.completions.create` is tagged with `trace <id>` and persisted as `logs/openai_traces/<trace>.json`.
- The JSON file contains the exact `messages` payload that went to OpenAI, plus system reminders injected by the agent.
- Use the trace file to reproduce 400-level responses (e.g., “tool_call_id not found”) without re-running a long session.

## Event-Driven Memory

- Every session streams events (user messages, tool calls/results, errors, summaries) to `logs/events/<session>.jsonl`.
- `MiniAgent` builds an “Agent Memory” system message each turn by retrieving high-signal events via `EventRetriever`.
- Artifacts: tool outputs > `EVENT_MEMORY_ARTIFACT_THRESHOLD` bytes are written to `ai-terminal-wd/artifacts/<session>_<id>.txt` and referenced via `artifact_path` in the event log.
- `GetContext` now reports `event_memory` with counts and the on-disk log path so you can open it directly.

**When debugging:**
- Scan the JSONL to understand what the model saw (errors, command outputs, artifact references).
- If the memory block mentions `artifact_path`, call `read_file` on that path only when you need the raw output; otherwise use the logged `artifact_summary`/`output_preview`.

## Session Logs

- `session_logs.db` stores structured entries such as:
  - `OPENAI_REQUEST`: summary of each payload (message count, last roles, tool call metadata).
  - `OPENAI_ERROR`: serialized error info (trace id, exception string).
  - `HISTORY_TRIM_DROP`: count of orphan tool outputs removed during trimming.
  - Other events (`USER_QUERY`, `TOOL_CALL`, `TRACE_WARNING`, etc.).
- Use any SQLite viewer or `sqlite3 logs/session_logs.db` to browse entries.

## Error Surfacing via `get_context`

- When an API call raises, `_SESSION_STATE.record_error("openai_api", ...)` stores it in session state.
- Running `get_context` shows these errors under the `errors` key along with tool history, so you can see what failed without re-running commands.

## History Guardrails

- `_trim_history()` now removes tool messages that have no matching assistant/tool_call anchor in the trimmed window.
- This prevents OpenAI from seeing dangling `tool_call_id` references that previously triggered 400 errors.

## Beads Issue Tracking

- All tasks are tracked via bd; changes must commit `.beads/issues.jsonl` alongside code.
- Helpful commands:
  - `bd ready --json` — show unblocked issues
  - `bd list --status in_progress --json` — see active work
  - `bd create "Title" -t bug|feature|task -p PRIORITY --json` — log new work
- When instrumentation uncovers new bugs, create a bead and link it via `--deps discovered-from:<parent-id>` if applicable.
