# Quick Reference: Enhanced get_context Additions

## Current Output
```json
{
  "working_dir": "path",
  "shell_cwd": "path",
  "recent_writes": ["file1", "file2"]
}
```

## What's Missing for AI Agents?

| Category | Missing | Use Case |
|----------|---------|----------|
| **Tools** | Which tools work? Sandbox limits? | Skip unavailable tools, respect limits |
| **Git** | Repo context already gathered, not exposed | Make branch-aware decisions |
| **Commands** | What just ran? Exit codes? | Understand state, debug failures |
| **System** | CPU, memory, disk capacity | Batch work appropriately |
| **Interpreters** | Python/Node/Ruby available? | Pick right language for task |
| **Constraints** | Write protection? Network disabled? | Avoid commands that will fail |

---

## Top 5 Quick Wins (15 min total)

### 1. **Tool Availability** (2 min)
```python
"tools": {
  "available": ["read_file", "write_file", "run_command", ...]
}
```
**Why**: Agent knows what it can actually use

### 2. **Sandbox Status** (5 min)
```python
"tools": {
  "sandboxed": {
    "enabled": true/false,
    "timeout_seconds": 30,
    "max_memory_mb": 1024,
    "network_disabled": true
  }
}
```
**Why**: Agent respects limits, makes smaller batches if needed

### 3. **Git Context** (2 min - data already exists!)
```python
"repository": {
  "in_git_repo": true,
  "branch": "feature/kimi2-agent-support",
  "repo_name": "ai-terminal",
  "uncommitted_changes_count": 3
}
```
**Why**: Context-aware decisions ("don't break this branch", "commit your work")

### 4. **Last Command Status** (2 min)
```python
"activity": {
  "last_command_exit_code": 0,
  "recent_writes": ["output.txt", "data.json"]
}
```
**Why**: Agent knows if previous operation succeeded

### 5. **Available Interpreters** (4 min)
```python
"capabilities": {
  "interpreters_available": {
    "python": "/usr/bin/python3",
    "node": "/usr/bin/node",
    "ruby": null,
    "bash": "/bin/bash"
  }
}
```
**Why**: Pick the right tool for the job

---

## Example Scenarios

### Scenario 1: Resource Constraints
```
Agent sees: max_memory_mb: 512, recent_timeout: true

Decision: Instead of loading entire CSV:
- Use chunked processing
- Stream data instead of buffering
- Break into smaller batches
```

### Scenario 2: Git Awareness
```
Agent sees: branch: "main", uncommitted_changes_count: 0

Decision:
- Feel safe to experiment
- Create feature branch for risky work
- Commit work when done
```

### Scenario 3: Tool Selection
```
Agent sees: interpreters_available.python: "/usr/bin/python3"
           interpreters_available.node: null

Decision: Use Python for script, avoid Node.js
```

### Scenario 4: Debugging
```
Agent sees: last_command_exit_code: 1

Decision:
- Last command failed
- Check error output
- Diagnose before retrying
```

---

## Implementation Checklist

- [ ] Add `tools.available` - list TOOLS.keys()
- [ ] Add `tools.sandboxed` - read environment variables
- [ ] Add `tools.isolation` - check SANDBOX_ENABLE_ISOLATION
- [ ] Add `repository` - expose git_info already gathered
- [ ] Add `activity.last_command_exit_code` - track in ShellIntegration
- [ ] Add `capabilities.interpreters_available` - use shutil.which()
- [ ] Add `capabilities.package_managers` - check which pm exists
- [ ] Add `system` metrics - parse existing system_info

---

## Code Locations

| Component | File | Location |
|-----------|------|----------|
| Tool registry | `tools.py` | ~line 880 (GetContextTool class) |
| Shell tracking | `shell_integration.py` | ShellIntegration.__init__ |
| System info | `utils/system_info.py` | get_system_info() |
| Git info | `utils/system_info.py` | get_git_info() |
| Config | `config.py` | Load_config() |

---

## Agent Benefits Summary

| Agent Behavior | Before | After |
|---|---|---|
| Knows what tools available? | ❌ Guesses | ✅ Checks get_context |
| Respects sandbox limits? | ❌ No awareness | ✅ Knows timeout, memory |
| Makes git-aware decisions? | ❌ Agnostic | ✅ Sees branch, changes |
| Understands recent failures? | ❌ Starts fresh | ✅ Sees exit codes |
| Picks right language? | ❌ Default to Python | ✅ Checks available |
| Prevents resource errors? | ❌ Tries and fails | ✅ Plans around limits |

---

## JSON Response Size

Current: ~300 bytes
Enhanced: ~1.5-2 KB (includes all new fields)

**No problem**: Returned once per agent turn, negligible cost

---

## Backward Compatibility

✅ **All new fields are additive**
✅ **Original fields (`working_dir`, `shell_cwd`, `recent_writes`) preserved**
✅ **Existing agents keep working**
✅ **New agents get enriched context**

---

## Next Steps

1. **Read**: `history/ENHANCED_GET_CONTEXT_ANALYSIS.md` (full details)
2. **Review**: The proposed JSON structure
3. **Pick approach**: Phase 1 (quick wins) or full implementation
4. **Code**: Add methods to GetContextTool
5. **Test**: Verify context is accurate
6. **Update agent system prompt**: Tell AI about new context fields
