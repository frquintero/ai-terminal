# Curl Tool Project Snapshot

## Issue / Problem
- Mini agent currently shells out to raw `curl`, producing unstructured blobs, missing response metadata, and offering zero built-in safety (rate limits, retries, auth hygiene).
- Users submit vague “hit this API” requests; the agent spends multiple turns massaging headers, parsing text, and apologizing when `curl` output is unreadable or the request silently fails.
- Lack of shared context makes debugging tough: no trace IDs, no structured errors, and no consistent way to reuse sessions/cookies across requests.

## Solution / Architecture
- Ship a first-class `curl` tool exposed in `tools.py` that wraps HTTP(S) requests and returns a structured envelope (status, headers, parsed body, raw fallback, trace ID).
- Provide user-aligned “profiles” (e.g., Quick Fetch, Gentle Crawl, Deep Audit) that bundle rate/parallelism, retries, header verbosity, and diagnostics switches so the agent can pick intent-appropriate defaults.
- Embed smart parsing (auto-detect JSON/XML/HTML, optional JSONPath/XPath/CSS selectors, HTML-table → JSON conversion) plus optional schema validation and pagination helpers.
- Manage sessions centrally: cookie jars, bearer/OAuth tokens, API keys, and pinned TLS settings live under named session IDs instead of ad-hoc shell history.
- Expose the tool as an explicit “capability menu”: every invocation advertises supported knobs (profiles, selectors, session_id, trace/debug toggles, schema hooks, pagination controls) so the mini agent always sees its full palette before choosing how to proceed.
- Capture every request via trace logs (`logs/openai_traces/<id>.json` + new HTTP trace artifacts) so `get_context` and diagnostics tools can surface failures instantly.

## System & User Gains
- **System:** deterministic tool contract, easier reasoning (structured outputs), reusable auth/context, fewer shell invocations, richer telemetry for debugging.
- **User:** cleaner answers (“Here are the headlines, 200 OK, cached session alpha”), fewer follow-up prompts, safer/bounded web access (rate limits, polite crawling, validation), and faster iteration when exploring APIs or scraping docs.
