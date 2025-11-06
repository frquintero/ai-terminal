# Summary: Enhancing get_context for AI Agents

## The Insight

Your `get_context` tool currently returns:
```json
{
  "working_dir": "...",
  "shell_cwd": "...",
  "recent_writes": [...]
}
```

**Problem**: An AI agent making decisions has no awareness of:
- What tools can actually run
- System constraints (memory, sandbox limits)
- Recent execution results
- Available interpreters/languages
- Repository state
- System resources

**Opportunity**: Expose this context so agents make **smarter, context-aware decisions**.

---

## What AI Agents Need to Know

### 1. **"What can I do?"** (Tools & Capabilities)
- Which tools are available
- Are they constrained? (sandbox limits, timeout)
- Is namespace isolation enabled?
- What interpreters are available?

**Agent benefit**: Avoid "tool not available" errors, respect resource limits

### 2. **"Where am I?"** (Environment)
- Working directory state
- Git repository context (branch, uncommitted changes)
- System resources (CPU cores, memory, disk)
- Python version and sandbox config

**Agent benefit**: Make context-aware decisions ("don't break this branch", "use smaller batches")

### 3. **"What just happened?"** (Activity)
- Recent commands and their exit codes
- Recently written files
- Last command status

**Agent benefit**: Understand if previous operation succeeded, debug failures

---

## Proposed Enhancements

### High Impact (Easy to Add)
✅ **Tool availability list** - Agent can check what it can use
✅ **Sandbox configuration** - Agent respects memory/timeout limits
✅ **Git context** - Agent makes branch-aware decisions
✅ **Exit codes** - Agent knows if last command succeeded
✅ **Available interpreters** - Agent picks right language

### Medium Impact (Good to Have)
✅ **System metrics** - Agent sizes work appropriately
✅ **Package managers** - Agent knows how to install things
✅ **Capabilities** - Agent knows about sudo, version control

### Lower Priority (Future)
- Performance tracking
- Error pattern analysis
- Permission analysis

---

## Example Impact

### Before Enhancement
```
User: "Analyze this 2GB CSV file"
Agent: Tries to load entire file into pandas → OutOfMemoryError
Agent: Has no context, retries same approach
Result: Failure
```

### After Enhancement
```
User: "Analyze this 2GB CSV file"
Agent: Calls get_context, sees max_memory_mb: 512
Agent: Uses chunked processing or pandas with chunks=50000
Agent: Succeeds with appropriate approach
Result: Success ✅
```

---

## Implementation Phases

### Phase 1: Quick Wins (45 minutes)
- [ ] Tool availability: `tools.available` ← list(TOOLS.keys())
- [ ] Sandbox config: `tools.sandboxed.*` ← environment variables
- [ ] Git context: `repository.*` ← already gathered in system_info!
- [ ] Exit codes: `activity.last_command_exit_code` ← track in ShellIntegration
- [ ] Interpreters: `capabilities.interpreters_available` ← shutil.which()

### Phase 2: Context Enhancement (20 minutes)
- [ ] System metrics: `system.*` ← existing get_system_info()
- [ ] Package managers: `capabilities.package_managers` ← check which exist
- [ ] Isolation config: `tools.isolation.*` ← environment variables

### Phase 3: Smart Features (Future)
- [ ] Performance tracking: `metrics.*`
- [ ] Error history: `activity.errors.*`
- [ ] Resource tracking: `metrics.resource_usage`

---

## Key Files

| Component | File | Change |
|-----------|------|--------|
| **Main tool** | `tools.py` | GetContextTool class (~40 lines added) |
| **Shell tracking** | `shell_integration.py` | Add command history (10 lines) |
| **System info** | Already exists | Just expose existing data |
| **Agent prompt** | `agent.py` | Document new context fields (5 lines) |

---

## Expected Output

```json
{
  "working_dir": "/home/user/ai-terminal-wd",
  "shell_cwd": "/home/user/ai-terminal-wd",
  
  "tools": {
    "available": ["read_file", "write_file", "run_command", "run_python_sandbox", ...],
    "sandboxed": {
      "enabled": true,
      "timeout_seconds": 30,
      "max_memory_mb": 1024,
      "network_disabled": true,
      "write_protected": false
    },
    "isolation": {
      "enabled": false,
      "rootfs_sha256": null
    }
  },
  
  "repository": {
    "in_git_repo": true,
    "branch": "feature/kimi2-agent-support",
    "repo_name": "ai-terminal",
    "uncommitted_changes_count": 3,
    "is_dirty": true
  },
  
  "capabilities": {
    "interpreters_available": {
      "python3": "/usr/bin/python3",
      "node": "/usr/bin/node",
      "bash": "/bin/bash"
    },
    "package_managers": ["pip", "apt", "npm"],
    "has_sudo": false
  },
  
  "system": {
    "os": "Linux",
    "kernel": "5.15.0-56-generic",
    "cpu_cores": 8,
    "memory_total_mb": 16384,
    "memory_available_mb": 8192,
    "disk_available_gb": 150.5,
    "python_version": "3.11.0"
  },
  
  "activity": {
    "recent_writes": ["output.json", "results.csv"],
    "recent_commands": [
      {"command": "ls -la", "exit_code": 0},
      {"command": "python script.py", "exit_code": 0}
    ],
    "last_command_exit_code": 0,
    "last_command": "python script.py"
  }
}
```

---

## Agent System Prompt Addition

Add to system prompt:
```
Context Awareness:
- Call get_context() to check tool availability, resource limits, and system state
- Respect sandbox limits (memory, timeout) by breaking work into smaller batches
- Check git status before making changes to ensure you're on the right branch
- Select interpreters based on availability; don't assume Python/Node/Ruby
- Check last_command_exit_code to understand if previous operations succeeded
- Use capabilities to inform decisions (e.g., "npm available, use Node.js")
```

---

## Benefits Summary

### For Agents
- ✅ Smarter tool selection
- ✅ Resource-aware execution
- ✅ Context-aware decisions
- ✅ Better error understanding
- ✅ Proactive constraint awareness

### For Users
- ✅ Fewer unexpected failures
- ✅ Better error messages
- ✅ Faster problem-solving
- ✅ More reliable automation

### For Development
- ✅ Better debugging (see what agent sees)
- ✅ Easier monitoring
- ✅ Pattern detection
- ✅ Performance insights

---

## Why This Works

### 1. **Low Implementation Cost**
- 75 minutes total work
- Most data already gathered
- Simple to integrate
- No breaking changes

### 2. **High Agent Value**
- Enables smarter decisions
- Prevents resource errors
- Improves context awareness
- Better debugging

### 3. **Easy to Extend**
- Additive structure
- No breaking changes
- Can add more fields over time
- Backward compatible

### 4. **Data Already Exists**
- System info already collected (system_info.py)
- Git info already collected (git_info())
- Tool schemas already available
- Just need to expose and format

---

## Comparison: Before vs After

| Capability | Before | After |
|---|---|---|
| Agent knows available tools? | ❌ | ✅ |
| Agent respects sandbox limits? | ❌ | ✅ |
| Agent aware of git state? | ❌ | ✅ |
| Agent knows exit codes? | ❌ | ✅ |
| Agent picks right language? | ❌ | ✅ |
| Agent plans for resources? | ❌ | ✅ |
| Agent provides context hints? | ❌ | ✅ |

---

## Next Steps

1. **Read the full analysis**: `history/ENHANCED_GET_CONTEXT_ANALYSIS.md`
2. **Review quick reference**: `history/GET_CONTEXT_QUICK_REFERENCE.md`
3. **Follow implementation guide**: `history/IMPLEMENTATION_GUIDE.md`
4. **Start Phase 1** (45 minutes for big gains)
5. **Test and iterate**

---

## Questions to Consider

- **Q**: Will this slow down the agent?
- **A**: No, adds ~5-10ms per call, minimal impact

- **Q**: Will agents use this information?
- **A**: Yes, if documented in system prompt with clear use cases

- **Q**: Can we add more context later?
- **A**: Yes, fully extensible with new fields

- **Q**: Does this break existing code?
- **A**: No, all changes are additive

---

## Key Insight

Your AI agent is currently **flying blind**, making decisions without understanding:
- Its capabilities
- Its constraints
- Its environment
- Its recent history

By exposing this context, you enable **smarter, context-aware automation** that:
- Respects limits
- Makes better decisions
- Recovers from failures
- Understands the bigger picture

This is a **force multiplier** for agent intelligence without adding complexity.

---

**Start with Phase 1 - you'll see immediate benefits in just 45 minutes of work!**
