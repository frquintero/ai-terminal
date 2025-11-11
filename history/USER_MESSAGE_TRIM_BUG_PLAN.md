# User Message Trimming Bug - Fix Plan

## Problem Summary

**Critical Bug**: User messages are being trimmed from message history before the first API call, causing the model to respond to stale/missing context.

### Evidence (Trace 7b911993.json)

**User Query:**
```
"righ! nevertheless, you did not answer my question...count how many callings you made before getting the final response"
```

**Model Response:**
```
"Final Answer: Kate has been successfully opened with the moon_phase_calculation.txt file..."
```

**Completely unrelated!** The model never saw the user's question.

### Root Cause Analysis

**Location:** `agent.py`, `process_input()` method, lines 817-822

```python
self._log("USER_QUERY", user_input)
                                        # ← User message appended
self.message_history.append({"role": "user", "content": user_input})
self._record_user_event(user_input)

self._trim_history()                   # ← IMMEDIATELY trims history!
```

**The Bug:**
1. User message gets appended to `message_history`
2. `_trim_history()` called immediately after
3. Trim keeps only `MAX_HISTORY_MESSAGES = 3` recent non-system messages
4. If there are pending tool results or plan reminders from previous turn, user message gets DROPPED
5. Model receives request with NO user message
6. Model responds based on stale context (last thing in memory)

**Confirmed by trace inspection:**
- `logs/openai_traces/7b911993.json` contains NO user messages
- Only system messages, previous assistant, tool results, plan reminders
- User query logged to DB but never sent to API

### Impact

This bug causes:
1. **Unrelated responses** - model answers questions it never saw
2. **Thought-only leaks** - model confused about what to do
3. **Context loss** - multi-turn conversations break down
4. **User frustration** - agent appears to ignore direct questions

## Solution Design

### Option 1: Defer trim until after first response (RECOMMENDED)

**Strategy:** Only trim history on subsequent loop iterations, not before the first API call of a turn.

**Implementation:**
```python
def process_input(self, user_input: str) -> dict:
    # ... existing setup ...
    
    self._log("USER_QUERY", user_input)
    self.message_history.append({"role": "user", "content": user_input})
    self._record_user_event(user_input)
    
    # DO NOT TRIM HERE - user message must reach the model!
    # self._trim_history()  # ← REMOVE THIS
    
    tools = get_tool_schemas()
    max_steps = self.config.max_steps
    step_count = 0
    
    react_loop_count = 0
    react_limit_warning_sent = False
    
    while step_count < max_steps:
        # Trim only AFTER first response, before subsequent calls
        if step_count > 0:
            self._trim_history()
        
        tool_state = self._sanitize_history_tool_calls()
        request_messages = self._build_request_messages()
        # ... rest of loop ...
```

**Pros:**
- Simple, surgical fix
- Guarantees user message reaches model on first call
- Maintains trimming for subsequent iterations
- No changes to `_trim_history()` logic

**Cons:**
- First API call might have slightly more tokens (acceptable tradeoff)

### Option 2: Smart trim that protects user messages

**Strategy:** Modify `_trim_history()` to never drop the most recent user message.

**Implementation:**
```python
def _trim_history(self, protect_last_user=False):
    """
    Keep the system message plus the most recent N exchanges.
    If protect_last_user=True, ensure the last user message is retained.
    """
    if self._pending_tool_history:
        self._truncate_tool_outputs(self.message_history)
        return

    if len(self.message_history) <= self.MAX_HISTORY_MESSAGES:
        return

    system_msg = self.message_history[0]
    messages = [self._to_dict_message(m) for m in self.message_history[1:]]
    
    # Find last user message index if protecting
    last_user_idx = -1
    if protect_last_user:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get('role') == 'user':
                last_user_idx = i
                break
    
    max_other = max(self.MAX_HISTORY_MESSAGES - 1, 0)
    
    if max_other <= 0:
        recent = []
    else:
        recent = messages[-max_other:]
        
        # Ensure last user message is included
        if protect_last_user and last_user_idx != -1:
            if last_user_idx < len(messages) - max_other:
                # User message would be dropped, force include it
                recent = messages[last_user_idx:]
    
    self._truncate_tool_outputs(recent)
    self.message_history = [system_msg] + recent
```

Call with: `self._trim_history(protect_last_user=True)` before first API call.

**Pros:**
- More defensive, protects against similar bugs
- Explicit intent in code

**Cons:**
- More complex logic
- Could create edge cases with message ordering

### Option 3: Move trim to end of turn

**Strategy:** Only trim history at the very end of `process_input()`, after all loops complete.

**Pros:**
- Simplest change
- Entire turn has full context

**Cons:**
- Could hit token limits on long ReAct loops
- Less predictable memory usage

## Recommended Approach

**Implement Option 1** - defer trim until after first response.

### Rationale:
1. **Minimal risk** - surgical one-line change
2. **Clear semantics** - user message MUST reach model
3. **Maintains trimming** - still prevents token bloat in multi-step loops
4. **Easy to verify** - check traces after fix to confirm user messages present

## Testing Plan

1. **Apply fix** (Option 1 implementation)
2. **Reproduce test case:**
   - Start new session
   - Have agent execute multi-step task (moon phase calculation)
   - Ask follow-up question: "count how many tool calls you made"
3. **Verify fix:**
   - Check `logs/openai_traces/<new_trace>.json`
   - Confirm user message present in messages array
   - Confirm model response is relevant to user query
4. **Regression check:**
   - Run through 10+ various interactions
   - Ensure no token limit errors
   - Verify ReAct loop still works correctly

## Success Criteria

- [ ] User messages always present in first API call of each turn
- [ ] Model responses relevant to user queries
- [ ] No token limit errors in multi-step tasks
- [ ] Traces show proper message ordering
- [ ] No new "Thought-only leak" cases

## Implementation Notes

- Change is in `agent.py`, `process_input()` method
- Remove line 822: `self._trim_history()`
- Add conditional trim inside while loop after line 827
- Update related bead: ai-terminal-61p
- Test thoroughly before merging to main
