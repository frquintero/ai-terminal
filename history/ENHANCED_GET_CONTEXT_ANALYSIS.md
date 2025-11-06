# Enhanced get_context Tool - Analysis & Recommendations

## Current State

The `get_context` tool currently returns:
```json
{
  "working_dir": "absolute_path_to_ai-terminal-wd",
  "shell_cwd": "current_shell_working_directory", 
  "recent_writes": ["file1.txt", "file2.py", ...]
}
```

This is **useful but incomplete** for an AI agent trying to understand its execution environment.

---

## Missing Context Information for AI Coding

### 1. **Tool Availability & State**
The agent doesn't know:
- Which tools are available (though it gets schemas, no quick reference)
- Tool status/limitations (e.g., "sandbox disabled", "isolation enabled")
- Tool-specific configuration (sandbox timeouts, limits)

**Value**: Agents could make smarter tool choices and avoid tools that won't work

### 2. **Environment Configuration**
Currently system info is only in system prompt at startup. Agent doesn't know:
- Current Python version & environment
- Sandbox configuration (enabled/disabled, limits)
- Namespace isolation status
- Available interpreters (python, node, ruby, etc.)

**Value**: Agents can validate code before execution and provide early warnings

### 3. **Recent Activity Context**
Only recent writes tracked, missing:
- Recently read files (understand what agent just analyzed)
- Recently executed commands (understand what just ran, relevant for debugging)
- Last command exit codes/success status
- Command execution timeline (when things happened)

**Value**: Better conversation continuity; agents understand context within multi-step operations

### 4. **Project/Repository Context**
Currently gathered at startup (system_info.py), not available to agent:
- Git repository info (branch, repo name, uncommitted changes)
- Project structure hints
- Package manager availability (pip, poetry, npm, etc.)

**Value**: Agents can make context-aware decisions (e.g., "create virtual env" vs "already has one")

### 5. **File System State**
No quick way to know:
- Filesystem capacity/usage
- Key directories existence/size
- Permission issues
- Sandboxing constraints

**Value**: Agents prevent errors like "disk full", understand read-only directories

### 6. **Performance Metrics & Constraints**
Agent unaware of:
- Active resource limits (memory, CPU time)
- Previous tool execution times
- Performance characteristics (slow/fast)
- Timeout configurations

**Value**: Agents can break work into smaller chunks to respect limits

### 7. **Error History**
No persistent record of:
- Previous tool failures
- Common error patterns
- Failed command categories

**Value**: Agents learn what works vs what doesn't in current environment

---

## Proposed Enhanced get_context Structure

```json
{
  "execution": {
    "working_dir": "string",
    "shell_cwd": "string",
    "home_dir": "string",
    "user": "string"
  },
  
  "environment": {
    "python_version": "string",
    "python_path": "string",
    "shell": "string",
    "locale": "string"
  },
  
  "tools": {
    "available": ["read_file", "write_file", "run_command", ...],
    "sandboxed": {
      "enabled": "boolean",
      "timeout_seconds": "integer",
      "max_memory_mb": "integer",
      "max_cpu_seconds": "integer",
      "network_disabled": "boolean",
      "write_protected": "boolean"
    },
    "isolation": {
      "enabled": "boolean",
      "rootfs_sha256": "string (optional)",
      "container_runtime": "string (bwrap/nix/etc)"
    }
  },
  
  "system": {
    "os": "string",
    "kernel": "string (Linux only)",
    "cpu_cores": "integer",
    "memory_total_mb": "integer",
    "memory_available_mb": "integer",
    "disk_available_gb": "float",
    "distro": "string (Linux)"
  },
  
  "repository": {
    "in_git_repo": "boolean",
    "repo_root": "string",
    "repo_name": "string",
    "branch": "string",
    "commit_short": "string",
    "origin_url": "string",
    "uncommitted_changes_count": "integer",
    "is_dirty": "boolean"
  },
  
  "activity": {
    "recent_writes": ["file1", "file2", ...],
    "recent_commands": [
      {
        "command": "string",
        "timestamp": "ISO8601",
        "exit_code": "integer",
        "duration_ms": "integer"
      }
    ],
    "last_command_exit_code": "integer or null",
    "session_tool_calls_count": "integer"
  },
  
  "capabilities": {
    "interpreters_available": {
      "python": "path_or_null",
      "node": "path_or_null",
      "ruby": "path_or_null",
      "bash": "path_or_null",
      "perl": "path_or_null"
    },
    "package_managers": ["pip", "npm", "apt", "brew"],
    "version_control": ["git", "hg"],
    "has_sudo": "boolean",
    "interactive_shell_available": "boolean"
  },
  
  "constraints": {
    "namespace_isolation_required": "boolean",
    "network_isolation": "boolean",
    "project_write_protection": "boolean",
    "file_size_limit_mb": "integer"
  }
}
```

---

## Implementation Strategy

### Phase 1: Essential Additions (High Value)
1. **Tool status** - Which tools are actually working now?
2. **Sandbox config** - Current limits and state
3. **Repository info** - Git context already gathered, expose it
4. **Recent commands** - Track and expose what just executed

### Phase 2: Context Enhancement
5. **Capabilities** - Available interpreters and tools
6. **System metrics** - CPU cores, memory (already gathered in system_info)
7. **Activity timeline** - When things happened

### Phase 3: Smart Features
8. **Constraints** - What limitations apply?
9. **Error history** - Pattern recognition
10. **Performance metrics** - Track execution speed

---

## Implementation Details

### Where to Track Recent Commands

**Option A: In ShellIntegration class**
```python
class ShellIntegration:
    def __init__(self, working_dir: str = None):
        self._command_history = deque(maxlen=20)  # Track last 20 commands
        self._last_exit_code = None
    
    def run_command(self, command: str, ...):
        # ... execute ...
        self._command_history.append({
            "command": command,
            "exit_code": returncode,
            "duration_ms": elapsed_time_ms,
            "timestamp": datetime.now().isoformat()
        })
        self._last_exit_code = returncode
```

**Option B: Separate CommandHistory class**
- Cleaner separation of concerns
- Can be accessed independently
- Thread-safe with locks if needed

### Where to Expose Context

**In GetContextTool.execute():**
```python
def execute(self) -> str:
    context = {
        "execution": {
            "working_dir": _get_working_dir_path(),
            "shell_cwd": self.shell.get_current_dir(),
            "home_dir": os.path.expanduser("~"),
            "user": os.environ.get("USER", "unknown")
        },
        
        "environment": {
            "python_version": self._get_python_info(),
            "shell": os.environ.get("SHELL"),
            ...
        },
        
        "tools": {
            "available": list(TOOLS.keys()),
            "sandboxed": {
                "enabled": os.getenv("SANDBOX_PYTHON") is not None,
                "timeout_seconds": int(os.getenv("SANDBOX_TIMEOUT", "30")),
                ...
            },
            "isolation": {
                "enabled": os.getenv("SANDBOX_ENABLE_ISOLATION") == "1",
                ...
            }
        },
        
        # ... rest of context ...
    }
    
    return json.dumps(context, indent=2)
```

### Helper Methods to Add

```python
def _get_python_info(self) -> dict:
    """Get Python version and path"""
    # Already available: sys.version, sys.executable
    pass

def _get_system_metrics(self) -> dict:
    """Get CPU cores, memory, disk from system_info module"""
    # Use existing get_system_info() and parse results
    pass

def _get_git_context(self) -> dict:
    """Get git repository info"""
    # Access existing git_info from system_info module
    pass

def _get_tool_status(self) -> dict:
    """Check which tools are functional"""
    # Validate sandbox, isolation, etc.
    pass

def _get_recent_commands(self) -> list:
    """Get command history from ShellIntegration"""
    # Access shell._command_history
    pass
```

---

## Benefits for AI Agent Coding

### Decision Making
- **Interpreter choice**: "Use Python" vs "Use Node" based on availability
- **Tool selection**: Skip sandbox if disabled, don't try isolation if not available
- **Performance**: Break work into chunks based on memory available
- **Dependencies**: Know if package managers exist before trying to install

### Error Prevention
- **Resource awareness**: Don't try long-running operations if timeout is short
- **Permission handling**: Know write-protected vs writable directories
- **Network detection**: Know if network calls will fail before trying

### Context Continuity
- **What just happened**: See recent commands to understand state
- **Success tracking**: Know exit codes of previous attempts
- **Activity timeline**: Understand what ran when for debugging

### Proactive Assistance
- **Configuration warnings**: "Sandbox disabled—runtime will be unsafe"
- **Limit reminders**: "Memory limit is 512MB, consider smaller batches"
- **Path helpers**: "No pip found, use apt to install Python packages"

---

## Backwards Compatibility

The enhanced `get_context` maintains the original simple response:
```json
{
  "working_dir": "...",
  "shell_cwd": "...",
  "recent_writes": [...]
}
```

New fields are **additive**, so:
- Existing agent implementations continue working
- New agents can use enriched context
- Optional fields can be added without breaking changes

---

## Priority Ranking

**Must Have (Session 1):**
1. ✅ Tool availability list
2. ✅ Sandbox enabled/disabled + config
3. ✅ Git repository context
4. ✅ Last command exit code

**Should Have (Session 2):**
5. Available interpreters
6. System metrics (cores, memory)
7. Recent command history
8. Package managers available

**Nice to Have (Session 3+):**
9. Performance tracking
10. Error pattern analysis
11. File system constraints
12. Permission analysis

---

## Code Example: Core Implementation

```python
# In tools.py - GetContextTool.execute()

def execute(self) -> str:
    """Return enriched execution context as JSON"""
    import subprocess
    from pathlib import Path
    from utils.system_info import (
        get_system_info, get_git_info, get_command_output
    )
    
    # Gather all context
    working_dir = _get_working_dir_path()
    
    # Get system info (cached if available)
    system_info = get_system_info()
    git_info = get_git_info()
    
    # Build context object
    context = {
        "execution": {
            "working_dir": working_dir,
            "shell_cwd": self.shell.get_current_dir() if self.shell else None,
            "home_dir": os.path.expanduser("~"),
            "user": os.environ.get("USER", "unknown")
        },
        
        "environment": {
            "python_version": platform.python_version(),
            "python_path": sys.executable,
            "shell": os.environ.get("SHELL", "unknown"),
        },
        
        "tools": {
            "available": sorted(list(TOOLS.keys())),
            "sandboxed": {
                "enabled": bool(os.getenv("SANDBOX_PYTHON")),
                "timeout_seconds": int(os.getenv("SANDBOX_TIMEOUT", "30")),
                "max_memory_mb": int(os.getenv("SANDBOX_MAX_MEM_MB", "1024")),
                "max_cpu_seconds": int(os.getenv("SANDBOX_MAX_CPU_SEC", "20")),
                "network_disabled": os.getenv("SANDBOX_DISABLE_NETWORK", "1") == "1",
                "write_protected": os.getenv("SANDBOX_ALLOW_PROJECT_WRITES", "0") == "0"
            },
            "isolation": {
                "enabled": os.getenv("SANDBOX_ENABLE_ISOLATION") == "1",
                "rootfs_sha256": os.getenv("SANDBOX_ROOTFS_SHA256"),
                "container_runtime": "bubblewrap" if os.getenv("SANDBOX_ENABLE_ISOLATION") == "1" else None
            }
        },
        
        "system": {
            "os": system_info.get("os"),
            "kernel": system_info.get("kernel"),
            "cpu_cores": int(system_info.get("cpu_cores", 0)) or None,
            "memory_total_mb": _parse_memory_to_mb(system_info.get("memory_total")),
            "memory_available_mb": _parse_memory_to_mb(system_info.get("memory_available")),
            "distro": system_info.get("distribution"),
        },
        
        "repository": {
            "in_git_repo": bool(git_info),
            "repo_root": git_info.get("repo_root"),
            "repo_name": git_info.get("repo_name"),
            "branch": git_info.get("branch"),
            "commit_short": git_info.get("commit"),
            "origin_url": git_info.get("origin"),
            "uncommitted_changes_count": int(git_info.get("uncommitted_changes", 0)),
            "is_dirty": bool(git_info.get("uncommitted_changes"))
        },
        
        "activity": {
            "recent_writes": list(_RECENT_WRITES)[-10:],  # Last 10
            "recent_commands": self._get_recent_commands(),
            "last_command_exit_code": self.shell._last_exit_code if self.shell else None,
            "session_tool_calls_count": getattr(self, '_tool_calls_count', 0)
        },
        
        "capabilities": {
            "interpreters_available": {
                "python": shutil.which("python3") or shutil.which("python"),
                "node": shutil.which("node"),
                "ruby": shutil.which("ruby"),
                "bash": shutil.which("bash"),
                "perl": shutil.which("perl")
            },
            "package_managers": [
                pm for pm in ["pip", "npm", "apt", "brew"]
                if shutil.which(pm)
            ],
            "version_control": [
                vc for vc in ["git", "hg"]
                if shutil.which(vc)
            ],
            "has_sudo": self._check_sudo_access(),
            "interactive_shell_available": sys.stdin.isatty()
        }
    }
    
    return json.dumps(context, indent=2)

def _get_recent_commands(self) -> list:
    """Get recent command history"""
    if self.shell and hasattr(self.shell, '_command_history'):
        return [
            {
                "command": cmd.get("command"),
                "exit_code": cmd.get("exit_code"),
                "duration_ms": cmd.get("duration_ms")
            }
            for cmd in list(self.shell._command_history)[-5:]
        ]
    return []

def _check_sudo_access(self) -> bool:
    """Check if sudo is available and accessible"""
    result = subprocess.run(
        ["sudo", "-n", "true"],
        capture_output=True,
        timeout=1
    )
    return result.returncode == 0

def _parse_memory_to_mb(mem_str: str) -> int:
    """Parse memory string like '16G', '512M' to MB"""
    if not mem_str:
        return None
    mem_str = mem_str.strip().upper()
    try:
        if 'G' in mem_str:
            return int(float(mem_str.replace('G', '')) * 1024)
        elif 'M' in mem_str:
            return int(float(mem_str.replace('M', '')))
        elif 'K' in mem_str:
            return int(float(mem_str.replace('K', '')) / 1024)
    except:
        pass
    return None
```

---

## Recommendations

### Start With:
1. **Add `tools.available`** - 5 min, high value
2. **Add sandbox config** - 10 min, critical for agent decisions
3. **Add git context** - 5 min (already have the data!)
4. **Add last exit code** - 5 min, helps debugging
5. **Add interpreters** - 10 min, enables smart tool selection

### Then Add:
6. System metrics (already gathered)
7. Recent command history (requires ShellIntegration changes)
8. Package manager detection

### Low Priority:
9. Error pattern tracking
10. Performance analytics

---

## Summary

The current `get_context` is a good foundation but **misses critical context** for AI agents to make smart decisions. The enhanced version proposed here:

- ✅ Keeps backward compatibility
- ✅ Uses existing data already gathered (system_info, git_info)
- ✅ Enables smarter tool selection
- ✅ Prevents errors by exposing constraints
- ✅ Improves debugging with activity history
- ✅ 80% of value from first 5 additions

**Recommended approach**: Implement in stages, starting with tool availability, sandbox config, git context, and exit codes.
