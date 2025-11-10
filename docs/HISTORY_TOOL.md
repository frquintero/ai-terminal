# History Tooling

Permanent, on-demand memory for AI Terminal.

## Why it exists
- Session `tool_history` is intentionally lean (last ~10 calls) to keep prompts cheap.
- Users still expect the agent to recall earlier work (e.g., moon phase diagnostics from session 171).
- JSONL logs already capture every event, so we index them into a searchable SQLite store and expose `history_sql` for precise SELECT/INSERT/UPDATE access. There is no fuzzy fallback—if a SQL query returns zero rows, that context truly isn’t recorded yet.

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

Auxiliary table: `agent_memories` captures agent-authored notes (`session_id`, `topic`, `content`, `tags`, `metadata_json`, timestamps) so MiniAgent can append durable summaries without mutating the primary `events` feed.

## Schema snapshot

Two tables exist in `logs/history/history.db`:

| Table | Purpose | Key columns |
| ----- | ------- | ----------- |
| `events` | Canonical log of tool interactions | `session_id`, `timestamp`, `event_type`, `tool`, `summary`, `detail_json`, `artifact_path`, `keywords` |
| `agent_memories` | Agent-authored notes | `session_id`, `topic`, `content`, `tags`, `metadata_json`, timestamps |

Use the `history_schema` tool (see below) to list tables or call `describe_table` to inspect the actual column metadata before forming SQL queries.

## `history_sql` Tool Contract (sole interface)

This tool executes a single SELECT/INSERT/UPDATE statement with bound parameters. Guard rails:
- Trailing semicolons are removed, but embedded semicolons are rejected (single statement only).
- DELETE/DROP/ALTER/TRUNCATE/VACUUM/ATTACH/DETACH/REPLACE and PRAGMA statements are blocked.
- SELECT responses are capped (default 50 rows, caller-adjustable up to 200) to keep outputs concise.

| Parameter      | Type    | Notes                                                                                 |
| -------------- | ------- | ------------------------------------------------------------------------------------- |
| `statement`    | string  | Required SQL statement (no DELETE/DROP/ALTER).                                        |
| `params`       | array   | Optional positional bindings for `?` placeholders.                                    |
| `named_params` | object  | Optional named bindings for `:name` placeholders (mutually exclusive with `params`).  |
| `max_rows`     | int     | Row cap for SELECT queries (default 50, max 200).                                     |

Response shape:
```json
{
  "statement": "SELECT summary FROM events WHERE session_id = ? ORDER BY id DESC",
  "operation": "select",
  "execution_ms": 3.42,
  "rows_returned": 1,
  "columns": ["summary"],
  "rows": [{"summary": "Andrés Quintero is my son."}],
  "truncated": false
}
```
INSERT/UPDATE replies also include `rowcount` and `last_insert_rowid` (for inserts).

## `history_schema` Tool

`history_schema` complements `history_sql` by exposing the DB structure:

| Action | Description |
| ------ | ----------- |
| `list_tables` (default) | Returns all table names in sorted order |
| `describe_table` | Returns column metadata (`name`, `type`, `notnull`, `default_value`, `primary_key`) for the requested table |

Example usage:
```json
{"tool": "history_schema", "arguments": {"action": "describe_table", "table": "events"}}
```

## Agent Guidance
- Default to the live `tool_history` (last ~10 calls) for immediate continuity.
- When the user references earlier work or you sense trimmed context, first run `history_schema` (list tables + describe `events`/`agent_memories`) unless you recently fetched the schema. Then issue `history_sql` with concise SELECT statements using the confirmed columns (e.g., `WHERE summary LIKE '%cv%' AND session_id = '177'`).
- If a SQL query returns zero rows, treat that as authoritative—ask the user for more details or record a new memory instead of falling back to fuzzy guesses.
- Only quote the portions of results needed for the current answer; cite artifacts if the user wants raw data.
- Use `history_sql` for all deterministic recall, aggregations, or to append a structured memory (`INSERT INTO agent_memories(...) VALUES (...)`). DELETE/DROP/ALTER remain blocked at the tool boundary.

## Developer Notes
- The store is shared across the agent and tools via `history_store.get_history_store()`.
- Tests can swap in a temporary DB using `history_store._set_history_store_for_tests`.
- The `history_sql` executor enforces WAL + foreign keys, validates statements, and commits INSERT/UPDATE operations atomically while logging failures.
- Future enhancements (tracked via beads) can add FTS indexing, clustering, or summarization helpers.
