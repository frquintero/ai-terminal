# HTTP Request Tool (curl wrapper) - Implementation Spec

## Overview

Replace raw curl usage with a dedicated `http.request` BaseTool that wraps curl, captures structured output (status, headers, body), auto-parses JSON/HTML/XML, applies optional selectors, and returns consistent JSON responses.

**Philosophy**: Shell-first. Leverage curl's robustness instead of reimplementing HTTP in Python.

---

## Architecture Decision: Shell-First Wrapping

### Why wrap curl instead of Python HTTP client?

| Aspect | Curl Wrapper | Python Client |
|--------|-------------|----------------|
| **Dependencies** | None (curl in terminal) | New deps (httpx/requests) |
| **SSL/TLS** | Battle-tested in production | Still good, but added complexity |
| **Auth strategies** | Native support (certs, netrc, Kerberos) | Need to implement |
| **Compression** | Auto via `--compressed` | Need handling |
| **Connection pooling** | Native | Session management |
| **Implementation time** | 1-2 days | 2-3 days |
| **Maintenance** | Curl updates benefit us | Dependency management |

**Decision**: Use curl with `-v` (verbose) + `--write-out` (structured metadata) + temp files for body/headers.

---

## Input Schema

```python
class HttpRequestInput(BaseModel):
    method: str = "GET"  # GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS
    url: str  # http/https only
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, Union[str, int, float, bool, list]]] = None
    body: Optional[Union[str, dict]] = None  # String or JSON-serializable
    
    # Timeouts & redirects
    timeout: float = 30.0  # Clamp 1-120 seconds
    connect_timeout: float = 10.0
    allow_redirects: bool = True
    max_redirects: int = 5  # Clamp 0-10
    
    # Response handling
    parse: bool = True  # Auto-parse JSON/HTML/XML
    max_response_bytes: Optional[int] = None  # Hard cap (default: 10MB)
    artifact_threshold_bytes: int = 512_000  # Store as artifact if >
    
    # Selectors (optional)
    selectors: Optional[Dict[str, Any]] = None
    # {
    #   "json_pointer": "/data/items",  # RFC 6901
    #   "jq": ".items[] | select(.status == 'active')",  # jq filter
    #   "xpath": "//div[@class='price']",  # XPath for HTML/XML
    #   "css": "div.item > span.name"  # CSS selector for HTML
    # }
    
    # Guardrails
    fail_on_http_error: bool = False  # Use curl --fail-with-body
    block_local_network: bool = True  # SSRF protection
    verify_tls: bool = True
    
    # Advanced
    extra_curl_args: Optional[List[str]] = None  # Additional curl flags (validated)
```

---

## Output Schema

```python
class HttpResponse(BaseModel):
    # Request echo
    method: str
    url: str
    effective_url: str  # After redirects
    
    # Response metadata
    status: int
    ok: bool  # 200-299 range
    redirects: int
    timings: Dict[str, float]  # time_total, time_connect, etc.
    
    # Headers
    request_headers: Dict[str, str]  # Sanitized (redact secrets)
    response_headers: Dict[str, str]
    content_type: Optional[str]
    encoding: Optional[str]  # charset from Content-Type
    
    # Body handling
    size_bytes: int
    body_artifact_id: Optional[str]  # If stored as artifact
    body_text: Optional[str]  # If small + text/json
    body_json: Optional[Any]  # If parsed JSON
    body_preview: Optional[str]  # First 2KB if large
    
    # Selections
    selections: Optional[Dict[str, Any]] = None
    # {
    #   "json_pointer": {...},
    #   "jq": "...",
    #   "xpath": [...],
    #   "css": [...]
    # }
    
    # Errors
    error: Optional[Dict[str, Any]] = None
    # {
    #   "type": "curl_error|http_error|timeout|ssrf_blocked|selector_error",
    #   "code": 28,  # curl exit code or HTTP status
    #   "message": "Operation timeout",
    #   "retryable": true,
    #   "details": {...}
    # }
    
    warnings: List[str] = []
```

---

## Command Construction

### Curl Command Builder

```
curl \
  -v                          # Verbose (headers to stderr)
  -s -S                       # Silent + show errors
  --compressed                # Auto-decompress
  --proto =http,https         # Restrict protocols
  -X POST                     # Method (if not GET)
  -H "Key: Value"             # Headers
  --data-binary @/tmp/body    # Body (binary-safe)
  -L --max-redirs 5           # Follow redirects
  --connect-timeout 10        # Connection timeout
  --max-time 30               # Total timeout
  --fail-with-body            # On 4xx/5xx, still return body
  -o /tmp/body                # Write body to file
  -D /tmp/headers             # Write headers to file
  -w '{...}'                  # Structured metadata (stdout)
  https://example.com/api
```

### Write-out Format

```python
write_out = {
    "http_code": "%{http_code}",
    "url_effective": "%{url_effective}",
    "content_type": "%{content_type}",
    "size_download": "%{size_download}",
    "time_total": "%{time_total}",
    "time_connect": "%{time_connect}",
    "time_namelookup": "%{time_namelookup}",
    "num_redirects": "%{num_redirects}",
    "remote_ip": "%{remote_ip}",
    "http_version": "%{http_version}",
}

# Convert to JSON for stdout
curl_args.extend(["-w", json.dumps(write_out)])
```

---

## Parsing Flow

### 1. Execute curl

```python
cmd = build_curl_args(...)  # List of strings
result = run_command(shlex.join(cmd))
# Returns: exit_code, stdout (meta JSON), stderr (verbose output)
```

### 2. Parse metadata (from stdout)

```python
meta = json.loads(result.stdout)
status = meta["http_code"]
effective_url = meta["url_effective"]
content_type = meta["content_type"]
size_bytes = meta["size_download"]
num_redirects = meta["num_redirects"]
```

### 3. Parse headers (from file)

**File format** (curl -D output):
```
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 1234
Set-Cookie: foo=bar

HTTP/1.1 301 Moved Permanently
Location: https://...

HTTP/1.1 200 OK
Content-Type: application/json
```

**Algorithm**:
- Split on blank lines to get blocks
- Skip `HTTP/1.1 100 Continue` interim responses
- Take last block (final response)
- First line is status (e.g., "HTTP/1.1 200 OK")
- Remaining lines are headers (split on first ":")
- Normalize keys to lowercase; combine duplicates with comma

```python
def parse_headers_file(path):
    blocks = []
    current_block = []
    
    with open(path) as f:
        for line in f:
            line = line.rstrip('\r\n')
            if not line:
                if current_block:
                    blocks.append(current_block)
                    current_block = []
            else:
                current_block.append(line)
        if current_block:
            blocks.append(current_block)
    
    # Take last block (final response)
    if not blocks:
        return {}, None
    
    final = blocks[-1]
    status_line = final[0]  # e.g., "HTTP/1.1 200 OK"
    headers_lines = final[1:]
    
    headers = {}
    for line in headers_lines:
        if ':' not in line:
            continue
        key, val = line.split(':', 1)
        key = key.lower().strip()
        val = val.strip()
        
        # Combine duplicates with comma
        if key in headers:
            headers[key] += f", {val}"
        else:
            headers[key] = val
    
    return headers, status_line
```

### 4. Handle body

```python
size_bytes = os.path.getsize(body_file)

if size_bytes > artifact_threshold_bytes:
    # Large response: store as artifact
    artifact_id = save_artifact(body_file, metadata={...})
    body_text = None
    preview = read_preview(body_file, 2048)  # First 2KB
else:
    # Small response: read into memory
    with open(body_file, 'rb') as f:
        raw = f.read()
    
    # Determine encoding
    charset = extract_charset_from_content_type(content_type)
    if charset is None:
        charset = 'utf-8'
    
    try:
        body_text = raw.decode(charset)
    except UnicodeDecodeError:
        body_text = raw.decode(charset, errors='replace')
    
    artifact_id = None
    preview = body_text[:2048]
```

### 5. Auto-parse body

```python
def parse_body(body_text, content_type):
    if not body_text or not content_type:
        return None, "none"
    
    # JSON detection
    if "json" in content_type or (body_text and body_text.strip()[0] in '{['):
        try:
            return json.loads(body_text), "json"
        except json.JSONDecodeError:
            pass  # Fallback to text
    
    # XML/HTML detection
    if "xml" in content_type or "html" in content_type:
        # Don't parse into DOM; return text
        # Selectors (below) will handle extraction
        return body_text, "html"  # or "xml"
    
    # Default
    return body_text, "text"
```

### 6. Apply selectors

```python
def apply_selectors(body_text, body_json, content_type, selectors):
    results = {}
    
    # JSON Pointer (RFC 6901)
    if selectors.get("json_pointer") and body_json:
        try:
            result = get_json_pointer(body_json, selectors["json_pointer"])
            results["json_pointer"] = result
        except Exception as e:
            results["json_pointer_error"] = str(e)
    
    # jq filter
    if selectors.get("jq"):
        if not shutil.which("jq"):
            results["jq_error"] = "jq not installed"
        else:
            try:
                # Write body to temp file
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                    if body_json:
                        json.dump(body_json, f)
                    else:
                        f.write(body_text or "")
                    temp_file = f.name
                
                # Run jq
                output = run_command(["jq", "-c", selectors["jq"], temp_file])
                results["jq"] = json.loads(output)  # If valid JSON
            except Exception as e:
                results["jq_error"] = str(e)
    
    # XPath (HTML/XML)
    if selectors.get("xpath"):
        if "xml" not in content_type and "html" not in content_type:
            results["xpath_error"] = "Not XML/HTML"
        elif not shutil.which("xmllint"):
            results["xpath_error"] = "xmllint not installed"
        else:
            try:
                output = run_command(["xmllint", "--html", "--xpath", 
                                     selectors["xpath"], body_file])
                results["xpath"] = output
            except Exception as e:
                results["xpath_error"] = str(e)
    
    # CSS selector (HTML)
    if selectors.get("css"):
        if "html" not in content_type:
            results["css_error"] = "Not HTML"
        else:
            # Try htmlq first, then pup
            tool = shutil.which("htmlq") or shutil.which("pup")
            if not tool:
                results["css_error"] = "No CSS selector tool (htmlq/pup)"
            else:
                try:
                    if "htmlq" in tool:
                        output = run_command([tool, "-t", selectors["css"], body_file])
                    else:
                        output = run_command([tool, selectors["css"], "text{}"])
                    results["css"] = output.split('\n')  # List of matches
                except Exception as e:
                    results["css_error"] = str(e)
    
    return results if results else None
```

---

## Error Handling

### Curl Exit Code Mapping

```python
CURL_EXIT_CODES = {
    1: ("curl_error", "Unsupported protocol"),
    3: ("curl_error", "URL malformed"),
    6: ("dns_error", "Couldn't resolve host"),
    7: ("connection_error", "Failed to connect"),
    28: ("timeout", "Operation timeout"),
    35: ("tls_error", "SSL connect error"),
    52: ("transport_error", "Empty response"),
    56: ("transport_error", "Failure in receiving data"),
    47: ("redirects", "Too many redirects"),
}

def handle_curl_error(exit_code, stderr):
    error_type, message = CURL_EXIT_CODES.get(exit_code, ("unknown_error", stderr))
    return {
        "type": error_type,
        "code": exit_code,
        "message": message,
        "retryable": error_type in ("timeout", "connection_error", "transport_error", "dns_error"),
        "details": {"stderr": stderr}
    }
```

### HTTP Errors

```python
def handle_http_error(status):
    if 200 <= status < 300:
        return None  # Success
    elif 300 <= status < 400:
        return {
            "type": "redirect",
            "code": status,
            "retryable": False
        }
    elif 400 <= status < 500:
        return {
            "type": "client_error",
            "code": status,
            "retryable": False
        }
    else:  # 500+
        return {
            "type": "server_error",
            "code": status,
            "retryable": True
        }
```

---

## Security Guards (SSRF Protection)

```python
import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_NETWORKS = [
    ipaddress.ip_network('127.0.0.0/8'),      # Loopback
    ipaddress.ip_network('169.254.0.0/16'),   # Link-local
    ipaddress.ip_network('10.0.0.0/8'),       # Private
    ipaddress.ip_network('172.16.0.0/12'),    # Private
    ipaddress.ip_network('192.168.0.0/16'),   # Private
    ipaddress.ip_network('::1/128'),          # IPv6 loopback
    ipaddress.ip_network('fc00::/7'),         # IPv6 private
    ipaddress.ip_network('100.64.0.0/10'),    # Shared address space
]

BLOCKED_HOSTNAMES = {
    'localhost', 'localdomain', 'local',
    'metadata.google.internal', '169.254.169.254',  # Cloud metadata
    'host.docker.internal',
}

def validate_url(url, block_local_network=True):
    parsed = urlparse(url)
    
    # Protocol check
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")
    
    if not block_local_network:
        return
    
    hostname = parsed.hostname
    
    # Hostname blocklist
    if hostname.lower() in BLOCKED_HOSTNAMES:
        raise ValueError(f"Blocked hostname: {hostname}")
    
    # IP blocklist (only for literal IPs)
    try:
        ip = ipaddress.ip_address(hostname)
        if any(ip in network for network in BLOCKED_NETWORKS):
            raise ValueError(f"Blocked IP: {ip}")
    except ValueError:
        # Not an IP, might be resolvable; skip for now
        # (To be stricter, resolve and check resolved IPs)
        pass
```

---

## Event Integration

Emit events via event_memory:

```python
def emit_request_event(method, url, headers):
    event_log.append("http.request.start", {
        "method": method,
        "url": url,
        "headers": sanitize_headers(headers),
        "request_id": uuid.uuid4().hex[:8]
    })

def emit_response_event(request_id, status, timings, redirects):
    event_log.append("http.response.received", {
        "request_id": request_id,
        "status": status,
        "num_redirects": redirects,
        "time_total_ms": timings["time_total"] * 1000,
        "headers": sanitize_headers(response_headers)
    })

def emit_artifact_event(request_id, artifact_id, size, content_type):
    event_log.append("http.response.artifact.saved", {
        "request_id": request_id,
        "artifact_id": artifact_id,
        "size_bytes": size,
        "content_type": content_type
    })
```

---

## Integration Points

### tools.py

```python
class HttpRequestTool(BaseTool):
    name = "http.request"
    description = "HTTP requests via curl with structured JSON output"
    
    def execute(self, **kwargs):
        args = HttpRequestInput(**kwargs)
        
        # Validate
        validate_url(args.url, block_local_network=args.block_local_network)
        
        # Build curl command
        cmd = build_curl_command(args)
        
        # Execute
        result = run_command(shlex.join(cmd))
        
        # Parse
        status, headers = parse_metadata_and_headers(result)
        
        # Format body
        body_text, artifact_id, size = handle_body(...)
        
        # Parse
        parsed_body, parse_type = parse_body(body_text, headers["content-type"])
        
        # Selectors
        selections = apply_selectors(...) if args.selectors else None
        
        # Build response
        return HttpResponse(...)

# Register
TOOLS["http.request"] = HttpRequestTool()
```

### config.py

Add (optional):
```python
http_request_artifact_threshold: int = 512_000
http_request_timeout: float = 30.0
http_request_block_local_network: bool = True
```

### get_context integration

Add HTTP call summary:
```python
event_summary = summarize_event_log(session_id)
if event_summary:
    context["http_calls"] = {
        "total": count,
        "errors": count,
        "redirects": count,
        "artifacts_created": count
    }
```

---

## Implementation Roadmap

### Day 1: Core
- [x] Input/output schema (Pydantic models)
- [x] curl command builder (method, headers, body, timeouts, redirects)
- [x] SSRF validation (hostname + IP blocklists)
- [x] Execute curl via run_command
- [x] Parse metadata (--write-out JSON)
- [x] Parse headers (split blocks, last response)
- [x] Handle body (read/artifact decision)
- [x] Auto-parse JSON (try json.loads)
- [x] Error mapping (curl exit codes)
- [x] Build structured response
- [x] Event logging (request/response events)

### Day 2: Polish & Selectors
- [ ] JSON Pointer support (RFC 6901)
- [ ] jq selector (detect, run, parse output)
- [ ] HTML/XML selectors (xmllint, htmlq/pup detection)
- [ ] Large response artifacts (integration with event_memory)
- [ ] Comprehensive error handling
- [ ] Tests (2xx, 3xx, 4xx, 5xx, timeouts, large bodies, selectors)
- [ ] Deprecation warning for raw curl in run_command

---

## Testing Strategy

```python
# Test cases:
def test_http_request_200_json():
    # GET JSON endpoint, parse response
    
def test_http_request_redirect():
    # Follow 301 → 200, verify effective_url
    
def test_http_request_post_json_body():
    # POST with JSON body, verify Content-Type header
    
def test_http_request_timeout():
    # Verify timeout maps to correct error type
    
def test_http_request_large_body():
    # Response > threshold, verify artifact storage
    
def test_http_request_json_selector_jq():
    # Apply jq filter to JSON response
    
def test_http_request_ssrf_blocked():
    # Attempt to access 127.0.0.1, verify blocked
    
def test_http_request_missing_tool():
    # jq not installed, verify graceful degradation + warning
```

---

## Future Enhancements

1. **Strict SSRF**: DNS resolution + IP verification for redirects
2. **Streaming**: Large downloads with progress events
3. **Auth strategies**: OAuth2, AWS SigV4, client certs
4. **Response caching**: ETag/If-None-Match, per-session cache
5. **Advanced selectors**: Full JSONPath, XPath via libraries if available
6. **Retry logic**: Exponential backoff for retryable errors
7. **Rate limiting**: Respect Retry-After headers

---

## Estimated Effort

- **Core (Day 1)**: 6-8 hours
  - Schema, command builder, parsing, JSON, error mapping, events
- **Polish (Day 2)**: 4-6 hours
  - Selectors, artifact integration, tests, deprecation warning
- **Total**: 10-14 hours (1.5-2 days)
