# Curl Tool Implementation Plan

**Status:** Validated by Oracle + Librarian Research  
**Complexity:** Medium (L-size, ~1-2 days)  
**Priority:** High - Replaces ad-hoc shell curl commands with structured HTTP capability

---

## Executive Summary

Build a single `http_request` tool that wraps curl (subprocess), returns structured JSON envelope, supports profiles, sessions, and auto-parsing (JSON only for MVP). Maintains shell-first philosophy while providing structured outputs and safety guardrails.

**Key Decision:** Use **subprocess curl** (not Python HTTP libs) to align with shell-first philosophy and avoid new dependencies.

---

## Architecture

### 1. Tool Structure

**Class:** `HttpRequestTool(BaseTool)` in `tools.py`

**Name:** `http_request`

**Interface:** Single tool with comprehensive parameters (simpler for LLM than multiple tools)

**Response Format:** JSON string envelope (agent already handles tool outputs as text)

### 2. Core Components

```
HttpRequestTool
├── Schema Definition (JSON schema for function calling)
├── Security Layer (SSRF protection, protocol validation)
├── Profile Manager (predefined configurations)
├── Session Manager (cookies, auth, headers)
├── Request Builder (curl command construction)
├── Response Parser (JSON auto-detect, body handling)
└── Trace Logger (integration with event system)
```

---

## Tool Schema Design

### Input Parameters

```python
{
    "type": "function",
    "function": {
        "name": "http_request",
        "description": "Execute HTTP/HTTPS requests with structured responses, session management, and safety guardrails",
        "parameters": {
            "type": "object",
            "properties": {
                # Core request
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                    "default": "GET"
                },
                "url": {
                    "type": "string",
                    "description": "Target URL (http/https only)"
                },
                
                # Request data
                "params": {
                    "type": "object",
                    "description": "URL query parameters as key-value pairs"
                },
                "headers": {
                    "type": "object",
                    "description": "HTTP headers as key-value pairs"
                },
                "body_json": {
                    "type": "object",
                    "description": "JSON body (auto-serialized, sets Content-Type)"
                },
                "body_form": {
                    "type": "object",
                    "description": "Form data (application/x-www-form-urlencoded)"
                },
                "body_raw": {
                    "type": "string",
                    "description": "Raw body string (set Content-Type via headers)"
                },
                
                # Behavior controls
                "timeout_sec": {
                    "type": "integer",
                    "description": "Request timeout (overrides profile default)"
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Maximum response size (overrides profile default)"
                },
                "follow_redirects": {
                    "type": "boolean",
                    "default": True
                },
                
                # Parsing controls
                "parse": {
                    "type": "string",
                    "enum": ["auto", "none", "json"],
                    "default": "auto",
                    "description": "Response parsing mode (MVP: json only)"
                },
                "json_pointer": {
                    "type": "string",
                    "description": "RFC 6901 JSON pointer to extract (e.g., '/data/items/0')"
                },
                
                # Session management
                "session_id": {
                    "type": "string",
                    "description": "Named session for cookies/auth reuse"
                },
                "session_update": {
                    "type": "object",
                    "description": "Update session defaults: {default_headers, auth_bearer, api_key}"
                },
                
                # Profile & advanced
                "profile": {
                    "type": "string",
                    "enum": ["quick_fetch", "gentle_crawl", "deep_audit"],
                    "default": "quick_fetch",
                    "description": "Preset configuration (timeout/retries/limits)"
                },
                "retries": {
                    "type": "integer",
                    "description": "Number of retries (overrides profile)"
                },
                "rate_limit_per_host_per_min": {
                    "type": "integer",
                    "description": "Max requests/min for this host (overrides profile)"
                },
                "allow_insecure_tls": {
                    "type": "boolean",
                    "default": False,
                    "description": "Allow invalid TLS certs (requires HTTP_ALLOW_INSECURE=1 env)"
                }
            },
            "required": ["url"]
        }
    }
}
```

### Output Envelope (Enhanced with curl metrics)

```json
{
    "ok": true,
    "status": 200,
    "status_text": "OK",
    "url": "https://api.example.com/data",
    "url_final": "https://api.example.com/data?page=1",
    "headers": {
        "content-type": "application/json",
        "cache-control": "public, max-age=300"
    },
    "content_type": "application/json",
    "body_preview": "{\"items\": [...]}",
    "body_path": "ai-terminal-wd/http_bodies/a3f8e2d1.body",
    "parsed": {"items": [...]},
    "extracted": {...},
    "metrics": {
        "time_total": 0.234,
        "time_namelookup": 0.056,
        "time_connect": 0.089,
        "time_appconnect": 0.123,
        "time_starttransfer": 0.198,
        "speed_download": 195274.46,
        "size_download": 45678,
        "size_upload": 0,
        "redirect_count": 0,
        "http_connect": 0,
        "remote_ip": "93.184.216.34",
        "remote_port": 443,
        "local_ip": "192.168.1.100",
        "local_port": 54321,
        "bytes_truncated": false
    },
    "trace_id": "a3f8e2d1",
    "session_id": "my-api",
    "curl_exit_code": 0,
    "error": null
}
```

**Metrics Breakdown:**
- `time_namelookup` - DNS lookup time (SSRF/routing validation)
- `time_connect` - TCP connect time (network latency)
- `time_appconnect` - TLS handshake time (security validation)
- `time_starttransfer` - TTFB (server processing time)
- `remote_ip` - Actual IP resolved (cross-check against SSRF blocklist)
- `speed_download` - Bytes/sec (throughput metric)

**Error Response:**
```json
{
    "ok": false,
    "status": 429,
    "error": {
        "type": "http_error",
        "code": 429,
        "message": "Too Many Requests",
        "retryable": true,
        "retry_after_seconds": 60
    },
    "trace_id": "b4c9f3e2",
    ...
}
```

---

## Implementation Details

### 1. Profile System

Profiles map to safe defaults without requiring the agent to specify every parameter:

```python
PROFILES = {
    "quick_fetch": {
        "timeout": 10,
        "retries": 1,
        "follow_redirects": True,
        "max_bytes": 2 * 1024 * 1024,  # 2MB
        "rate_limit_per_host": 30,  # 30 req/min
        "min_interval_sec": 0
    },
    "gentle_crawl": {
        "timeout": 20,
        "retries": 2,
        "follow_redirects": True,
        "max_bytes": 4 * 1024 * 1024,  # 4MB
        "rate_limit_per_host": 10,  # 10 req/min
        "min_interval_sec": 1  # 1 second between requests
    },
    "deep_audit": {
        "timeout": 45,
        "retries": 3,
        "follow_redirects": True,
        "max_bytes": 8 * 1024 * 1024,  # 8MB
        "rate_limit_per_host": 4,  # 4 req/min
        "min_interval_sec": 0,
        "verbose_metrics": True
    }
}
```

### 2. Session Management

**In-Memory State:**
```python
_HTTP_SESSIONS = {}  # {session_id: SessionState}

class SessionState:
    default_headers: Dict[str, str]
    auth_bearer: Optional[str]
    api_keys: Dict[str, str]  # {header_name: value}
    cookie_jar_path: Path
    last_request_times: Dict[str, float]  # {host: timestamp}
    rate_limits: Dict[str, int]  # {host: requests_per_min}
```

**Persistence:**
- Cookie jars: `ai-terminal-wd/.http_sessions/{session_id}/cookies.txt` (mode 0600)
- Optional non-secret metadata: `ai-terminal-wd/.http_sessions/{session_id}/session.json` (only if `HTTP_SESSION_PERSIST=1`)
- **Never persist:** Authorization headers, bearer tokens, API keys (memory only)

### 3. Security Guardrails

**SSRF Protection:**
```python
def validate_url(url: str) -> tuple[bool, str]:
    """
    1. Check protocol (http/https only)
    2. Parse and extract hostname
    3. DNS resolve hostname
    4. Check all IPs against blocklist:
       - 10.0.0.0/8 (Private-Use)
       - 127.0.0.0/8 (Loopback)
       - 169.254.0.0/16 (Link Local)
       - 172.16.0.0/12 (Private-Use)
       - 192.168.0.0/16 (Private-Use)
       - IPv6 equivalents (fc00::/7, ::1/128, fe80::/10)
       - Multicast, broadcast ranges
    5. Reject if any IP is blocked
    
    Returns: (is_valid, error_message)
    """
```

**Redaction:**
```python
REDACT_HEADERS = {
    "Authorization", "Cookie", "Set-Cookie", 
    "X-API-Key", "X-Auth-Token", "Proxy-Authorization"
}

def redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Replace sensitive header values with [REDACTED]"""
    return {
        k: "[REDACTED]" if k in REDACT_HEADERS else v
        for k, v in headers.items()
    }
```

### 4. Curl Command Construction

```python
def build_curl_command(
    method: str,
    url: str,
    headers: Dict[str, str],
    body: Optional[str],
    timeout: int,
    follow_redirects: bool,
    max_bytes: int,
    cookie_jar: Optional[Path],
    output_body: Path,
    output_headers: Path
) -> List[str]:
    """
    Build curl command with safety flags:
    - -sS: Silent but show errors
    - --compressed: Accept compression
    - --fail-with-body: Get body even on HTTP errors
    - --location: Follow redirects (if enabled)
    - --max-time: Total timeout
    - --connect-timeout: Connection timeout (5s)
    - -D: Dump headers
    - -o: Output body
    - -w: Write metrics template
    - --max-filesize: Size limit (pre-check)
    """
    cmd = ["curl", "-sS", "--compressed", "--fail-with-body"]
    
    if follow_redirects:
        cmd.append("--location")
    
    cmd.extend(["--max-time", str(timeout)])
    cmd.extend(["--connect-timeout", "5"])
    
    if max_bytes:
        cmd.extend(["--max-filesize", str(max_bytes)])
    
    cmd.extend(["-D", str(output_headers)])
    cmd.extend(["-o", str(output_body)])
    
    # Metrics template
    cmd.extend(["-w", "%{http_code} %{size_download} %{time_total} %{num_redirects} %{remote_ip}"])
    
    if cookie_jar:
        cmd.extend(["--cookie", str(cookie_jar)])
        cmd.extend(["--cookie-jar", str(cookie_jar)])
    
    for k, v in headers.items():
        cmd.extend(["-H", f"{k}: {v}"])
    
    if method != "GET":
        cmd.extend(["--request", method])
    
    if body:
        cmd.extend(["--data-binary", body])
    
    cmd.append(url)
    return cmd
```

### 5. Response Parsing

```python
def parse_response(
    status: int,
    headers: Dict[str, str],
    body_path: Path,
    parse_mode: str,
    json_pointer: Optional[str]
) -> Dict[str, Any]:
    """
    1. Read body from file
    2. Determine content type
    3. If parse=auto and content-type is JSON:
       - Parse if size <= 256KB
       - Otherwise set parsed=null, provide body_path
    4. If json_pointer provided and parsed exists:
       - Extract using RFC 6901 pointer
    5. Always provide body_preview (first 2-4KB)
    """
    content_type = headers.get("content-type", "")
    body = body_path.read_bytes()
    
    body_preview = body[:4096].decode("utf-8", errors="replace")
    
    parsed = None
    extracted = None
    
    if parse_mode == "json" or (
        parse_mode == "auto" and "json" in content_type
    ):
        if len(body) <= 256 * 1024:  # 256KB
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                pass
        
        if parsed and json_pointer:
            extracted = extract_json_pointer(parsed, json_pointer)
    
    return {
        "body_preview": body_preview,
        "body_path": str(body_path) if len(body) > 8192 else None,
        "parsed": parsed,
        "extracted": extracted
    }
```

### 6. Rate Limiting

```python
class RateLimiter:
    """Simple per-host token bucket"""
    
    def __init__(self):
        self.last_request: Dict[str, float] = {}  # {host: timestamp}
        self.request_count: Dict[str, deque] = {}  # {host: [timestamps]}
    
    def check_rate_limit(
        self, 
        host: str, 
        limit_per_min: int,
        min_interval_sec: float
    ) -> tuple[bool, float]:
        """
        Returns: (allowed, wait_seconds)
        """
        now = time.time()
        
        # Check minimum interval
        if host in self.last_request:
            elapsed = now - self.last_request[host]
            if elapsed < min_interval_sec:
                return False, min_interval_sec - elapsed
        
        # Check requests per minute
        if host not in self.request_count:
            self.request_count[host] = deque(maxlen=limit_per_min)
        
        # Remove old timestamps
        window_start = now - 60
        while self.request_count[host] and self.request_count[host][0] < window_start:
            self.request_count[host].popleft()
        
        if len(self.request_count[host]) >= limit_per_min:
            oldest = self.request_count[host][0]
            wait = 60 - (now - oldest)
            return False, wait
        
        return True, 0
    
    def record_request(self, host: str):
        """Record successful request"""
        now = time.time()
        self.last_request[host] = now
        if host not in self.request_count:
            self.request_count[host] = deque()
        self.request_count[host].append(now)
```

### 7. Trace Logging

```python
def write_trace_file(trace_id: str, envelope: Dict[str, Any]):
    """
    Write minimal trace to ai-terminal-wd/http_traces/trace-{trace_id}.json
    
    Excludes:
    - body_preview (too large)
    - Full body content
    - Secret headers (already redacted)
    
    Includes:
    - Request metadata (method, url, session_id)
    - Response metadata (status, headers, metrics)
    - Error details
    - Timing information
    """
    trace_dir = Path(WORKING_DIR_PREFIX) / "http_traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    
    trace_data = {
        "trace_id": trace_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": {
            "method": envelope.get("request_method"),
            "url": envelope["url"],
            "session_id": envelope.get("session_id")
        },
        "response": {
            "ok": envelope["ok"],
            "status": envelope.get("status"),
            "content_type": envelope.get("content_type"),
            "size": envelope["metrics"]["size_download"],
            "time": envelope["metrics"]["time_total"]
        },
        "error": envelope.get("error")
    }
    
    trace_path = trace_dir / f"trace-{trace_id}.json"
    trace_path.write_text(json.dumps(trace_data, indent=2))
```

---

## Curl-Specific Innovations (from Everything-Curl research)

### 1. Persistent Subprocess Sessions
**Discovery:** curl maintains connection pools; spawning new processes per request defeats this.

**Innovation:** Keep curl subprocess alive per session_id, pipe requests via stdin with `--next` (batch requests)
```bash
# Instead of: spawn curl, parse output, close
# Do: keep session_fd open, write requests, read responses
curl \
  --config ai-terminal-wd/.http_sessions/{session_id}/.curlrc \
  --next https://api1.example.com \
  --next https://api2.example.com
```

**Benefit:** Connection reuse within session, cookie jar persistence, TLS session resumption

### 2. Enhanced Error Classification
**Discovery:** curl has 30+ exit codes; our plan only covers ~10 error types.

**Mapping:**
- Exit code 6 → "dns_error" (host not found)
- Exit code 7 → "connect_error" (connection refused)
- Exit code 28 → "timeout" (already have)
- Exit code 35 → "tls_error" (SSL/TLS handshake failed)
- Exit code 60 → "tls_cert_error" (SSL peer certificate cannot be authenticated)
- Expand error_types dict to cover curl's full range

### 3. Built-In Metrics Leverage
**Discovery:** curl outputs timing data with `-w` format string.

**Enhancement:** Use curl's write-out variables instead of manual timing:
```bash
curl -w '\n{
  "time_total": %{time_total},
  "time_connect": %{time_connect},
  "time_namelookup": %{time_namelookup},
  "time_appconnect": %{time_appconnect},
  "speed_download": %{speed_download},
  "size_download": %{size_download},
  "http_code": %{http_code},
  "remote_ip": %{remote_ip}
}' "$@"
```

**Benefit:** Accurate timing, DNS+TLS+connect breakdown, remote IP for logging/SSRF detection

### 4. Curl Config File Pattern for Session Defaults
**Discovery:** curl reads `.curlrc` (or `curl.cfg` on Windows) for persistent defaults.

**Innovation:** Store session defaults in `.http_sessions/{session_id}/.curlrc`:
```
# Session config for "api-github"
user-agent = "ai-terminal/1.0"
header = "Authorization: Bearer token_xxx"
header = "X-Custom-Header: value"
cookie-jar = ".http_sessions/api-github/cookies.txt"
cookie = ".http_sessions/api-github/cookies.txt"
```

**Benefit:** Cleaner code, session state isolated to directory, curl handles defaults automatically

### 5. Password/Auth Hygiene
**Discovery:** curl offers multiple safe auth patterns (netrc, stdin prompt, config files).

**Implementation:**
- Bearer tokens stored in session config (encrypted at rest, optional)
- API keys stored in session config (encrypted at rest, optional)
- Basic auth only via `--user file` (curl reads from file, not cmdline)
- OAuth flows use opaque refresh tokens in session state

### 6. Variable Expansion for Agent Requests
**Discovery:** curl's `--variable` + `--expand-*` allows templating (e.g., `{{host:trim:url}}`).

**Future:** Could expose this to agent for dynamic request building:
```
http_request(
  url="https://{{api_host}}/{{endpoint:url}}",
  session_id="api-session",  # has api_host, endpoint defined
  body_json={"key": "{{value:trim:json}}"}
)
```

---

## JSON & Response Parsing Innovations (from Everything-Curl research)

### 1. Native JSON Output Format
**Discovery:** curl `-w json` outputs ALL metrics as a single JSON object (curl 7.72.0+).

**Innovation:** Use native curl JSON output for metrics instead of manual parsing:
```bash
curl -w '\n%{json}' https://example.com/ > response_with_metrics.json
```

**Output includes:** status, url, headers, content_type, time_total, time_namelookup, time_connect, time_appconnect, speed_download, remote_ip, ssl_verify_result, num_redirects, **and more** (~30 metrics)

**Benefit:** Zero custom parsing, guaranteed accuracy, covers all edge cases curl tracks

### 2. Write-Out Variables for Rich Metadata
**Discovery:** curl exposes 30+ `--write-out` variables covering all aspects of the transfer.

**Key Variables NOT in basic metrics:**
- `content_type` - Response Content-Type (for auto-parsing detection)
- `num_certs` - Number of certs in TLS chain (7.88.0+)
- `certs` - Full certificate chain details (7.88.0+)
- `num_redirects` - Count of HTTP redirects followed
- `redirect_url` - URL a redirect would lead to (without -L)
- `http_version` - HTTP version used (1.0, 1.1, 2.0, 3)
- `method` - HTTP method that was used (7.72.0+)
- `size_header` - Bytes downloaded in headers only
- `size_request` - Bytes sent in request
- `ssl_verify_result` - SSL cert verification result (0=success)
- `proxy_ssl_verify_result` - Proxy SSL verification result
- `errormsg` - Human-readable error message (7.75.0+)
- `exitcode` - Curl's exit code (7.75.0+)
- `url.*` - URL component extraction (scheme, host, path, user, password) [curl 8.1.0+]

**Benefit:** Comprehensive transfer metadata for rich diagnostics and debugging

### 3. Automatic Content-Type Detection for Parsing
**Discovery:** curl reports `content_type` which can guide auto-parsing strategy.

**Implementation:**
```python
# Use curl's content_type to decide parsing strategy
content_type = metrics.get("content_type", "")
if "application/json" in content_type:
    parse_mode = "json"
elif "text/html" in content_type:
    parse_mode = "html"  # Future: BeautifulSoup
elif "application/xml" in content_type:
    parse_mode = "xml"   # Future: lxml
else:
    parse_mode = "none"
```

**Benefit:** Auto-detect format without agent intervention, future-proof for HTML/XML parsing

### 4. Verbose Mode Headers Extraction
**Discovery:** curl `-v` outputs all headers with prefixes (`>` request, `<` response).

**Enhancement:** Parse verbose output to extract:
- All request headers sent
- All response headers received
- Request line (method, path, HTTP version)
- Response status line (HTTP version, code, reason)

**Format:**
```
> GET /api/users HTTP/1.1
> Host: api.example.com
> Authorization: Bearer [REDACTED]
> Content-Type: application/json
>
< HTTP/1.1 200 OK
< Content-Type: application/json
< Cache-Control: public, max-age=300
< X-RateLimit-Remaining: 4999
<
```

**Benefit:** Full request/response header visibility for debugging, extract rate-limit headers programmatically

### 5. JSON-Native Input/Output with jo/jq
**Discovery:** curl plays well with external JSON tools (jo for building, jq for parsing).

**Philosophy alignment:** Shell-first approach - use native tools:
```bash
# Build JSON with jo
jo name=alice age=30 | curl --json @- https://api.example.com/users

# Parse response with jq
curl https://api.example.com/users | jq '.[] | select(.status=="active")'
```

**For agent:** We can't rely on user having jq installed, but our tool can:
- Accept pre-built JSON in `body_json` parameter (agent builds it)
- Return parsed JSON from `parsed` field (we parse it)
- Support JSON pointer extraction as alternative to jq

**Benefit:** Composable with shell workflows, familiar for Unix power users

### 6. Certificate Chain Inspection
**Discovery:** curl 7.88.0+ supports `%{certs}` to output full TLS certificate chain details.

**Use case:** Security validation, certificate pinning, trust chain verification.

**Future enhancement:** Store cert fingerprints, validate against pinned certs in session config.

---

## Implementation Phases

### Phase 1: Core Tool (Priority: Critical)
**Estimate:** 4-6 hours

- [ ] Define `HttpRequestTool` class structure
- [ ] Implement profile system (3 profiles)
- [ ] Build curl command constructor
- [ ] Parse curl output (status, headers, body)
- [ ] Return JSON envelope
- [ ] Basic error handling

**Deliverable:** Working GET requests with structured responses

### Phase 2: Security & Validation + Enhanced Error Handling (Priority: Critical)
**Estimate:** 3-5 hours

- [ ] SSRF protection (IP blocklist validation + remote_ip check from curl)
- [ ] Protocol validation (http/https only)
- [ ] Header redaction (Authorization, Cookie, etc.) with secure logging
- [ ] Size limits enforcement (max_bytes)
- [ ] Timeout enforcement
- [ ] **Curl exit code mapping** (1→protocol_error, 6→dns_error, 7→connect_error, 28→timeout, 35→tls_error, 60→tls_cert_error, etc.)
- [ ] **Build curl metrics into envelope** (time_namelookup, time_connect, time_total, speed_download, remote_ip)
- [ ] **HTTP status classification** (4xx→client error, 5xx→server_error, 429→rate_limit indicator)

**Deliverable:** Hardened tool with rich error metadata and diagnostic metrics

### Phase 3: Session Management (Priority: High)
**Estimate:** 3-4 hours

- [ ] In-memory session registry
- [ ] Cookie jar persistence (per session)
- [ ] Default headers injection
- [ ] Auth token handling (bearer, API keys)
- [ ] Session update API

**Deliverable:** Reusable sessions across requests

### Phase 4: Advanced Features + JSON Parsing (Priority: Medium)
**Estimate:** 4-6 hours

- [ ] Rate limiting (per-host token bucket)
- [ ] **JSON auto-parsing** using curl's native `-w %{json}` + content-type detection
- [ ] **JSON pointer extraction** (RFC 6901) with fallback via jq if available
- [ ] **Auto-detect content-type** (json/html/xml) and set parse mode
- [ ] **Verbose header extraction** (parse `-v` output for request/response headers)
- [ ] **Rich metadata** from all 30+ write-out variables (not just metrics)
- [ ] Retry logic with backoff
- [ ] POST/PUT/PATCH support (body_json, body_form, body_raw)
- [ ] **Certificate chain output** (if curl 7.88.0+, include cert fingerprints)

**Deliverable:** Full-featured HTTP client with rich JSON parsing and metadata

### Phase 5: Integration & Polish (Priority: High)
**Estimate:** 2-3 hours

- [ ] Trace file logging (http_traces/)
- [ ] Body artifact persistence (http_bodies/)
- [ ] Event memory integration (record tool calls)
- [ ] Session state integration (track exit codes)
- [ ] Documentation (tool usage examples)

**Deliverable:** Fully integrated with existing agent systems

### Phase 6: Testing (Priority: Critical)
**Estimate:** 2-3 hours

- [ ] Unit tests (URL validation, parsing, profiles)
- [ ] Integration tests (live GET/POST requests)
- [ ] Security tests (SSRF attempts, redaction)
- [ ] Session persistence tests
- [ ] Error handling tests

**Deliverable:** Tested, production-ready tool

---

## Environment Variables

```bash
# Optional configuration
HTTP_ALLOW_INSECURE=0          # Allow self-signed certs (default: disabled)
HTTP_SESSION_PERSIST=0          # Persist session metadata to disk (default: disabled)
HTTP_MAX_BODY_PREVIEW=4096      # Max chars in body_preview (default: 4KB)
HTTP_DEFAULT_TIMEOUT=10         # Default timeout seconds (default: 10)
HTTP_DEFAULT_MAX_BYTES=2097152  # Default max response size (default: 2MB)
```

---

## File Structure

```
ai-terminal-wd/
├── .http_sessions/
│   ├── {session_id}/
│   │   ├── cookies.txt          # Netscape cookie format (mode 0600)
│   │   └── session.json         # Optional non-secret metadata
│   └── ...
├── http_bodies/
│   ├── {trace_id}.body          # Large response bodies
│   ├── {trace_id}.headers       # Response headers (raw)
│   └── ...
└── http_traces/
    ├── trace-{trace_id}.json    # Minimal request/response metadata
    └── ...
```

---

## Error Types (Aligned with curl exit codes)

```python
ERROR_TYPES = {
    # Protocol/URL errors
    "protocol_error": "Invalid protocol (only http/https allowed) [curl 1]",
    "url_malformed": "URL syntax incorrect [curl 3]",
    
    # DNS/Network errors
    "dns_error": "Hostname not resolved / DNS failure [curl 6]",
    "connect_error": "Connection refused or unreachable [curl 7]",
    "network_error": "Network unreachable or I/O error [curl 28+]",
    
    # TLS/Security errors
    "tls_error": "TLS/SSL handshake failed [curl 35]",
    "tls_cert_error": "SSL certificate cannot be authenticated [curl 60]",
    "ssrf_error": "Request blocked (private/loopback IP) [security check]",
    
    # Timeout errors
    "timeout": "Request timeout exceeded [curl 28]",
    "connect_timeout": "Connection timeout [curl 28]",
    "dns_timeout": "DNS resolution timeout [curl 28]",
    
    # HTTP errors
    "http_error": "HTTP error response (4xx/5xx) [non-2xx]",
    "http_422": "Unprocessable entity (validation) [curl 22+]",
    "http_429": "Too many requests (rate limited) [curl 22+]",
    "http_503": "Service unavailable (temporary) [curl 22+]",
    
    # Size/content errors
    "size_error": "Response exceeds max_bytes limit [custom limit]",
    "parse_error": "Failed to parse response body [JSON parse error]",
    "content_error": "Invalid or corrupted response content [custom validation]",
    
    # Rate limiting
    "rate_limit": "Rate limit exceeded for host [token bucket]",
    
    # Functional errors
    "auth_error": "Authentication failed (401/403) [HTTP 401/403]",
    "resource_not_found": "Resource not found [HTTP 404]",
    "server_error": "Internal server error (5xx) [HTTP 5xx]"
}
```

---

## Success Criteria

- [ ] Single `http_request` tool auto-registered in TOOLS
- [ ] Agent can make GET requests and receive structured JSON
- [ ] SSRF protection blocks private IPs
- [ ] Sessions persist cookies across requests
- [ ] Large responses saved to files with preview
- [ ] Trace logs integrated with event system
- [ ] All tests passing
- [ ] Documentation complete

---

## Testing Strategy

### Unit Tests
```python
def test_url_validation():
    assert validate_url("http://example.com")[0] == True
    assert validate_url("https://api.github.com")[0] == True
    assert validate_url("ftp://example.com")[0] == False
    assert validate_url("http://127.0.0.1")[0] == False
    assert validate_url("http://192.168.1.1")[0] == False

def test_profile_loading():
    profile = get_profile("quick_fetch")
    assert profile["timeout"] == 10
    assert profile["retries"] == 1

def test_header_redaction():
    headers = {"Authorization": "Bearer token123", "Content-Type": "application/json"}
    redacted = redact_headers(headers)
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["Content-Type"] == "application/json"
```

### Integration Tests
```python
def test_simple_get():
    tool = HttpRequestTool()
    result = tool.execute(url="https://httpbin.org/get")
    envelope = json.loads(result)
    assert envelope["ok"] == True
    assert envelope["status"] == 200

def test_session_cookies():
    tool = HttpRequestTool()
    # Set cookie
    tool.execute(url="https://httpbin.org/cookies/set?session=abc123", session_id="test")
    # Verify cookie persisted
    result = tool.execute(url="https://httpbin.org/cookies", session_id="test")
    envelope = json.loads(result)
    assert "session" in envelope["parsed"]["cookies"]
```

---

## Migration Path

1. **Deploy tool** - Add to tools.py, auto-registers
2. **Update system prompt** - Mention http_request capability
3. **Monitor usage** - Track via event logs
4. **Iterate** - Add features based on real usage patterns

**No breaking changes** - Existing run_command + curl still works

---

## Future Enhancements (Post-MVP)

- HTML parsing with BeautifulSoup/selectolax (CSS selectors)
- XML parsing with lxml (XPath support)
- Pagination helpers (Link header parsing)
- Schema validation (JSON Schema, Pydantic)
- OAuth flows (device code, PKCE)
- mTLS support
- SOCKS proxy support
- WebSocket upgrade path
- GraphQL query builder
- Parallel batch requests

---

## References

**Oracle Consultation:** Validated architecture, security model, and integration strategy

**Librarian Research:**
- LangChain HTTP patterns (layered wrapper, session reuse)
- AutoGPT SSRF protection (IP blocklist validation)
- OpenAI Agents schema design (Pydantic + strict mode)
- Qwen-Agent HTML cleaning (BS4 patterns)

**Alignment:**
- Shell-first philosophy (subprocess curl, not httpx/requests)
- Tool auto-registration pattern (BaseTool subclass)
- Event memory integration (trace logs, artifacts)
- ReAct loop compatibility (structured JSON output)

---

## Quick Reference: Key Curl Flags for Implementation

```bash
# Metrics extraction (native JSON output)
curl -w '\n%{json}' "$url"          # ALL metrics as single JSON object

# Verbose mode with headers (for rich debugging)
curl -v "$url"                       # Shows all request/response headers

# Custom format string (for specific metrics)
curl -w 'Status: %{http_code}, IP: %{remote_ip}, Time: %{time_total}s' "$url"

# Session state (cookies, headers)
curl -b cookies.txt -c cookies.txt  # Read & write cookies
curl --config .curlrc               # Read session config file

# Security & limits
curl --max-time 10                  # Timeout: 10 seconds
curl --max-filesize 10485760        # Max response: 10MB
curl -k                             # Allow insecure TLS (flag it)

# Request building
curl -H "Header: value"             # Custom header
curl -d @- < input.json             # Read body from stdin
curl --json @- < payload.json       # JSON body from stdin
curl -X POST                        # Override HTTP method

# Error handling & retries
curl --retry 3 --retry-delay 1      # Retry logic
curl --fail                         # Fail on HTTP 4xx/5xx
curl --fail-with-body               # Include body in error response

# Data encoding
curl --data-urlencode "key=value"   # URL-encode form data
```

**For our tool, we'll use:**
1. `-w '\n%{json}'` for metrics (Phase 1)
2. `-v` conditionally for verbose/debug output (Phase 4)
3. `--config .curlrc` for session management (Phase 3)
4. Custom `-H` headers for auth/api-keys (Phase 3)
5. `-d @-` / `--json @-` for request bodies (Phase 1)
6. `--max-time` / `--max-filesize` for limits (Phase 1)
7. Built-in error handling via exit codes (Phase 2)
