# Router Tuning & Debugging Guide

**v2.0 Router** uses a 4-level precedence system with regex patterns, FTS5 intention cache, and conservative fallback. This guide explains how to tune, debug, and extend the router.

---

## Router Classification Levels

### Level 1: SHELL Patterns (Highest Priority)

160+ regex patterns detect direct shell commands:

```python
# Examples in router/rules.py:
r'^ls\b',
r'^grep\b',
r'^docker\b',
r'^git\b',
```

**Characteristics**:
- Matches if query **starts with** a known command
- Returns Route.SHELL immediately
- 0-1ms latency (regex only)
- Executes via `run_command` or `run_interactive`

**Debugging**:

```bash
# Test if query matches SHELL patterns
python -m router.cli "ls -la" --verbose

# Output:
# Query: ls -la
# Route: SHELL (confidence: 0.99)
# Matched Rule: ^ls\b
```

**Tuning**: Add command patterns to `SHELL_COMMAND_PATTERNS`:

```python
# In router/rules.py, find SHELL_COMMAND_PATTERNS and add:
r'^mycommand\b',          # Exact match
r'^my-command\b',         # With dash
r'^my_tool\b',            # With underscore
```

Then test:

```bash
python -m router.cli "mycommand arg1" --verbose
# Should now route to SHELL
```

---

### Level 2: CACHED Route (Intent Cache)

FTS5 full-text search on previous executions:

```python
# Queries intention_cache table with BM25 scoring
# Threshold: 0.85 (configurable)
```

**Characteristics**:
- Only matches if cache entry exists AND similarity score ≥ 0.85
- Skips LLM planning, just reruns previous tool args
- 10-50ms latency (FTS search + scoring)

**Cached Entry Example**:

```json
{
  "user_query_text": "list all Python files",
  "tool_name": "run_command",
  "tool_args": {"command": "find . -name '*.py' -type f"},
  "success": 1,
  "usage_count": 3,
  "last_used_at": "2025-11-12T10:30:00"
}
```

**Debugging**:

```bash
# Check what's in the cache
python -c "
from memory.api import Memory
mem = Memory()
hits = mem.search_intention_cache('list files', limit=5)
for h in hits:
    print(f\"Tool: {h['tool_name']}, Query: {h['user_query_text']}\")
"

# Test if a new query would hit cache
python -m router.cli "show all python files" --verbose
# Output includes cache hit or misses
```

**Tuning**:

#### Adjust Similarity Threshold

```python
# In router/router.py, find:
CACHE_THRESHOLD = 0.85

# Lower for more hits (risk false positives):
CACHE_THRESHOLD = 0.75  # More permissive
# Raise for fewer hits (risk missing valid matches):
CACHE_THRESHOLD = 0.95  # More conservative
```

#### Manually Seed Cache

```python
from memory.api import Memory

mem = Memory()
mem.add_to_intention_cache(
    user_query="list files in directory",
    normalized_intent="enumerate files",
    tool_name="run_command",
    tool_args={"command": "ls -lah"},
    success=True
)

# Now this query will hit cache:
python -m router.cli "list files in directory" --verbose
# Route: CACHED, Score: 0.95
```

#### Monitor Cache Hit Rate

```python
from orchestrator.metrics import get_metrics

metrics = get_metrics()
cache_stats = metrics.get_cache_hit_rate(limit_hours=24)
print(f"Hit rate: {cache_stats['hit_rate_percent']}%")
```

---

### Level 3: CHAT Patterns

12 regex patterns for informational questions:

```python
# In router/rules.py, CHAT_QUERY_PATTERNS:
r'^what\s+(is|are|was|were)\b',
r'^how\s+(is|are|was|were|do|does|did)\b',
r'^explain\b',
r'^define\b',
```

**Characteristics**:
- Matches informational/educational queries
- Routes to Agent C (chat mode) **without** tool execution
- 0-1ms latency (regex only)
- No side effects

**Debugging**:

```bash
python -m router.cli "What is Docker?" --verbose
# Route: CHAT (confidence: 0.90)
# Matched Rule: ^what\s+(is|are|was|were)\b
```

**Tuning**: Add question patterns to `CHAT_QUERY_PATTERNS`:

```python
# For new question types:
r'^is\s+.*\s+a\b',       # "Is X a Y?"
r'^can\s+.*\b',          # "Can you..."
r'^should\s+.*\b',       # "Should I..."
```

Test:

```bash
python -m router.cli "Can you explain Docker?" --verbose
# Should route to CHAT if pattern matches
```

---

### Level 4: PLANNER (Fallback)

**Characteristics**:
- Catches everything else
- Conservative default (confidence 0.5-0.6)
- Routes to Agent A→B→C loop for complex decomposition
- 200-2000ms latency (includes LLM calls)

**When queries reach PLANNER**:

```bash
# Query that doesn't match SHELL/CACHED/CHAT patterns:
python -m router.cli "Build a monitoring dashboard for my server" --verbose

# Route: PLANNER (confidence: 0.60)
# Matched Rule: (none - fallback)
```

---

## Interactive Command Detection

Special handling for TTY-requiring commands (vim, nano, top):

```python
# In router/rules.py, INTERACTIVE_COMMAND_PATTERNS:
r'^vim\b(?!\s+-c)',        # vim (but NOT vim -c)
r'^nano\b',                 # nano always interactive
r'^top\b',                  # top always interactive
```

**Characteristics**:
- Matches SHELL patterns first
- Then checks `is_interactive_command()`
- If interactive → routes to `run_interactive` (TTY forwarding)
- Otherwise → routes to `run_command` (non-TTY)

**Debugging**:

```bash
# Interactive command
python -m router.cli "vim main.py" --verbose
# is_interactive: True → uses run_interactive

# Batch mode (not interactive)
python -m router.cli "vim -c 'set number' file.py" --verbose
# is_interactive: False → uses run_command

# Regular command
python -m router.cli "ls -la" --verbose
# is_interactive: False → uses run_command
```

**Tuning**: Add interactive patterns:

```python
# For new interactive tools:
r'^less\b',              # less pager
r'^more\b',              # more pager
r'^python\b',            # Python REPL
r'^psql\b',              # PostgreSQL interactive
```

---

## Debugging Tools

### 1. Router CLI (Manual Classification)

```bash
# Single query
python -m router.cli "ls -la"

# Batch test (test_queries.txt contains one query per line)
python -m router.cli --test-file test_queries.txt

# Interactive REPL
python -m router.cli --interactive

# JSON output
python -m router.cli "what is python?" --json

# Verbose analysis
python -m router.cli "create a script" --verbose --show-patterns
```

### 2. Programmatic Testing

```python
from router.router import Router
from memory.api import Memory

router = Router(memory=Memory())

# Classify a query
result = router.classify("ls -la")
print(f"Route: {result.route}")
print(f"Confidence: {result.confidence}")
print(f"Matched rule: {result.matched_rule}")

# Check cache
cache_hits = router.intention_cache.lookup("list files")
if cache_hits:
    print(f"Cache hit: {cache_hits}")
```

### 3. Database Inspection

```python
from memory.api import Memory

mem = Memory()

# View recent router decisions
decisions = mem.conn.execute("""
    SELECT route, confidence, query_text, created_at
    FROM router_decisions
    WHERE created_at > datetime('now', '-1 hour')
    ORDER BY created_at DESC
    LIMIT 20
""").fetchall()

for route, conf, query, ts in decisions:
    print(f"{ts} | {route:8} ({conf:.2f}) | {query[:50]}")

# View intention cache
cache = mem.conn.execute("""
    SELECT user_query_text, tool_name, usage_count
    FROM intention_cache
    ORDER BY usage_count DESC
    LIMIT 10
""").fetchall()

for query, tool, count in cache:
    print(f"{count:2} uses | {tool:15} | {query}")
```

### 4. Metrics Dashboard

```python
from orchestrator.metrics import get_metrics
import json

metrics = get_metrics()
report = metrics.get_summary_report(limit_hours=24)

print(json.dumps(report, indent=2))

# Output:
# {
#   "route_distribution": {
#     "SHELL": 45,
#     "CHAT": 28,
#     "CACHED": 12,
#     "PLANNER": 5
#   },
#   "cache_hit_rate": {
#     "hits": 12,
#     "total": 100,
#     "hit_rate_percent": 12.0
#   },
#   "latency_stats": {
#     "all": {"avg_ms": 250, "p95_ms": 450, ...},
#     "shell": {...},
#     ...
#   }
# }
```

---

## Common Issues & Solutions

### Issue: Query routes to PLANNER when it should be SHELL

**Symptom**:
```bash
python -m router.cli "mycommand arg1"
# Route: PLANNER (confidence: 0.60)
# Expected: SHELL
```

**Solution**:
1. Check if `mycommand` is in `SHELL_COMMAND_PATTERNS`
2. If not, add it: `r'^mycommand\b'`
3. Test again

```bash
python -m router.cli "mycommand arg1" --verbose
# Route: SHELL (confidence: 0.99)
```

### Issue: Cache never gets hits

**Symptom**:
```bash
python -m router.cli "list files"
# Route: PLANNER (no cache hit)
# Then execute and cache the result
python -m router.cli "list files"
# Route: PLANNER (still no cache hit)
```

**Solution**:
1. Check cache is populated: 
```python
from memory.api import Memory
mem = Memory()
hits = mem.search_intention_cache("list files")
print(len(hits))  # Should be > 0
```

2. Lower cache threshold temporarily to see if it's a scoring issue:
```python
# In router/router.py:
CACHE_THRESHOLD = 0.70  # More permissive
```

3. If threshold adjustment helps, gradually raise it back up while monitoring hit rate

### Issue: Too many false-positive cache hits

**Symptom**:
```bash
# Execute one query
python -m router.cli "find all txt files"
# Execute different query but gets cached result
python -m router.cli "find all pdf files"
# Route: CACHED (wrong! Should be PLANNER or CHAT)
```

**Solution**:
1. Raise cache threshold:
```python
# In router/router.py:
CACHE_THRESHOLD = 0.95  # More conservative
```

2. Verify cache entries are correctly seeded (should be exact matches of real patterns users type)

3. Manually remove bad cache entries:
```python
from memory.api import Memory
mem = Memory()
mem.conn.execute("DELETE FROM intention_cache WHERE user_query_text LIKE '%pattern%'")
mem.conn.commit()
```

### Issue: Interactive commands not launching TTY

**Symptom**:
```bash
python main.py
> vim main.py
# Doesn't open vim, just runs as non-interactive
```

**Solution**:
1. Check if command is in `INTERACTIVE_COMMAND_PATTERNS`:
```bash
python -m router.cli "vim main.py" --verbose
# is_interactive: should be True
```

2. If False, add to patterns:
```python
# In router/rules.py, INTERACTIVE_COMMAND_PATTERNS:
r'^vim\b(?!\s+-c)',  # vim (except vim -c)
```

3. Check if `run_interactive` tool is available:
```python
from tools import TOOLS
assert "run_interactive" in TOOLS
```

4. If still not working, check shell wrapper is properly initialized (see shell_integration.py)

---

## Best Practices

### 1. Keep SHELL Patterns Specific

Bad:
```python
r'^my.*command\b',  # Too broad, might match other tools
```

Good:
```python
r'^mycommand\b',    # Exact match
```

### 2. Seed Cache With Real Patterns

Only cache **actual user patterns**, not hypothetical ones:

```python
# Good: Based on observed queries
mem.add_to_intention_cache(
    user_query="show command history",
    normalized_intent="display history",
    tool_name="run_command",
    tool_args={"command": "history"}
)

# Bad: Hypothetical pattern that users won't type
mem.add_to_intention_cache(
    user_query="enumerate past bash invocations with optional filtering",
    ...
)
```

### 3. Monitor Metrics Weekly

```bash
# Cron job or manual check:
python -c "
from orchestrator.metrics import get_metrics
m = get_metrics()
report = m.get_summary_report(limit_hours=168)  # Last week
print('Route distribution:', report['route_distribution'])
print('Cache hit rate:', report['cache_hit_rate']['hit_rate_percent'], '%')
"
```

### 4. A/B Test Threshold Changes

When adjusting thresholds, measure impact:

```python
# Before change
metrics_before = get_metrics().get_cache_hit_rate()  # 5%

# Change threshold
# CACHE_THRESHOLD = 0.75  (from 0.85)

# After change
metrics_after = get_metrics().get_cache_hit_rate()   # 15%

# Accept if hit rate improves and no false positives observed
```

---

## Adding Custom Route Logic

For advanced cases, extend the Router:

```python
# In router/router.py, extend classify():

def classify(self, query: str) -> RouterResult:
    # Level 1: SHELL
    if self.rule_engine.is_shell_command(query):
        return RouterResult(route=Route.SHELL, confidence=0.99, ...)
    
    # Level 2: CACHED
    cache_hit = self.intention_cache.lookup(query)
    if cache_hit and cache_hit.score > CACHE_THRESHOLD:
        return RouterResult(route=Route.CACHED, confidence=cache_hit.score, ...)
    
    # Level 3: CHAT
    if self.rule_engine.is_chat_query(query):
        return RouterResult(route=Route.CHAT, confidence=0.90, ...)
    
    # Level 4: CUSTOM (your logic here)
    if self._custom_detector(query):
        return RouterResult(route=Route.CUSTOM, confidence=0.70, ...)
    
    # Level 5: PLANNER (fallback)
    return RouterResult(route=Route.PLANNER, confidence=0.60, ...)

def _custom_detector(self, query: str) -> bool:
    # Your custom heuristic
    return "special keyword" in query.lower()
```

---

## Performance Tuning

### Optimize Regex Compilation

Patterns are compiled once at module load (already done):

```python
# In router/rules.py:
_SHELL_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in SHELL_COMMAND_PATTERNS]
```

### Cache Database Indexing

FTS5 is automatically indexed. For cache queries to stay <50ms:

```python
# Check index exists:
from memory.api import Memory
mem = Memory()
indexes = mem.conn.execute("""
    SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='intention_cache'
""").fetchall()
print(f"Indexes on intention_cache: {indexes}")
```

### Monitor Query Latency

```python
from orchestrator.metrics import get_metrics

metrics = get_metrics()
stats = metrics.get_latency_stats("CACHED", limit_hours=24)
print(f"CACHED route avg: {stats['avg_ms']}ms")
print(f"CACHED route p95: {stats['p95_ms']}ms")
```

---

## Validation Checklist

Before deploying router changes:

- [ ] Added new patterns to appropriate list (SHELL/CHAT/INTERACTIVE)
- [ ] Tested with `python -m router.cli`
- [ ] Verified no regressions: `pytest tests/test_router_cli.py -v`
- [ ] Ran metrics report: no unexplained routing changes
- [ ] Documented the change in this guide (if adding new patterns)
- [ ] Committed `.beads/issues.jsonl` along with code changes

---

**For issues or questions, create a bd task: `bd create "Router: ..." -t task -p 2`**
