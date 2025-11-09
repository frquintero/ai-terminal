# `http_request` Tool Cheat Sheet

The AI terminal now exposes a first-class curl wrapper so the agent can reason about HTTP work without shell gymnastics. The schema advertises every knob, but this cheat sheet summarizes the most useful groups of options.

## Profiles & Sessions
- `profile`: `quick_fetch`, `gentle_crawl`, `deep_audit` – tune timeout, retries, politeness intervals.
- `session_id` + `session_update`: persist cookies, default headers, bearer/API keys per session.
- `min_interval_sec`: throttle the target host beyond the profile defaults (per-host delay enforced by the tool).

## Request Construction
- `method`, `url`, `params`, `headers`.
- Bodies: `body_json`, `body_form`, or `body_raw` (mutually exclusive). Content-Type auto-filled for JSON/form.
- `accept_compression`: enables `--compressed`.
- `follow_redirects` + `max_redirects`.
- `variables`: per-call template variables surfaced to all strings via `{{name}}` (supports filters like `{{token|trim}}`, `{{email|lower}}`).
- `session_update.variables`: persist template variables with a session for repeated use.

### Template Variables & JSON Composition
- Any string field (URL, params, headers, JSON/form/body payloads) can reference `{{variable}}` placeholders.
- Filters: `trim`, `upper`, `lower`, `url` (URL-encode), `json` (JSON-escape string).
- Combine session-scoped variables (set once via `session_update`) with per-call overrides for fast API work. This replaces manual `jo` invocations—the tool handles JSON serialization and templating automatically.

## Networking Controls
- `proxy`: HTTP/HTTPS/SOCKS proxies with full URL syntax.
- `dns_servers`: comma-separated list passed to `curl --dns-servers`.
- `bind_interface`: pin the request to a local interface/IP.
- `http_version`: force HTTP `1.0`, `1.1`, `2`, `3`, or `auto`.
- `allow_insecure_tls`: opt-in self-signed certificates.
- `allow_local_networks`: override SSRF guard (loopback/private IPs are blocked by default).

## Parsing & Extraction
- `parse_mode`: `auto`, `json`, `none`.
- `json_pointer`: RFC 6901 pointer to pluck nested values after parsing.
- `json_selector`: run a jq expression (`.data[] | {id, status}`) when jq is installed. Results surface via `json_selector_value`.
- `save_body`: force persistence of the full body under `ai-terminal-wd/http_bodies/` even when short.
- Verbose headers remain enabled by default (`verbose_headers=True`) so the agent can inspect request/response chains.

## Diagnostics & Telemetry
- Native curl `%{json}` metrics surface DNS/TLS/TTFB timings, byte counts, redirect info, plus TLS chain details (`%{certs}` when curl ≥7.88).
- Envelope fields include `diagnostics`, `latency`, `http_headers`, `certificate_chain`, and `throttle_delay_sec`.
- SSRF guard upgrades: private/loopback targets are blocked up front and if curl ultimately resolves to a private IP the response is flagged with `error_type = "ssrf_blocked"`.
- `helper_capabilities` reports whether jq/jo binaries are available along with curl's TLS-trace support so MiniAgent knows which selectors/templating paths it can rely on.

Use this tool for any HTTP/API interaction—`run_command` + `curl` should be a last resort. The schema exposed to MiniAgent mirrors the parameters above, so the model always sees the full capability menu before choosing how to call the tool.
