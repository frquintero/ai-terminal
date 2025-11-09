# Event-Driven Memory Upgrade

## **🔴 The Problem**

**Your agent is forgetful and wasteful:**

- Sends last 40 messages to LLM every turn (10,000+ tokens)
- When history exceeds 40 messages, **blindly deletes old messages**
- Loses important context: previous errors, file writes, tool outputs
- Can't remember what happened 50 turns ago
- Wastes tokens repeating the same outputs in every prompt

**Example**: If you ran 60 commands in a session, the agent forgot the first 20. If command #55 failed, it can't see what worked in command #10.

---

## **🟢 The Solution**

**Event-driven memory system (like Letta/MemGPT):**

Instead of:
```
User message → Add to message_history → Trim to 40 → Send all to LLM
```

Do this:
```
User message → Log to event stream → Retrieve relevant events → Build smart prompt → LLM
                                      ↓
                               [Events stored forever]
                               - tool_call: run_command pwd
                               - tool_result: /home/user success
                               - error: command failed exit_code=1
                               - artifact: large_output.txt (50KB)
```

**Build prompts like this:**
```
System: You are a shell agent...

Memory (last 10 important events):
{"type":"error","tool":"run_command","exit_code":1,"error":"permission denied"}
{"type":"result","tool":"write_file","file":"script.sh","success":true}
{"type":"result","tool":"run_command","preview":"total 156K...","artifact":"artifacts/abc.txt"}

Recent conversation:
User: what failed last time?
Assistant: Let me check... [sees error in memory]
```

---

## **🏗️ Architecture**

### **Current (Dumb)**
```
┌─────────────────┐
│  message_history│  ← Python list, trimmed to 40
│  [msg1...msg40] │
└─────────────────┘
        ↓
   Send all to LLM (10K tokens)
```

### **New (Smart)**
```
┌──────────────────┐
│   Event Log      │  ← JSONL file, grows forever
│  (session_123.   │
│   jsonl)         │
│                  │
│ • user_message   │
│ • tool_call      │
│ • tool_result    │
│ • error          │
│ • summary        │
└──────────────────┘
        ↓
   [Retrieval Layer]
   • Last 8 messages (recent)
   • Last 3 errors (debug context)
   • Last 10 tool results (memory)
   • Summaries (compacted history)
        ↓
   Build smart prompt (3-5K tokens)
        ↓
      LLM
```

### **Key Components**

1. **EventLog class**: Appends every action to `logs/events/<session>.jsonl`
2. **Artifact storage**: Large outputs (>8KB) saved to files, referenced in events
3. **Selective retriever**: Grabs relevant events (errors, recent tools, summaries)
4. **Memory block**: JSONL section in prompt showing important past events
5. **Trim aggressively**: Keep only last 8 chat messages (not 40!)

---

## **📊 Expected Gains**

### **For the System/App**

**Token efficiency:**
- Current: 8,000-15,000 tokens/turn
- New: 3,000-6,000 tokens/turn
- **Savings: 40-60% reduction** → Faster responses, lower API costs

**Memory capacity:**
- Current: Remembers 40 messages (~20 interactions)
- New: Remembers entire session (100+ interactions) via retrieval
- **Infinite memory** without context window limits

**Debugging power:**
- Current: Loses error history when trimmed
- New: Always shows last 3 errors in every prompt
- **Better self-correction**

### **For the User**

**Smarter agent:**
- ✅ Recalls what happened 50 turns ago
- ✅ Sees patterns in failures (e.g., "this failed 3 times before")
- ✅ Doesn't repeat mistakes from earlier in the session
- ✅ Can reference large outputs without re-running commands

**Better conversations:**
- User: "What failed last time?"
- Agent: *checks memory* → "Command X failed with exit code 1 (permission denied)"
- No need to re-run `pwd`, `ls`, `git status` every turn

**Long-running sessions:**
- Can work on complex tasks across 100+ steps without losing context
- Agent builds up knowledge about the project as session progresses

### **Examples**

**Before (dumb):**
```
Turn 50: User runs complex pipeline, gets 50KB output
Turn 60: Agent forgets output (trimmed from history)
Turn 65: User asks "what was the output of that pipeline?"
Agent: "I don't have that information" 😞
```

**After (smart):**
```
Turn 50: User runs pipeline → stored as artifact_abc.txt
Turn 60: Agent has {"artifact":"artifact_abc.txt"} in memory
Turn 65: User asks "what was the output?"
Agent: "Let me read artifacts/abc.txt" → shows output 😎
```

---

## **🎯 One-Sentence Summary**

**Replace the dumb 40-message queue with a smart event log that lets the agent retrieve relevant past actions, remember errors forever, and build lean prompts with only what matters—cutting tokens by 50% while gaining infinite memory.**

---

## **📚 Production-Validated Architectures**

This approach is validated by production systems:

### **1. Letta (formerly MemGPT)** 🏆 Best Match
- **19k+ stars**, production-grade
- **Event-driven memory**: Agents use `archival_memory_search`, `recall_memory_search` to query their own history
- **Infinite sessions**: No 40-message limit—old context summarized, retrieved on-demand
- **Pattern**: Hierarchical memory (core context + archival storage + recall search)

### **2. Generative Agents** 📚 Research-Backed
- **Stanford research** (19k+ stars)
- **Memory stream**: Append-only log scored by:
  - **Recency** (exponential decay)
  - **Relevance** (embedding similarity)
  - **Importance** (1-10 score)
- **Pattern**: Multi-factor retrieval for selective context

### **3. LangGraph** 🛠️ Industry Standard
- **Checkpointing**: State snapshots at every step
- **Time-travel debugging**: Resume from any checkpoint
- **Pattern**: Persistent state with checkpoint-based retrieval

### **4. AutoGen v0.4** 🔧 Modular Memory
- **Memory as a Service**: Pluggable memory backends (Redis, ChromaDB, List)
- **Event-driven messaging**: CloudEvents specification
- **Pattern**: Separate message history from model context

---

## **Implementation Phases**

### **Phase 1: Event Log Infrastructure** (Effort: M, 2-3h)
- Create `EventLog` class in `tools.py`
- Methods: `append()`, `retrieve_recent()`, `retrieve_errors()`
- Storage: `logs/events/<session_id>.jsonl`

### **Phase 2: Capture Events** (Effort: S, 1h)
- Log user messages, tool calls, tool results in `agent.py`
- Add artifact storage for outputs >8KB
- Store artifacts in `ai-terminal-wd/artifacts/<session>_<id>.txt`

### **Phase 3: Selective Context Building** (Effort: M, 2-3h)
- Build `_build_selective_prompt()` method
- Retrieve: last 3 errors, last 10 tool results, last 8 messages
- Format memory block as JSONL in system message

### **Phase 4: Update System Prompt** (Effort: S, 30min)
- Document memory format in system prompt
- Explain artifact references
- Add examples of memory entries

### **Phase 5: Optional - RAG Enhancement** (Effort: L, 1-2d)
- Add embedding-based retrieval for semantic search
- Implement summarization/compaction for old events
- Multi-factor scoring (recency + relevance + importance)

---

## **Backward Compatibility**

✅ **Zero breaking changes**: Keep existing `message_history` as fallback  
✅ **Gradual migration**: Add event log, test, then switch prompt building  
✅ **Tool interfaces unchanged**: No changes to `get_context` or tool outputs  
✅ **Database untouched**: SQLite logging continues as-is  

---

## **Risk Mitigation**

1. **Disk growth**: Add retention via `EVENT_LOG_RETENTION_DAYS` env var
2. **Retrieval quality**: Start with simple recency-based rules, add embeddings later
3. **Prompt quality**: Test that memory block doesn't confuse LLM
4. **Performance**: Event log reads are fast (JSONL is line-based), minimal overhead

---

## **Success Metrics**

**Token efficiency:**
- Measure average tokens/turn before/after
- Target: 40-60% reduction

**Memory capacity:**
- Test sessions with 100+ interactions
- Verify agent recalls early context

**User satisfaction:**
- Agent correctly answers "what failed?" questions
- No redundant command re-runs

**Cost savings:**
- Calculate API cost reduction from token savings

---

## **Implementation Specification**

### **1. Retrieval Heuristics (Concrete)**

**Problem**: "Last N" is naive—need prioritization, deduplication, relevance scoring.

**Solution**: Multi-tier retrieval with scoring

```python
class EventRetriever:
    """Smart event retrieval with scoring and deduplication"""
    
    def retrieve_for_prompt(self, event_log: EventLog, max_events: int = 20) -> list[dict]:
        """
        Retrieve events with priority scoring:
        - Errors: priority 10 (always include recent)
        - Tool results: priority 5 (successful) or 8 (failed)
        - Summaries: priority 7
        - User messages: priority 3 (context only)
        """
        
        events = event_log.read_all()
        scored = []
        
        for event in events:
            score = self._calculate_score(event)
            if score > 0:  # Filter out low-priority events
                scored.append((score, event))
        
        # Sort by score desc, then recency (timestamp)
        scored.sort(key=lambda x: (x[0], x[1]["timestamp"]), reverse=True)
        
        # Deduplicate: same tool + same result within 5 events
        deduped = self._deduplicate(scored, window=5)
        
        # Cap to max_events
        return [event for score, event in deduped[:max_events]]
    
    def _calculate_score(self, event: dict) -> int:
        """Priority scoring logic"""
        event_type = event.get("type")
        
        # Errors always high priority
        if event_type == "tool_result" and not event.get("success"):
            return 10
        
        # Recent errors even higher
        if event_type == "error":
            age_minutes = (datetime.now() - parse_timestamp(event["timestamp"])).total_seconds() / 60
            if age_minutes < 10:
                return 12  # Very recent error
            return 10
        
        # Summaries (compacted history)
        if event_type == "summary":
            return 7
        
        # Successful tool results
        if event_type == "tool_result" and event.get("success"):
            # Prioritize file writes and commands with artifacts
            if event.get("tool") in ["write_file", "run_python_sandbox"]:
                return 6
            if event.get("artifact_path"):
                return 6  # Large output stored
            return 5
        
        # Tool calls (for context)
        if event_type == "tool_call":
            return 4
        
        # User messages (low priority, use recent chat instead)
        if event_type == "user_message":
            return 2
        
        return 0  # Skip other events
    
    def _deduplicate(self, scored: list[tuple], window: int = 5) -> list[tuple]:
        """Remove redundant events (same tool + similar result within window)"""
        seen = {}
        deduped = []
        
        for score, event in scored:
            # Create dedup key
            if event.get("type") == "tool_result":
                key = (
                    event.get("tool"),
                    event.get("success"),
                    event.get("exit_code"),
                    event.get("output_preview", "")[:100]  # First 100 chars
                )
                
                # Check if we've seen this recently
                if key in seen and len(deduped) - seen[key] < window:
                    continue  # Skip duplicate
                
                seen[key] = len(deduped)
            
            deduped.append((score, event))
        
        return deduped
```

**Configuration (via env vars):**
```bash
EVENT_MEMORY_MAX_EVENTS=20        # Max events in memory block
EVENT_MEMORY_ERROR_PRIORITY=10    # Error priority score
EVENT_MEMORY_DEDUP_WINDOW=5       # Deduplication window
EVENT_MEMORY_RECENCY_BOOST=2      # Boost score for recent events (<10min)
```

---

### **2. Prompt Construction (Concrete Schema)**

**Problem**: No concrete format for memory block, size capping, artifact handling.

**Solution**: Strict schema with size limits

```python
def _build_memory_block(self, events: list[dict], max_tokens: int = 2000) -> str:
    """
    Build JSONL memory block with strict schema and size limits.
    
    Schema per line:
    - error: {"type":"error","tool":"X","exit_code":N,"msg":"..."}
    - result: {"type":"result","tool":"X","success":bool,"preview":"...","artifact":"path"}
    - summary: {"type":"summary","turns":[N,M],"actions":["..."]}
    - context: {"type":"context","tool":"X","args_hash":"abc123"}
    """
    
    lines = []
    current_tokens = 0
    
    header = "Agent Memory (prioritized events from this session):"
    lines.append(header)
    lines.append("```jsonl")
    
    for event in events:
        # Format event according to schema
        line = self._format_event_for_memory(event)
        
        # Estimate tokens (rough: 1 token ~= 4 chars)
        line_tokens = len(line) // 4
        
        if current_tokens + line_tokens > max_tokens:
            # Cap reached - add truncation notice
            lines.append("# ... (older events truncated)")
            break
        
        lines.append(line)
        current_tokens += line_tokens
    
    lines.append("```")
    lines.append("")
    lines.append("Use this memory to avoid redundant commands. If you need full output, read the artifact path.")
    
    return "\n".join(lines)

def _format_event_for_memory(self, event: dict) -> str:
    """Format event into strict JSON schema"""
    event_type = event.get("type")
    
    if event_type == "error" or (event_type == "tool_result" and not event.get("success")):
        return json.dumps({
            "type": "error",
            "tool": event.get("tool"),
            "exit_code": event.get("exit_code"),
            "msg": event.get("error", "")[:200]  # Truncate long errors
        }, ensure_ascii=False)
    
    elif event_type == "tool_result" and event.get("success"):
        result = {
            "type": "result",
            "tool": event.get("tool"),
            "success": True
        }
        
        # Add preview or artifact reference
        if event.get("artifact_path"):
            result["artifact"] = event["artifact_path"]
            result["preview"] = event.get("output_preview", "")[:150]  # Short preview
        else:
            result["output"] = event.get("output_preview", "")[:300]  # Inline small outputs
        
        return json.dumps(result, ensure_ascii=False)
    
    elif event_type == "summary":
        return json.dumps({
            "type": "summary",
            "turns": event.get("turn_range", []),
            "actions": event.get("key_actions", [])[:5]  # Top 5 actions
        }, ensure_ascii=False)
    
    elif event_type == "tool_call":
        return json.dumps({
            "type": "context",
            "tool": event.get("tool"),
            "args_hash": event.get("args_hash", "")[:12]
        }, ensure_ascii=False)
    
    return ""  # Skip other event types
```

**Example output:**
```
Agent Memory (prioritized events from this session):
```jsonl
{"type":"error","tool":"run_command","exit_code":1,"msg":"permission denied: /etc/config"}
{"type":"result","tool":"write_file","success":true,"output":"File written: script.sh"}
{"type":"result","tool":"run_command","success":true,"artifact":"ai-terminal-wd/artifacts/abc123.txt","preview":"total 156K\ndrwxr-xr-x 5 user..."}
{"type":"summary","turns":[1,25],"actions":["installed packages","created venv","wrote 3 scripts"]}
```

Use this memory to avoid redundant commands. If you need full output, read the artifact path.
```

**Size Cap Strategy:**
- Max 2000 tokens (~8KB) for memory block
- Truncate individual previews (errors: 200 chars, outputs: 300 chars)
- Drop oldest events if cap exceeded
- Always include last 3 errors (even if over cap)

---

### **3. Integration with Existing Code**

**Problem**: Unclear how event-driven memory interacts with `_trim_history`, `_sanitize_history_tool_calls`.

**Solution**: Keep existing code, slim it down

```python
class MiniAgent:
    # NEW: Event-driven configuration
    MAX_HISTORY_MESSAGES = 10  # Reduced from 40! (was 40)
    MAX_TOOL_OUTPUT_CHARS = 2000  # Reduced from 8000 (was 8000)
    MEMORY_BLOCK_MAX_TOKENS = 2000  # New constant
    
    def __init__(self):
        # ... existing code ...
        
        # Add event log
        self.event_log = EventLog(self.session_id)
        self.event_retriever = EventRetriever()
    
    def process_input(self, user_input: str) -> dict:
        # Log user message to event stream
        self.event_log.append("user_message", {"content": user_input})
        
        # Build prompt from events BEFORE entering loop
        self.message_history = self._build_selective_prompt(user_input)
        
        # ... existing ReAct loop ...
        
        # After tool execution:
        # 1. Log to event stream
        self.event_log.append("tool_result", {
            "tool": tool_name,
            "success": success,
            "exit_code": exit_code,
            "error": error_msg,
            "output_preview": result_str[:2000],
            "artifact_path": artifact_path if len(result_str) > 8000 else None
        })
        
        # 2. Add to message_history (short-term, will be trimmed)
        # ... existing tool message append ...
        
        # 3. Trim aggressively (keep last 10, not 40)
        self._trim_history()  # Still runs, but with lower threshold
    
    def _build_selective_prompt(self, current_user_input: str) -> list[dict]:
        """Replace old prompt building with event-driven version"""
        
        # 1. System message (unchanged)
        messages = [self.message_history[0]]
        
        # 2. Memory block (NEW)
        relevant_events = self.event_retriever.retrieve_for_prompt(
            self.event_log,
            max_events=int(os.getenv("EVENT_MEMORY_MAX_EVENTS", "20"))
        )
        memory_block = self._build_memory_block(
            relevant_events,
            max_tokens=self.MEMORY_BLOCK_MAX_TOKENS
        )
        messages.append({"role": "system", "content": memory_block})
        
        # 3. Recent conversation (last 8 messages, not 40)
        recent_chat = [
            self._to_dict_message(m) 
            for m in self.message_history[-8:] 
            if m.get("role") in ("user", "assistant", "tool")
        ]
        messages.extend(recent_chat)
        
        # 4. Current user input (not added yet, will be added by caller)
        # messages.append({"role": "user", "content": current_user_input})
        
        return messages
    
    def _trim_history(self):
        """Keep trimming for short-term storage, but more aggressive"""
        # Now we only need to keep recent conversation (8-10 messages)
        # Memory block handles long-term recall
        
        if len(self.message_history) <= self.MAX_HISTORY_MESSAGES:
            return
        
        system_msg = self.message_history[0]
        messages = [self._to_dict_message(m) for m in self.message_history[1:]]
        
        # Keep only last 8 messages (reduced from 40)
        recent = messages[-8:]
        
        # ... existing orphan tool message cleanup ...
        # (keep this logic unchanged)
        
        self.message_history = [system_msg] + recent
```

**Key Changes:**
- `MAX_HISTORY_MESSAGES`: 40 → 10 (aggressive trimming)
- `MAX_TOOL_OUTPUT_CHARS`: 8000 → 2000 (rely on artifacts)
- `_build_selective_prompt()`: New method, replaces old logic
- `_trim_history()`: Still runs, but on smaller window
- `_sanitize_history_tool_calls()`: Unchanged, still normalizes tool calls

**Migration Path:**
1. Add event log alongside existing history (both run in parallel)
2. Test prompts side-by-side (old vs new)
3. Switch to new prompt building via feature flag
4. Remove old history once validated

---

### **4. get_context Integration**

**Problem**: No plan for exposing event memory via `get_context`.

**Solution**: Add event summary to `get_context` output

```python
# tools.py - GetContextTool
class GetContextTool(BaseTool):
    def execute(self) -> str:
        # ... existing context building ...
        
        # Add event memory summary
        event_log_path = Path(f"logs/events/{_SESSION_STATE.session_id}.jsonl")
        if event_log_path.exists():
            # Read last 50 events for summary
            recent_events = []
            with open(event_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    recent_events.append(json.loads(line))
            
            # Summarize event counts
            event_summary = {
                "total_events": len(recent_events),
                "errors": len([e for e in recent_events if e.get("type") == "error" or not e.get("success", True)]),
                "tool_calls": len([e for e in recent_events if e.get("type") == "tool_call"]),
                "artifacts_created": len([e for e in recent_events if e.get("artifact_path")]),
                "event_log_path": str(event_log_path)
            }
            
            context["event_memory"] = event_summary
        
        return json.dumps(context, indent=2)
```

**get_context output (new section):**
```json
{
  "working_dir": "...",
  "session": {...},
  "event_memory": {
    "total_events": 127,
    "errors": 3,
    "tool_calls": 45,
    "artifacts_created": 8,
    "event_log_path": "logs/events/abc123.jsonl"
  }
}
```

---

### **5. Test Migration Plan**

**Problem**: Existing tests assume 40-message history, no event log.

**Solution**: Update tests incrementally

```python
# tests/test_event_memory.py (NEW)
def test_event_log_capture():
    """Verify events are logged correctly"""
    agent = MiniAgent()
    agent.process_input("list files")
    
    # Check event log exists
    event_path = Path(f"logs/events/{agent.session_id}.jsonl")
    assert event_path.exists()
    
    # Verify events
    events = []
    with open(event_path) as f:
        for line in f:
            events.append(json.loads(line))
    
    assert any(e["type"] == "user_message" for e in events)
    assert any(e["type"] == "tool_call" for e in events)

def test_event_retrieval_prioritization():
    """Verify errors are prioritized over normal results"""
    retriever = EventRetriever()
    
    events = [
        {"type": "tool_result", "success": True, "timestamp": "2025-01-01T10:00:00Z"},
        {"type": "error", "tool": "run_command", "timestamp": "2025-01-01T10:01:00Z"},
    ]
    
    # Error should come first despite being later
    retrieved = retriever.retrieve_for_prompt(events, max_events=10)
    assert retrieved[0]["type"] == "error"

def test_memory_block_size_cap():
    """Verify memory block doesn't exceed token limit"""
    agent = MiniAgent()
    
    # Generate 100 events
    for i in range(100):
        agent.event_log.append("tool_result", {
            "tool": "run_command",
            "success": True,
            "output_preview": "x" * 1000
        })
    
    # Build memory block
    events = agent.event_retriever.retrieve_for_prompt(agent.event_log, max_events=50)
    memory_block = agent._build_memory_block(events, max_tokens=2000)
    
    # Should be capped
    assert len(memory_block) < 10000  # ~2000 tokens * 4 chars/token + overhead

# tests/test_agent.py (UPDATE EXISTING)
def test_message_history_trimming():
    """Update to expect 10 messages, not 40"""
    agent = MiniAgent()
    
    # ... existing test ...
    
    # Changed expectation
    assert len(agent.message_history) <= 10  # Was: <= 40

def test_selective_prompt_building():
    """New test for event-driven prompts"""
    agent = MiniAgent()
    
    # Simulate session with errors
    agent.event_log.append("error", {"tool": "run_command", "exit_code": 1})
    agent.event_log.append("tool_result", {"tool": "write_file", "success": True})
    
    # Build prompt
    prompt = agent._build_selective_prompt("what failed?")
    
    # Should have system + memory + recent
    assert len(prompt) >= 2  # System + memory block
    assert any("Agent Memory" in str(m.get("content", "")) for m in prompt)
```

---

## **Architecture Decisions - Clarifications**

### **1. Token Budget Overflow Handling**

**Problem**: Prioritized events might still exceed `MEMORY_BLOCK_MAX_TOKENS` (2000). What happens?

**Decision**:
```python
# EventRetriever.retrieve_for_prompt() returns events in priority order:
# 1. Last 3 errors (non-negotiable, always included if available)
# 2. Last error's context (tools/commands around the error)
# 3. Last 5 successful tool results (high signal)
# 4. Recent summaries (if available)
# 5. Recent chat turns (if space remains)

def _build_memory_block(self, events, max_tokens=2000):
    """Build memory block with soft overflow handling"""
    block = []
    token_count = 0
    required_count = 0
    
    # Phase 1: Include non-negotiable errors (must-have)
    errors = [e for e in events if e.get("type") == "error"]
    for e in errors[:3]:  # Last 3 errors
        tokens = len(json.dumps(e)) // 4 + 50  # rough estimate
        if token_count + tokens <= max_tokens:
            block.append(e)
            token_count += tokens
            required_count += 1
        # If errors don't fit, still force-include first error for debugging
        elif required_count == 0:
            block.append(e)
            token_count += tokens
            required_count += 1
            break  # Stop here, only include first error
    
    # Phase 2: Add other events up to budget
    other_events = [e for e in events if e.get("type") != "error"]
    for e in other_events:
        tokens = len(json.dumps(e)) // 4 + 50
        if token_count + tokens <= max_tokens:
            block.append(e)
            token_count += tokens
        else:
            break  # Stop when budget exceeded
    
    # Return what fit (partial is acceptable)
    return block
```

**Behavior**:
- ✅ Errors **always** take priority (at least 1 error is guaranteed if any exist)
- ✅ Successful results included until token budget is exhausted
- ✅ If memory block exceeds limit, truncate from tail (oldest events first)
- ✅ Return partial memory block (not an error—selective memory is the point)

**Token accounting**:
```
Total prompt = system_msg + memory_block + recent_chat
Example:
- System msg: ~800 tokens
- Memory block: ~1500 tokens (soft limit, may reach ~2000)
- Recent chat (last 8 msgs): ~800 tokens
- Total: ~3100 tokens (acceptable for 4K context window)
```

---

### **2. Artifact Usage Pattern**

**Problem**: Spec stores large outputs (>8KB) as artifact files and adds path references to memory block. How does agent use them?

**Decision - Two-Mode Artifact Handling**:

**Mode A: Implicit Artifacts (Default)**
```json
{
  "type": "result",
  "tool": "run_command",
  "success": true,
  "output_preview": "total 156K\n-rw-r--r-- 1 user staff 127K Nov 9 10:23 large_file.tar.gz",
  "artifact_path": "artifacts/cmd_ls_abc123.txt"
}
```
- Agent sees `artifact_path` field in memory
- Agent does **NOT** automatically read artifact
- Agent uses path only if needed to respond to user query like "show me that output again"
- System prompt includes note: *"When memory shows artifact_path, use `read_file` if user asks for the full output"*

**Mode B: Explicit Artifact References (for crucial data)**
```json
{
  "type": "result",
  "tool": "run_python_sandbox",
  "success": true,
  "output_preview": "[First 500 chars of analysis result...]",
  "artifact_path": "artifacts/analysis_xyz.json",
  "artifact_type": "json_data",
  "artifact_summary": "ML model metrics (accuracy=0.94, loss=0.12)"
}
```
- Agent sees summary + path
- System prompt: *"If `artifact_summary` is present, that's the key insight—reference it. Read the full artifact only if user needs details"*

**System Prompt Update**:
```
Artifact Handling Rules:
- When memory shows "artifact_path", the output was too large to fit in context
- For artifact_summary: Use the summary directly in your reasoning
- For other artifacts: Only call read_file if the user explicitly asks for that data
- Example: User asks "what failed?" → use memory block error summary
         User asks "show me the pipeline output" → read_file(artifact_path)
```

**Rationale**:
- Avoids wasteful artifact reads on every turn (keep memory lean)
- Agent retains agency: reads artifacts only when relevant
- Fallback for user: "What was in that 50KB output?" → agent reads artifact on demand

---

### **3. SQLite + JSONL Relationship**

**Problem**: No clear statement on whether both logging systems coexist, mirror, or if JSONL replaces SQLite.

**Decision - Hybrid Approach (Parallel, Non-Mirrored)**

**Phase 1-3 (Event Rollout)**:
- **JSONL is primary event stream** (EventLog writes to `logs/events/<session>.jsonl`)
  - Used for prompt building, artifact references, retrieval
- **SQLite continues unchanged** (DBLogger writes to `session_logs.db`)
  - Retains human-readable session summaries, query interface
  - Does NOT mirror every event (too granular, wastes DB space)
  - Contains only high-level summaries: session_info, session_errors, session_tool_history

**No Mirroring**:
```python
# OLD: Both log everything
db_logger.log_entry(session_id, "TOOL_CALL", tool_name)  # → SQLite
db_logger.log_entry(session_id, "TOOL_RESULT", result)   # → SQLite

# NEW: Separate concerns
event_log.append("tool_call", {...})  # → JSONL (agent memory)
# SQLite only updated at session close for summary:
db_logger.log_summary(session_id, {
    "total_events": 127,
    "errors": 3,
    "final_branch": "main",
    "session_duration": 300
})
```

**Why Parallel?**:
| System | Purpose | Query | Retention |
|--------|---------|-------|-----------|
| **JSONL** | Agent memory, prompt building | Sequential read, retrieval scoring | Per-session, auto-cleanup via `EVENT_LOG_RETENTION_DAYS` |
| **SQLite** | Human audit trail, session UI | SQL queries, indexed lookups | Long-term, manual cleanup |

**Migration Path**:
1. **Now (Phase 1-2)**: Both run, JSONL for agent, SQLite for history
2. **Later (Phase 5+)**: If embedding-based retrieval is added, optionally sync JSONL summaries into SQLite full_text search table for post-hoc analysis
3. **Never (Skip)**: Don't mirror raw events—too costly, defeats purpose of JSONL compaction

**get_context output** (shows both):
```json
{
  "session": {
    "id": "abc123",
    "duration_seconds": 150,
    "interactions": 8,
    "tool_calls": 15
  },
  "event_memory": {
    "total_events": 45,
    "errors": 2,
    "artifacts_created": 3,
    "event_log_path": "logs/events/abc123.jsonl"
  },
  "db_summary": {
    "last_logged_at": "2025-01-01T10:15:00Z",
    "summary_available": true
  }
}
```

---

## **Next Steps**

1. **Implement core classes**: `EventLog`, `EventRetriever` (Phase 1)
2. **Add event capture**: Update `agent.py` to log events (Phase 2)
3. **Build retrieval logic**: Implement scoring, deduplication (Phase 2.5)
4. **Update prompt building**: Replace old logic with `_build_selective_prompt()` (Phase 3)
5. **Test side-by-side**: Compare old vs new prompts, measure tokens (Phase 3)
6. **Update tests**: Migrate existing tests, add new event tests (Phase 4)
7. **Feature flag rollout**: `USE_EVENT_MEMORY=1` env var for gradual rollout
8. **Validate**: Run 100+ interaction sessions, ensure no regressions
9. **Ship**: Make event-driven memory the default

**Estimated Total Effort**: 6-8 hours for production-ready implementation (increased from 4-6h to account for rigorous testing)
