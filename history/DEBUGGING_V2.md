# v2.0 Debugging Guide

Comprehensive debugging strategies for the v2.0 Multi-Role Orchestrator.

---

## Architecture Debugging

### Trace a Query Through the System

```bash
# Terminal A: Start logging
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from orchestrator.orchestrator import Orchestrator
from config import load_config
config = load_config()
o = Orchestrator(config=config)
# Keep process running
import time; time.sleep(3600)
" > orchestrator.log 2>&1 &

# Terminal B: Run a query through main.py
python main.py
> ls -la
# Ctrl-C after seeing result

# Terminal A: Examine logs
tail -100 orchestrator.log
```

### Inspect Router Decision

```python
from orchestrator.orchestrator import Orchestrator
from config import load_config

config = load_config()
o = Orchestrator(config=config)

# Trace a specific query
result = o.handle_query("ls -la")
print(f"Route: {result.route}")
print(f"Cycle ID: {result.cycle_id}")
print(f"Latency: {result.latency_ms}ms")
print(f"Error: {result.error}")

# Check what was stored
from memory.api import Memory
mem = Memory()
decision = mem.get_router_decision(result.cycle_id)
print(f"Stored decision: {decision}")
```

---

## Router Debugging

### Step-by-Step Classification

```python
from router.router import Router
from memory.api import Memory

router = Router(memory=Memory())
query = "Create a monitoring script"

# Get detailed result
result = router.classify(query)

# Inspect each attribute
print(f"Query: {result.query}")
print(f"Route: {result.route} (Route.{result.route.name})")
print(f"Confidence: {result.confidence}")
print(f"Matched rule: {result.matched_rule}")

# Check if it's a cached hit
if hasattr(result, 'cache_hit') and result.cache_hit:
    print(f"Cache hit: {result.cache_hit}")
```

### Check Rule Matching

```python
from router.rules import RuleEngine

engine = RuleEngine()

# Check SHELL patterns
query = "ls -la"
for pattern in engine.shell_patterns:
    if pattern.match(query):
        print(f"SHELL: Matched {pattern.pattern}")

# Check CHAT patterns
query = "What is Docker?"
for pattern in engine.chat_patterns:
    if pattern.search(query):
        print(f"CHAT: Matched {pattern.pattern}")

# Check interactive patterns
query = "vim main.py"
is_interactive = engine.is_interactive_command(query)
print(f"Interactive: {is_interactive}")
```

### Analyze Cache Performance

```python
from router.intention_cache import IntentionCache
from memory.api import Memory

cache = IntentionCache(memory=Memory())

# Search for a query
query = "list files"
hits = cache.search(query, limit=5)

print(f"Found {len(hits)} cache hits for '{query}'")
for i, hit in enumerate(hits):
    print(f"  {i+1}. {hit['user_query_text']}")
    print(f"     Tool: {hit['tool_name']}")
    print(f"     Score: {hit['score']:.3f}")
    print(f"     Usage count: {hit['usage_count']}")
```

---

## Memory Debugging

### Database Inspection

```python
from memory.api import Memory
import sqlite3

mem = Memory()

# List all tables
tables = mem.conn.execute("""
    SELECT name FROM sqlite_master WHERE type='table'
    ORDER BY name
""").fetchall()

print("Tables in orchestrator.db:")
for table, in tables:
    count = mem.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table}: {count} rows")

# Get database size
import os
db_path = "logs/orchestrator.db"
size_kb = os.path.getsize(db_path) / 1024
print(f"\nDatabase size: {size_kb:.1f} KB")
```

### Check Session State

```python
from memory.api import Memory

mem = Memory()

# Get all sessions
sessions = mem.conn.execute("""
    SELECT session_id, created_at, model, last_activity_at
    FROM sessions
    ORDER BY created_at DESC
    LIMIT 5
""").fetchall()

for session_id, created, model, last_activity in sessions:
    print(f"Session: {session_id}")
    print(f"  Created: {created}")
    print(f"  Model: {model}")
    print(f"  Last activity: {last_activity}")
    
    # Count cycles in session
    cycle_count = mem.conn.execute(
        "SELECT COUNT(*) FROM router_decisions WHERE session_id = ?",
        (session_id,)
    ).fetchone()[0]
    print(f"  Cycles: {cycle_count}")
```

### View Router Decisions

```python
from memory.api import Memory

mem = Memory()

# Recent decisions
decisions = mem.conn.execute("""
    SELECT cycle_id, route, confidence, query_text, created_at
    FROM router_decisions
    WHERE created_at > datetime('now', '-1 hour')
    ORDER BY created_at DESC
    LIMIT 10
""").fetchall()

print("Recent routing decisions:")
for cycle_id, route, conf, query, ts in decisions:
    print(f"{ts} | {route:8} ({conf:.2f}) | {query[:40]}...")
```

### Inspect Step Execution (PLANNER)

```python
from memory.api import Memory

mem = Memory()

# Find a PLANNER cycle
planner_cycles = mem.conn.execute("""
    SELECT cycle_id FROM router_decisions WHERE route = 'PLANNER'
    ORDER BY created_at DESC LIMIT 1
""").fetchall()

if planner_cycles:
    cycle_id = planner_cycles[0][0]
    
    # Get the plan
    task = mem.get_task_state(cycle_id)
    print(f"Plan status: {task['status']}")
    print(f"Current step: {task['current_step_id']}")
    
    # Get all step outputs
    steps = mem.get_step_outputs(cycle_id)
    for step in steps:
        print(f"\nStep {step['step_id']}: {step['tool_name']}")
        print(f"  Success: {step['success']}")
        print(f"  Output: {step['output_preview'][:100]}...")
```

---

## LLM Debugging

### View LLM Traces

```python
from memory.api import Memory
import json

mem = Memory()

# Get recent LLM calls
traces = mem.get_llm_traces(limit=5)

for trace in traces:
    print(f"\n=== LLM Trace {trace['id']} ===")
    print(f"Role: {trace['role']}")
    print(f"Cycle: {trace['cycle_id']}")
    print(f"Tokens: {trace.get('prompt_tokens', '?')} prompt, {trace.get('completion_tokens', '?')} completion")
    
    # Show prompt preview
    prompt = trace['full_prompt']
    print(f"\nPrompt (first 300 chars):")
    print(prompt[:300])
    
    # Show response preview
    response = trace['full_response']
    print(f"\nResponse (first 300 chars):")
    print(response[:300])
```

### Check LLM Client Behavior

```python
from llm_client import LLMClient
from config import load_config

config = load_config()
client = LLMClient(config=config, role="C")  # Agent C

# Make a test call
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is Docker?"}
]

result = client.call(messages=messages, cycle_id="test-cycle")

print(f"Success: {not result['error']}")
print(f"Message: {result['message'].content if result['message'] else 'None'}")
print(f"Latency: {result['latency_ms']}ms")
if result['error']:
    print(f"Error: {result['error']}")
```

### Validate Plan JSON

```python
from orchestrator.plan_validator import PlanValidator, PlanValidationError
import json

validator = PlanValidator()

# Test a plan
plan_json = """{
  "steps": [
    {
      "id": 0,
      "tool_name": "create_file",
      "intent": "Create a monitoring script",
      "description": "Write Python script for disk monitoring"
    },
    {
      "id": 1,
      "tool_name": "run_command",
      "intent": "Make script executable",
      "description": "Set executable permission"
    }
  ]
}"""

try:
    plan = validator.validate(plan_json)
    print(f"✓ Plan valid with {len(plan['steps'])} steps")
except PlanValidationError as e:
    print(f"✗ Plan invalid: {e}")
```

---

## Metrics Debugging

### View Route Distribution

```python
from orchestrator.metrics import get_metrics

metrics = get_metrics()

# Route distribution over time windows
for hours in [1, 24, 168]:  # Last 1h, 1d, 1w
    dist = metrics.get_route_distribution(limit_hours=hours)
    total = sum(dist.values())
    print(f"\nLast {hours}h ({total} queries):")
    for route, count in sorted(dist.items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total > 0 else 0
        print(f"  {route:8} {count:4} ({pct:5.1f}%)")
```

### Check Latency Percentiles

```python
from orchestrator.metrics import get_metrics

metrics = get_metrics()

# Overall latency
stats = metrics.get_latency_stats(limit_hours=24)
print(f"Overall latency (last 24h):")
print(f"  Avg: {stats['avg_ms']}ms")
print(f"  P50: {stats['p50_ms']}ms")
print(f"  P95: {stats['p95_ms']}ms")

# Per-route latency
for route in ['SHELL', 'CACHED', 'CHAT', 'PLANNER']:
    stats = metrics.get_latency_stats(route=route, limit_hours=24)
    if stats.get('count', 0) > 0:
        print(f"\n{route} latency:")
        print(f"  Avg: {stats['avg_ms']}ms")
        print(f"  P95: {stats['p95_ms']}ms")
```

### Analyze Tool Performance

```python
from orchestrator.metrics import get_metrics

metrics = get_metrics()
planner_stats = metrics.get_planner_stats(limit_hours=24)

print("PLANNER step success rates:")
for tool, stats in planner_stats.items():
    print(f"\n{tool}:")
    print(f"  Calls: {stats['total_calls']}")
    print(f"  Success: {stats['successful']}/{stats['total_calls']} ({stats['success_rate_percent']}%)")
    print(f"  Avg latency: {stats['avg_latency_ms']}ms")
```

---

## End-to-End Test Scenarios

### Scenario 1: Simple CHAT Query

```python
from orchestrator.orchestrator import Orchestrator
from config import load_config

config = load_config()
o = Orchestrator(config=config)

result = o.handle_query("What is Kubernetes?")

assert result.route == "CHAT", f"Expected CHAT, got {result.route}"
assert result.agent_response is not None, "No response from Agent C"
assert result.error is None, f"Unexpected error: {result.error}"
assert result.latency_ms < 1000, f"Too slow: {result.latency_ms}ms"

print("✓ CHAT query works end-to-end")
```

### Scenario 2: SHELL Command Execution

```python
from orchestrator.orchestrator import Orchestrator
from config import load_config

config = load_config()
o = Orchestrator(config=config)

result = o.handle_query("ls -la /tmp")

assert result.route == "SHELL", f"Expected SHELL, got {result.route}"
assert result.agent_response is not None, "No response from Agent C"
assert result.latency_ms < 500, f"Too slow for simple command: {result.latency_ms}ms"

print("✓ SHELL command works end-to-end")
```

### Scenario 3: CACHED Route Hit

```python
from orchestrator.orchestrator import Orchestrator
from memory.api import Memory
from config import load_config

# Seed cache
mem = Memory()
mem.add_to_intention_cache(
    user_query="show last 10 commands",
    normalized_intent="display command history",
    tool_name="run_command",
    tool_args={"command": "history | tail -10"},
    success=True
)

# Execute
config = load_config()
o = Orchestrator(config=config)
result = o.handle_query("show command history")

# Check if it was cached
from memory.api import Memory
mem = Memory()
decision = mem.get_router_decision(result.cycle_id)
# Note: May be CACHED or PLANNER depending on threshold

print(f"Route: {result.route}")
print(f"Response: {result.agent_response[:100]}...")
```

---

## Common Bugs & Fixes

### Bug: "orchestrator.db not found"

**Symptom**:
```
FileNotFoundError: [Errno 2] No such file or directory: 'logs/orchestrator.db'
```

**Fix**:
```python
from memory.api import Memory
mem = Memory()  # Creates db and tables automatically
```

### Bug: "No module named 'orchestrator'"

**Symptom**:
```
ModuleNotFoundError: No module named 'orchestrator'
```

**Fix**:
```bash
# Ensure you're in the repo root
pwd
# Should output: /path/to/ai-terminal

# Run from repo root
python -c "from orchestrator.orchestrator import Orchestrator"
```

### Bug: "LLM call failed: API key invalid"

**Symptom**:
```
RuntimeError: LLM call failed: Incorrect API key provided
```

**Fix**:
```bash
# Check .env file exists
cat .env | grep OPENAI_API_KEY

# Or set environment variable
export OPENAI_API_KEY=sk-...

# Or override in code
from config import Config
config = Config(api_key="sk-...")
```

### Bug: "Plan JSON parsing failed"

**Symptom**:
```
json.JSONDecodeError: Expecting value: line 1 column 1
```

**Fix**:
```python
# Check what Agent A returned
from memory.api import Memory
mem = Memory()
traces = mem.get_llm_traces(role="A", limit=1)
if traces:
    print("Agent A response:")
    print(traces[0]['full_response'])
    # Usually Agent A forgot to return JSON
    # Increase temperature or improve prompt
```

---

## Performance Profiling

### Profile Route Classification Speed

```python
import time
from router.router import Router
from memory.api import Memory

router = Router(memory=Memory())

# Warm up
router.classify("test")

# Benchmark
queries = ["ls -la", "What is Python?", "create a script", "docker ps"]
times = []

for q in queries * 100:  # 400 iterations
    start = time.time()
    router.classify(q)
    times.append(time.time() - start)

import statistics
print(f"Router classification speed:")
print(f"  Mean: {statistics.mean(times)*1000:.2f}ms")
print(f"  Median: {statistics.median(times)*1000:.2f}ms")
print(f"  P95: {sorted(times)[int(len(times)*0.95)]*1000:.2f}ms")
```

### Profile Orchestrator End-to-End

```python
import time
from orchestrator.orchestrator import Orchestrator
from config import load_config

config = load_config()
o = Orchestrator(config=config)

# Benchmark CHAT query
start = time.time()
result = o.handle_query("What is Docker?")
elapsed = time.time() - start

print(f"Orchestrator latency: {elapsed*1000:.0f}ms")
print(f"  Reported latency: {result.latency_ms}ms")
```

---

## Advanced: Database Forensics

### Check Transaction History

```python
from memory.api import Memory

mem = Memory()

# Get all transaction timestamps
events = mem.conn.execute("""
    SELECT 'router_decision' as table_name, COUNT(*) as count, MAX(created_at) as latest
    FROM router_decisions
    UNION ALL
    SELECT 'step_output', COUNT(*), MAX(created_at)
    FROM step_outputs
    UNION ALL
    SELECT 'chat_history', COUNT(*), MAX(created_at)
    FROM chat_history
    ORDER BY latest DESC
""").fetchall()

print("Database write activity:")
for table, count, latest in events:
    print(f"  {table:15} {count:6} records, latest: {latest}")
```

### Find Slow Queries

```python
from memory.api import Memory
import time

mem = Memory()

# Profile cache search
start = time.time()
hits = mem.search_intention_cache("list files", limit=10)
cache_time = time.time() - start

print(f"Cache search time: {cache_time*1000:.2f}ms")

# Profile router_decisions query
start = time.time()
decisions = mem.get_router_decision("some-cycle-id")
db_time = time.time() - start

print(f"Router decision fetch time: {db_time*1000:.2f}ms")
```

---

## Support

For debugging issues:

1. **Gather logs**: `cat logs/orchestrator.db` (run `sqlite3 logs/orchestrator.db` for interactive access)
2. **Check metrics**: `python -c "from orchestrator.metrics import get_metrics; import json; print(json.dumps(get_metrics().get_summary_report(), indent=2))"`
3. **Create issue**: `bd create "Debug: ..." -t task -p 1 --json`
4. **Provide traces**: Paste relevant LLM traces from `Memory.get_llm_traces()`

