# Phase 6 Revised Plan — In AI We Trust

**Status**: Re-scoped for trusted-user environment  
**Date**: November 12, 2025  
**Philosophy**: In AI We Trust, first-class users only  

---

## Philosophy Correction

Original review (check1.md) was written for **public/untrusted-user systems**. This project:
- ✅ Internal only (trusted developers)
- ✅ No public API or user-facing deployment
- ✅ "In AI We Trust" architecture (minimal guardrails, full access)
- ✅ First-class users (no adversarial input)

**Implication**: Security hardening (command injection, prompt injection) becomes **Phase 7+ (nice-to-have)**, not blockers.

---

## Reclassified Issues

### Production Blockers (MUST FIX - Phase 6)

#### 1. 🔴 Race Condition in Memory Auto-Sync (ai-terminal-fdpc)
**Why critical**: Data corruption affects session state  
**Effort**: 1.5 hours  
**Fix**: Add threading lock to export_to_jsonl()

#### 2. 🔴 Unbounded Chat History Growth (ai-terminal-jcw7)
**Why critical**: Context window overflows on long sessions  
**Effort**: 1.5 hours  
**Fix**: Token budget enforcement in get_chat_history()

#### 3. 🔴 Missing LLM API Retry Logic (ai-terminal-l1pv)
**Why critical**: Transient errors (network, rate limits) cause user-visible failures  
**Effort**: 1 hour  
**Fix**: Exponential backoff retry (3x)

#### 4. 🟠 Missing Input Validation (ai-terminal-rcp0)
**Why important**: Malformed JSON from Agent B crashes orchestrator  
**Effort**: 1 hour  
**Fix**: jsonschema validation before tool.execute()

---

### Security Hardening (DEFER - Phase 7+)

#### ⏭️ Command Injection (ai-terminal-2n4q)
**Why deferred**: Trusted users won't inject commands  
**When needed**: When opening to untrusted users  
**Phase**: 7 (Security hardening)

#### ⏭️ Prompt Injection (ai-terminal-vo4g)
**Why deferred**: Trusted developers won't attack prompts  
**When needed**: When deploying to public/shared systems  
**Phase**: 7 (Security hardening)

---

### Nice-to-Have (Phase 6 or Later)

#### Circuit Breaker (ai-terminal-rlpo)
**Why deferrable**: v2.0 for internal testing, not production SLA  
**When needed**: Production deployment with uptime SLA  
**Phase**: 7+ (Operations)

#### Hard-Coded Thresholds (ai-terminal-481m)
**Why deferrable**: Defaults work for MVP, A/B testing not needed yet  
**When needed**: Operational tuning based on metrics  
**Phase**: 7+ (Operations)

---

## Phase 6 Revised Scope

### Week 1: Production Reliability Fixes

**Day 1 (4 hours)**:
- 1.5h: Race condition fix (threading lock in memory export)
- 1.5h: Chat history token budget
- 1h: LLM API retry logic

**Day 2-3 (5 hours)**:
- 1h: Input validation (jsonschema)
- 4h: Full integration testing

**Result**: 4 critical issues fixed, 65 tests passing, ready for internal testing.

### Week 2: Polish & Documentation

**Day 1-2 (4 hours)**:
- Update README with Phase 6 completion
- Test suite status: 65/65 passing
- Create deployment guide (internal)

**Result**: Documented, tested, ready for next iteration or public beta.

---

## Implementation Details

### Fix 1: Race Condition (1.5h)

**File**: `memory/api.py`

```python
import threading

class Memory:
    def __init__(self):
        self._export_lock = threading.RLock()
        # ...
    
    def export_to_jsonl(self):
        """Thread-safe atomic export"""
        with self._export_lock:
            # Write to temp file first
            import tempfile, shutil
            with tempfile.NamedTemporaryFile(
                mode='w', dir='.beads', suffix='.jsonl.tmp', delete=False
            ) as tmp:
                for issue in self.issues:
                    json.dump(issue, tmp)
                    tmp.write('\n')
                tmp_path = tmp.name
            
            # Atomic move
            shutil.move(tmp_path, '.beads/issues.jsonl')
```

**Test**:
```bash
pytest tests/test_memory_thread_safety.py -v
```

---

### Fix 2: Chat History Token Budget (1.5h)

**File**: `memory/api.py`

```python
def get_chat_history(self, session_id: str, token_budget: int = 2000):
    """Get chat history up to token budget (not message count)"""
    rows = db.execute("""
        SELECT * FROM chat_history 
        WHERE session_id = ? 
        ORDER BY created_at DESC
    """, (session_id,))
    
    messages = []
    total_tokens = 0
    
    for row in rows:
        user_tokens = len(row['user_query']) // 4  # Rough estimate
        response_tokens = len(row['agent_response']) // 4
        
        if total_tokens + user_tokens + response_tokens > token_budget:
            break
        
        messages.insert(0, row)
        total_tokens += user_tokens + response_tokens
    
    return messages
```

**Test**:
```bash
# Simulate 100 interactions
python -c "
from memory.api import Memory
mem = Memory()
session_id = mem.create_session('test', 'gpt-4')

for i in range(100):
    mem.log_chat_history(session_id, f'Q{i}', f'R{i}' * 100)

history = mem.get_chat_history(session_id, token_budget=2000)
total_tokens = sum(len(msg['user_query']) // 4 for msg in history)
assert total_tokens < 2100, f'Budget exceeded: {total_tokens} tokens'
print(f'✓ Chat history within budget: {len(history)} msgs, {total_tokens} tokens')
"
```

---

### Fix 3: LLM API Retry (1h)

**File**: `llm_client.py`

```python
import time

def call(self, messages, ..., max_retries=3):
    """Call LLM with exponential backoff"""
    for attempt in range(max_retries):
        try:
            response = self.client.chat.completions.create(...)
            return {"message": response, "error": None}
        except Exception as e:
            is_last = (attempt == max_retries - 1)
            is_retryable = self._is_retryable(e)
            
            if is_retryable and not is_last:
                delay = 2 ** attempt  # 1s, 2s, 4s
                logger.info(f"Retry after {delay}s ({attempt+1}/{max_retries})")
                time.sleep(delay)
                continue
            
            return {"message": None, "error": str(e)}

def _is_retryable(self, e: Exception) -> bool:
    err_str = str(e).lower()
    retryable = ['timeout', 'rate_limit', '429', 'connection', '503']
    non_retryable = ['api key', '401', '403', 'authentication']
    
    if any(p in err_str for p in retryable):
        return True
    if any(p in err_str for p in non_retryable):
        return False
    
    return False  # Unknown: don't retry
```

**Test**:
```bash
# Test retry on transient error
pytest tests/test_llm_retry.py::test_retries_on_rate_limit -v
```

---

### Fix 4: Input Validation (1h)

**File**: `tool_executor.py`

```python
import jsonschema

def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]):
    """Execute with schema validation"""
    tool = TOOLS[tool_name]
    schema = tool.schema['function']['parameters']
    
    try:
        jsonschema.validate(tool_args, schema)
    except jsonschema.ValidationError as e:
        return {
            "success": False,
            "error": f"Invalid args: {e.message}",
            "result": None
        }
    
    try:
        result = tool.execute(**tool_args)
        return {"success": True, "error": None, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e), "result": None}
```

**Test**:
```bash
pytest tests/test_tool_validation.py -v
```

---

## Testing Plan

### Unit Tests (2h)
```bash
# Memory thread safety
pytest tests/test_memory_thread_safety.py -v

# Chat history token budget
pytest tests/test_chat_history_budget.py -v

# LLM retry logic
pytest tests/test_llm_retry.py -v

# Tool validation
pytest tests/test_tool_validation.py -v
```

### Integration Tests (1h)
```bash
# Full orchestrator with all fixes
pytest tests/test_e2e_chat_cached.py -v
pytest tests/test_e2e_planner.py -v
pytest tests/test_cross_route_integration.py -v

# Ensure 65/65 still passing
pytest tests/ -v
```

### Manual Testing (1h)
```bash
# Long conversation (test chat history budget)
python main.py
> query 1
> query 2
> ... (50+ queries)
# Should not exceed context window

# Network hiccup simulation (test retry)
# Kill API and restart after 2s
# Agent should retry and succeed
```

---

## Success Criteria

✅ **Phase 6 Complete when**:
1. Race condition fixed (thread lock)
2. Chat history bounded (token budget)
3. API retry working (3x exponential backoff)
4. Input validation enforced (jsonschema)
5. All 65 tests passing
6. No regressions
7. Documentation updated

---

## Deliverables

- [ ] 4 bug fixes implemented
- [ ] 65/65 tests passing
- [ ] PHASE_6_COMPLETION.md (sign-off)
- [ ] README updated with Phase 6 status
- [ ] Ready for internal beta testing

---

## Timeline

**Week 1**: All fixes complete, tested, integrated  
**Week 2**: Polish, docs, final sign-off  

**Total effort**: ~8 hours implementation + testing  
**Risk**: LOW (no architectural changes, just defensive coding)  

---

## Phase 7+ (Deferred Security)

When ready to move beyond internal testing:
- Command injection hardening (shell=False, shlex, allowlist)
- Prompt injection mitigation (XML tags, input sanitization)
- Rate limiting per user
- Structured logging
- Monitoring/alerting
- Distributed tracing

---

**Status**: REVISED FOR TRUSTED-USER ENVIRONMENT  
**Blocker Reduction**: 8 issues → 4 critical fixes → Phase 6 complete
