# get_context Enhancement - Implementation Plan

## Executive Summary

**Goal**: Enhance `get_context` tool to provide rich session context WITHOUT duplicating system info already in the prompt.

**Key Insight**: System info is static and sent with every prompt (heavy). Session info is dynamic and only retrieved when needed via `get_context` (lightweight).

---

## Current State Analysis

### What's Already in System Prompt (Sent Every Turn - Must Stay Light)
```python
# From agent.py _build_system_prompt():
system_context = format_system_info(system_info)
# Contains:
# - OS name and shell
# - User and home directory  
# - PATH (first 5 dirs)
```

### Current get_context Output (Retrieved On-Demand)
```json
{
  "working_dir": "ai-terminal-wd/",
  "shell_cwd": "/current/dir",
  "recent_writes": ["file1.txt", "file2.py"]
}
```

### What's Missing
- Session interaction history (tool calls, commands, results)
- Available tools and their constraints
- Git repository context (branch, changes)
- Exit codes from recent commands
- Sandbox/isolation configuration status
- Recent errors or failures

---

## Design Principles

### 1. **No Duplication**
- ❌ Don't repeat system info (OS, shell, user) already in prompt
- ✅ Focus on SESSION-SPECIFIC dynamic context

### 2. **Lightweight Prompt**
- ✅ Keep system prompt minimal (static info only)
- ✅ Session context retrieved on-demand via get_context

### 3. **Debugging-Friendly**
- ✅ Track tool execution history within session
- ✅ Track command exit codes and errors
- ✅ Provide timeline of what happened

### 4. **Zero Regression**
- ✅ Backward compatible (keep existing fields)
- ✅ No performance impact on prompt
- ✅ Minimal overhead on get_context calls

---

## Enhanced get_context Structure

```json
{
  // EXISTING (Keep for compatibility)
  "working_dir": "string",
  "shell_cwd": "string", 
  "recent_writes": ["file1", "file2"],
  
  // NEW: Session activity tracking
  "session": {
    "id": "uuid",
    "start_time": "ISO8601",
    "duration_seconds": 123,
    "total_interactions": 5,
    "total_tool_calls": 12
  },
  
  // NEW: Recent tool execution history
  "tool_history": [
    {
      "tool": "run_command",
      "args": {"command": "ls -la"},
      "timestamp": "ISO8601",
      "exit_code": 0,
      "success": true,
      "error": null
    },
    {
      "tool": "run_python_sandbox",
      "timestamp": "ISO8601", 
      "success": false,
      "error": "TimeoutExpired"
    }
  ],
  
  // NEW: Available tools (just names, schemas are in prompt)
  "available_tools": {
    "all": ["read_file", "write_file", "run_command", ...],
    "sandboxed": ["run_python_sandbox"],
    "interactive": ["run_interactive"]
  },
  
  // NEW: Configuration state (dynamic, changes per session)
  "configuration": {
    "sandbox": {
      "enabled": true,
      "timeout_seconds": 30,
      "max_memory_mb": 1024,
      "network_disabled": true
    },
    "isolation": {
      "enabled": false,
      "rootfs_sha256": null
    }
  },
  
  // NEW: Git context (if in repo)
  "repository": {
    "in_repo": true,
    "branch": "master",
    "uncommitted_changes": 3
  },
  
  // NEW: Recent errors (last 3)
  "recent_errors": [
    {
      "timestamp": "ISO8601",
      "tool": "run_command",
      "error": "Command failed with exit code 1",
      "command": "grep nonexistent file.txt"
    }
  ]
}
```

---

## Implementation Strategy

### Phase 1: Session Tracking Infrastructure (Core)
**Files**: `agent.py`, `tools.py`

1. **Add session state to MiniAgent**
   - Track session start time
   - Track total interactions and tool calls
   - Track recent tool execution history (deque, max 20)

2. **Update GetContextTool to access agent state**
   - Pass agent reference to tool (or use shared state)
   - Read session metrics
   - Format tool history

### Phase 2: Tool Execution Tracking
**Files**: `agent.py` (in process_input loop)

1. **Track each tool call**
   - Tool name
   - Arguments (truncated if large)
   - Timestamp
   - Success/failure
   - Exit code (for run_command)
   - Error message (if failed)

2. **Track errors separately**
   - Keep last 3 errors in dedicated list
   - Include context (tool, command, timestamp)

### Phase 3: Configuration & Repository Context
**Files**: `tools.py` (GetContextTool)

1. **Add configuration state**
   - Read sandbox env vars
   - Read isolation status
   - Format as structured JSON

2. **Add git context**
   - Use existing `get_git_info()` from utils
   - Only include if in repo
   - Show branch, uncommitted count

### Phase 4: Update System Prompt
**Files**: `agent.py` (_build_system_prompt)

1. **Update get_context description**
   - Explain it now includes session history
   - Mention it's the source for debugging context
   - Examples of when to use

2. **Remove redundant info from prompt**
   - Keep only: OS, shell, user, PATH (static)
   - Remove anything now in get_context

---

## Avoiding Code Duplication

### Reuse Existing Functions
```python
# Already exists in utils/system_info.py - REUSE
get_git_info()

# Already exists in tools.py - REFERENCE
TOOLS dictionary (for available_tools list)

# Already gathered in agent.py - REUSE
self.session_id (from db_logger)
```

### Shared State Pattern
```python
# Option A: Pass agent to tool (simple)
class GetContextTool(BaseTool):
    def __init__(self, agent=None):
        self.agent = agent
    
    def execute(self):
        session_info = self.agent.get_session_info()
        ...

# Option B: Module-level state (current pattern)
_SESSION_STATE = {
    "start_time": None,
    "tool_history": deque(maxlen=20),
    "recent_errors": deque(maxlen=3)
}
```

### Single Source of Truth
- Session tracking: `agent.py` (owns session lifecycle)
- Tool history: `agent.py` (sees all tool calls)
- Git info: `utils/system_info.py` (already exists)
- Tool list: `tools.py > TOOLS` (already exists)
- Config: Environment variables (read once in get_context)

---

## Preventing Regression

### Backward Compatibility Checklist
- [ ] Keep existing fields: `working_dir`, `shell_cwd`, `recent_writes`
- [ ] All new fields are additive (no removals)
- [ ] get_context still works with zero args
- [ ] JSON structure remains valid

### Performance Checklist
- [ ] System prompt size unchanged (no new static info)
- [ ] get_context adds <5ms overhead (session state is in-memory)
- [ ] Tool history limited to 20 entries (bounded memory)
- [ ] No new file I/O (git info uses cached result)

### Testing Checklist
- [ ] Verify get_context returns valid JSON
- [ ] Verify all new fields present and accurate
- [ ] Verify session metrics increment correctly
- [ ] Verify tool history captures exit codes
- [ ] Verify errors logged correctly
- [ ] Verify backward compatibility (old clients work)

---

## System Prompt Update

### Current Mention
```
- get_context: Use to query working_dir, shell_cwd, and files written this turn. 
  Avoid redundant pwd/ls unless you truly need listing output.
```

### Enhanced Mention
```
- get_context: Retrieve current session context including:
  * Execution state (working_dir, shell_cwd)
  * Session history (tool calls, commands, exit codes)
  * Recent errors and their context
  * Available tools and configuration
  * Repository state (branch, uncommitted changes)
  Use this for debugging, understanding session state, or checking recent results.
  Prefer this over redundant pwd/ls/git status commands.
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (30 min)
1. Add session state tracking to MiniAgent
2. Add tool history tracking in process_input loop
3. Update GetContextTool to access session state
4. Test: session metrics appear in get_context

### Phase 2: Tool Execution Details (20 min)
1. Track exit codes from run_command
2. Track errors separately
3. Format tool history with timestamps
4. Test: tool history shows recent calls

### Phase 3: Context Enrichment (20 min)
1. Add git context (reuse get_git_info)
2. Add configuration state (read env vars)
3. Add available tools list (from TOOLS)
4. Test: all new fields accurate

### Phase 4: Prompt & Documentation (10 min)
1. Update system prompt with new description
2. Update tool schema description
3. Test: agent uses get_context effectively

**Total Estimated Time**: ~80 minutes

---

## Code Changes Summary

### Files to Modify

1. **agent.py** (~40 lines added)
   - Add session tracking attributes to __init__
   - Add tool history tracking in process_input
   - Add method to provide session info to tools
   - Update system prompt description

2. **tools.py** (~50 lines added)
   - Update GetContextTool.execute() with new fields
   - Add helper methods (_get_git_context, _get_config, etc.)
   - Update schema description

3. **shell_integration.py** (~10 lines added)
   - Track last_exit_code (if not already)
   - Make accessible to tools

### No Changes Needed
- `utils/system_info.py` - Already has get_git_info
- `config.py` - No changes
- `db_logger.py` - No changes

---

## Example Usage Scenario

### User Query
```
"The last command failed, what happened?"
```

### Agent Response (using get_context)
```python
# Agent calls: get_context()
# Receives:
{
  "tool_history": [
    {"tool": "run_command", "command": "grep foo bar.txt", "exit_code": 1, "error": "..."}
  ],
  "recent_errors": [
    {"tool": "run_command", "error": "Command failed with exit code 1", "command": "grep foo bar.txt"}
  ]
}

# Agent responds:
"The last command `grep foo bar.txt` failed with exit code 1. 
This typically means the pattern 'foo' was not found in bar.txt.
Let me check if the file exists..."
```

---

## Success Criteria

### Technical
- ✅ get_context returns enriched JSON
- ✅ Session metrics accurate (interactions, tool calls, duration)
- ✅ Tool history captures last 20 calls with exit codes
- ✅ Recent errors tracked (last 3)
- ✅ Git context accurate (if in repo)
- ✅ Configuration state reflects env vars
- ✅ Zero regression (backward compatible)
- ✅ System prompt still lightweight

### Functional
- ✅ Agent can debug failed commands using get_context
- ✅ Agent understands session timeline
- ✅ Agent knows available tools without guessing
- ✅ Agent respects sandbox limits from config
- ✅ Agent makes git-aware decisions

### Performance
- ✅ System prompt size unchanged
- ✅ get_context adds <5ms overhead
- ✅ No memory leaks (bounded history)

---

## Risk Mitigation

### Risk: Breaking Existing Code
**Mitigation**: Keep all existing fields, only add new ones. Test with simple get_context call.

### Risk: Performance Degradation
**Mitigation**: All session data in-memory. Bounded collections (deque maxlen). No extra I/O.

### Risk: Prompt Bloat
**Mitigation**: NO changes to system prompt static content. Only update tool description.

### Risk: Code Duplication
**Mitigation**: Reuse get_git_info, TOOLS dict, session_id. Single source of truth.

---

## Next Steps

1. **Review and approve this plan**
2. **Create bd issues for implementation**
   - Issue 1: Core session tracking (Phase 1)
   - Issue 2: Tool execution tracking (Phase 2)
   - Issue 3: Context enrichment (Phase 3)
   - Issue 4: Prompt update (Phase 4)
3. **Implement phase by phase**
4. **Test after each phase**
5. **Commit with .beads/issues.jsonl**

---

## Open Questions

1. **Q**: Should we pass agent reference to GetContextTool or use module-level state?
   **A**: Module-level state is cleaner (matches current pattern with _RECENT_WRITES)

2. **Q**: Should tool history include full arguments or truncate large ones?
   **A**: Truncate args longer than 200 chars to prevent bloat

3. **Q**: Should we track shell command history separately from tool history?
   **A**: No, tool_history captures everything. run_command entries include the command.

4. **Q**: Should configuration state be cached or read fresh each time?
   **A**: Read fresh (env vars might change during session, unlikely but possible)

---

**Status**: Ready for review and approval
**Estimated Effort**: 80 minutes implementation + 20 minutes testing
**Risk Level**: Low (additive changes, backward compatible)
**Value**: High (better debugging, session awareness, context continuity)
