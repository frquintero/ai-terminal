# History Tool Plan

## Problem & Context
- Session logs show we routinely lose long-running context once `tool_history` is trimmed, which left the mini agent unable to recall prior moon-phase work in session 171.
- JSONL event logging exists, but it only helps humans; the agent still sees a tiny sliding window.
- Users want transparency: every correctly finished interaction must be recoverable, searchable, and callable on demand without bloating every prompt.

## Solution Overview
1. **Permanent Event Store** – Maintain a self-healing SQLite database (e.g., `logs/history/history.db`) that mirrors each finalized tool interaction: session id, timestamps, tool, query, summary, payload pointer.
2. **`history_schema` Tool** – Lightweight helper that lists tables / describes columns so the agent knows the schema before querying.
3. **`history_sql` Tool** – A first-class tool in `tools.py` that lets the agent run parameterized SELECT/INSERT/UPDATE statements over the store (DELETE/DROP blocked). Responses return structured rows plus references back to the JSONL trace if deeper dives are needed.
4. **Agent Memory Summaries** – After each tool cycle we log tool_call/tool_result events with the `tool_call_id` so the Agent Memory block can report the tool name, args, outcome, and truncated output preview. With that summary in place, we drop the tool call/observation pair from the live prompt, keeping the working memory at three exchanges while letting `history_sql` provide deeper recall.
5. **Agent Guidance & Memory Balance** – Update the MiniAgent system prompt so it knows:
   - use normal `tool_history` for short-term context,
   - call `history_sql` whenever the user references work that predates the live window (or when it senses gaps),
   - interpret results as authoritative historical memory.
   - Tighten short-term memory to ~3 interactions (configurable) now that deep history is available, keeping prompts ultra-lean without sacrificing recall.

## Data & Storage Design
- **Database**: SQLite, auto-initialized on startup; tables:
  - `events(id INTEGER PK, session_id INT, timestamp TEXT, tool TEXT, action TEXT, summary TEXT, detail_json TEXT, keywords TEXT)`.
  - Optional `attachments` table for paths to stored bodies (`http_traces`, etc.).
- **Auto-bootstrap**: On launch we check schema integrity; if missing or corrupt we recreate and backfill from existing `logs/events/*.jsonl`.
- **Ingestion**: Each successful tool call writes a row. Include derived keywords (normalized text) for fast LIKE queries.
- **Querying**: Encourage concise WHERE clauses (session/time/tool filters, keywords) so SELECT statements stay fast and bounded.

## Tool Contract (`history_sql`)
- **Statements**: Single SELECT/INSERT/UPDATE with positional or named parameters; DELETE/DROP/ALTER rejected.
- **Result caps**: SELECT responses limited (default 50, up to 200) to keep payloads bounded.
- **Outputs**: Operation type, execution time, columns, rows (JSON objects), truncation flag, and rowcount/last_insert_rowid for writes.

## Agent Prompt Updates
- Document in README (high-level) that extended history exists; place detailed guidance + examples in `docs/HISTORY_TOOL.md`.
- **Prompt budget guardrails**: keep guidance compact (≤2 sentences) while encoding the rules below so payload stays lean.
- System instructions snippet:
  > If user intent references past work or you detect gaps beyond the last ~10 tool calls, invoke `history_sql` with a concise SELECT (short keywords/WHERE clauses) before replying. Only include the relevant portions of results in your response.
- Teach the agent explicit triggers, e.g., “user mentions ‘earlier session’,” “self is unsure whether prior step exists,” or “must cite precedent,” plus a reminder to avoid redundant history lookups when current context already covers the question.
- Ensure `get_context.available_tools.all` includes `history_sql` so tooling/CLI surfaces it.

## Gains
- **User**: Can reference weeks-old tasks; agent can cite precise past outputs, reducing repeated troubleshooting.
- **System**: Structured, queryable archive aids debugging and analytics (pattern detection, regression tracking).
- **Agent**: Keeps prompts lean while still offering “extended memory on demand.”

## Implementation Tasks (for beads)
1. Create & bootstrap database (auto-validate schema, backfill JSONL).
2. Record finalized tool interactions into both JSONL and DB.
3. Implement `history_schema` + `history_sql` tools with tests.
4. Update docs, `get_context`, and prompts so both tools are discoverable.
5. (Optional follow-up) Provide summarization helpers for very long result sets or topic clustering.

This plan aligns with the user directive: the agent keeps lightweight working memory but can deliberately consult a permanent, searchable history whenever needed.
