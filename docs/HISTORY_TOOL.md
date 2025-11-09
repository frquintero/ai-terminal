# History Search Tool

Permanent, on-demand memory for AI Terminal.

## Why it exists
- Session `tool_history` is intentionally lean (last ~10 calls) to keep prompts cheap.
- Users still expect the agent to recall earlier work (e.g., moon phase diagnostics from session 171).
- JSONL logs already capture every event, so we index them into a searchable SQLite store and expose the `history_search` tool.

## Storage & Resilience
- Database path: `logs/history/history.db` (override via `HISTORY_DB_PATH`).
- On startup the app ensures:
  1. Directory exists.
  2. Schema matches the expected version.
  3. `PRAGMA quick_check` passes. Failures trigger automatic rebuild; corrupted DBs are renamed `*.corrupt-<timestamp>`.
- Every event recorded via `EventLog.append` is also written to the store with summaries, keywords, and artifact pointers.

Schema (simplified):

| Column        | Purpose                                           |
| ------------- | ------------------------------------------------- |
| `session_id`  | Source session (string)                           |
| `timestamp`   | ISO-8601 event time                               |
| `event_type`  | `user_message`, `tool_call`, `tool_result`, etc.  |
| `tool`        | Tool name or source                               |
| `action`      | Tool call id / source identifier                  |
| `summary`     | Short human-friendly description                  |
| `detail_json` | Full JSON payload (mirrors event log entry)       |
| `artifact_path` | Points to persisted outputs when available     |

## `history_search` Tool Contract

| Parameter   | Type    | Notes                                                                 |
| ----------- | ------- | ---------------------------------------------------------------------- |
| `query`     | string  | Keywords or natural language (case-insensitive `LIKE` search).        |
| `session_id`| string  | Filter to a single session (`"171"`, `"ai-terminal-logs"`).           |
| `since`     | string  | ISO timestamp lower bound.                                            |
| `until`     | string  | ISO timestamp upper bound.                                            |
| `tool`      | string  | Filter by tool name (`run_command`, `http_request`, …).               |
| `limit`     | int     | 1–25 (default 5) for bounded responses.                               |

Output structure:
```json
{
  "matches": [
    {
      "session_id": "171",
      "timestamp": "2025-11-09T14:12:03.482Z",
      "event_type": "tool_result",
      "tool": "http_request",
      "summary": "Moon API response (200)",
      "detail_preview": "Return JSON with phase=waning gibbous",
      "artifact_path": "ai-terminal-wd/artifacts/171_moon_api.txt",
      "source_ref": {
        "type": "history_db",
        "event_id": 42,
        "session_log": "logs/events/171.jsonl"
      }
    }
  ],
  "stats": {
    "returned": 1,
    "limit": 5,
    "total_available": 3
  }
}
```

## Agent Guidance
- Default to the live `tool_history` (last ~10 calls) for immediate continuity.
- Invoke `history_search` when:
  1. The user references earlier work/sessions.
  2. You suspect relevant steps were trimmed from `tool_history`.
  3. You need authoritative recall before performing a risky/destructive action.
- Keep queries focused (keywords + optional time/session filters) so responses stay concise.
- Only quote the portions of results needed for the current answer; cite artifacts if the user wants raw data.

## Developer Notes
- The store is shared across the agent and tools via `history_store.get_history_store()`.
- Tests can swap in a temporary DB using `history_store._set_history_store_for_tests`.
- Future enhancements (tracked via beads) can add FTS indexing, clustering, or summarization helpers.
