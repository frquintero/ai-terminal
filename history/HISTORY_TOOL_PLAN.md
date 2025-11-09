# History Tool Plan

## Problem & Context
- Session logs show we routinely lose long-running context once `tool_history` is trimmed, which left the mini agent unable to recall prior moon-phase work in session 171.
- JSONL event logging exists, but it only helps humans; the agent still sees a tiny sliding window.
- Users want transparency: every correctly finished interaction must be recoverable, searchable, and callable on demand without bloating every prompt.

## Solution Overview
1. **Permanent Event Store** – Maintain a self-healing SQLite database (e.g., `logs/history/history.db`) that mirrors each finalized tool interaction: session id, timestamps, tool, query, summary, payload pointer.
2. **`history_search` Tool** – A first-class tool in `tools.py` that lets the agent query the store by keywords, time ranges, session numbers, or tool names. Responses return structured snippets plus references back to the JSONL trace if deeper dives are needed.
3. **Agent Guidance & Memory Balance** – Update the MiniAgent system prompt so it knows:
   - use normal `tool_history` for short-term context,
   - call `history_search` whenever the user references work that predates the live window (or when it senses gaps),
   - interpret results as authoritative historical memory.
   - Tighten short-term memory to ~10 interactions (configurable) now that deep history is available, keeping prompts lean without sacrificing recall.

## Data & Storage Design
- **Database**: SQLite, auto-initialized on startup; tables:
  - `events(id INTEGER PK, session_id INT, timestamp TEXT, tool TEXT, action TEXT, summary TEXT, detail_json TEXT, keywords TEXT)`.
  - Optional `attachments` table for paths to stored bodies (`http_traces`, etc.).
- **Auto-bootstrap**: On launch we check schema integrity; if missing or corrupt we recreate and backfill from existing `logs/events/*.jsonl`.
- **Ingestion**: Each successful tool call writes a row. Include derived keywords (normalized text) for fast LIKE queries.
- **Search**: Support filters (`session_id`, `since`, `until`, `tool`, `text`). Apply LIMIT/OFFSET defaults to keep payloads small.

## Tool Contract (`history_search`)
- **Inputs**:
  - `query` (string, optional) – keywords or natural language.
  - `session_id` / `since` / `until` – narrow time ranges.
  - `tool` or `category` hints (optional).
  - `limit` (default 5) to bound results.
- **Outputs**:
  - `matches` array with `session_id`, `timestamp`, `tool`, `summary`, `detail_excerpt`, `source_ref`.
  - `suggestions` (optional) if no hits found (e.g., “Try earlier session 168”).
  - `stats` describing total hits vs returned.

## Agent Prompt Updates
- Document in README (high-level) that extended history exists; place detailed guidance + examples in `docs/HISTORY_TOOL.md`.
- **Prompt budget guardrails**: keep guidance compact (≤2 sentences) while encoding the rules below so payload stays lean.
- System instructions snippet:
  > If user intent references past work or you detect gaps beyond the last ~10 tool calls, invoke `history_search` with succinct keywords (and optional filters) before replying. Only include the relevant portions of results in your response.
- Teach the agent explicit triggers, e.g., “user mentions ‘earlier session’,” “self is unsure whether prior step exists,” or “must cite precedent,” plus a reminder to avoid redundant history lookups when current context already covers the question.
- Ensure `get_context.available_tools.all` includes `history_search` so tooling/CLI surfaces it.

## Gains
- **User**: Can reference weeks-old tasks; agent can cite precise past outputs, reducing repeated troubleshooting.
- **System**: Structured, queryable archive aids debugging and analytics (pattern detection, regression tracking).
- **Agent**: Keeps prompts lean while still offering “extended memory on demand.”

## Implementation Tasks (for beads)
1. Create & bootstrap database (auto-validate schema, backfill JSONL).
2. Record finalized tool interactions into both JSONL and DB.
3. Implement `history_search` tool + tests.
4. Update docs, `get_context`, and prompts so the tool is discoverable.
5. (Optional follow-up) Provide summarization helpers for very long result sets or topic clustering.

This plan aligns with the user directive: the agent keeps lightweight working memory but can deliberately consult a permanent, searchable history whenever needed.
