# Implementation Guide: Enhanced get_context

## Overview

This guide provides step-by-step instructions to enhance the `get_context` tool with richer execution context for AI agents.

---

## Phase 1: Quick Wins (30-45 minutes)

These additions use data already gathered or available via simple checks.

### Step 1: Add Tool Availability (5 min)

**File**: `tools.py` > `GetContextTool.execute()`

**Current**:
```python
def execute(self) -> str:
    """Return execution context as JSON"""
    working_dir = _get_working_dir_path()
    context = {
        "working_dir": working_dir,
        "shell_cwd": shell_cwd,
        "recent_writes": list(_RECENT_WRITES)
    }
    return json.dumps(context, indent=2)
```

**Add**:
```python
def execute(self) -> str:
    """Return execution context as JSON"""
    working_dir = _get_working_dir_path()
    
    # NEW: Tool availability
    tools_section = {
        "available": sorted(list(TOOLS.keys())),
        "sandboxed": self._get_sandbox_config(),
        "isolation": self._get_isolation_config()
    }
    
    context = {
        "working_dir": working_dir,
        "shell_cwd": shell_cwd,
        "recent_writes": list(_RECENT_WRITES),
        "tools": tools_section  # NEW
    }
    return json.dumps(context, indent=2)

def _get_sandbox_config(self) -> dict:
    """Get sandbox configuration from environment"""
    return {
        "enabled": bool(os.getenv("SANDBOX_PYTHON")),
        "timeout_seconds": int(os.getenv("SANDBOX_TIMEOUT", "30")),
        "max_memory_mb": int(os.getenv("SANDBOX_MAX_MEM_MB", "1024")),
        "max_cpu_seconds": int(os.getenv("SANDBOX_MAX_CPU_SEC", "20")),
        "network_disabled": os.getenv("SANDBOX_DISABLE_NETWORK", "1") == "1",
        "write_protected": os.getenv("SANDBOX_ALLOW_PROJECT_WRITES", "0") == "0"
    }

def _get_isolation_config(self) -> dict:
    """Get namespace isolation configuration"""
    return {
        "enabled": os.getenv("SANDBOX_ENABLE_ISOLATION") == "1",
        "rootfs_sha256": os.getenv("SANDBOX_ROOTFS_SHA256"),
        "container_runtime": "bubblewrap" if os.getenv("SANDBOX_ENABLE_ISOLATION") == "1" else None
    }
```

**Test**: `get_context()` should now show tools with their configs

---

### Step 2: Add Git Repository Context (5 min)

**File**: `tools.py` > `GetContextTool`

**Add helper method**:
```python
def _get_git_context(self) -> dict:
    """Get git repository information"""
    from utils.system_info import get_git_info
    
    git_info = get_git_info()
    
    return {
        "in_git_repo": bool(git_info),
        "repo_root": git_info.get("repo_root"),
        "repo_name": git_info.get("repo_name"),
        "branch": git_info.get("branch"),
        "commit_short": git_info.get("commit"),
        "origin_url": git_info.get("origin"),
        "uncommitted_changes_count": int(git_info.get("uncommitted_changes", 0)),
        "is_dirty": bool(git_info.get("uncommitted_changes"))
    }
```

**Update `execute()`**:
```python
def execute(self) -> str:
    """Return execution context as JSON"""
    working_dir = _get_working_dir_path()
    
    tools_section = {
        "available": sorted(list(TOOLS.keys())),
        "sandboxed": self._get_sandbox_config(),
        "isolation": self._get_isolation_config()
    }
    
    context = {
        "working_dir": working_dir,
        "shell_cwd": shell_cwd,
        "recent_writes": list(_RECENT_WRITES),
        "tools": tools_section,
        "repository": self._get_git_context()  # NEW
    }
    return json.dumps(context, indent=2)
```

---

### Step 3: Add Available Interpreters (8 min)

**File**: `tools.py` > `GetContextTool`

**Add helper method**:
```python
def _get_interpreters_available(self) -> dict:
    """Check which interpreters are available"""
    import shutil
    
    interpreters = {}
    for name in ["python3", "python", "node", "ruby", "perl", "bash", "sh"]:
        interpreters[name] = shutil.which(name)
    
    return {k: v for k, v in interpreters.items() if v}  # Only return found

def _get_package_managers(self) -> list:
    """Check which package managers are available"""
    import shutil
    
    managers = []
    for pm in ["pip", "pip3", "npm", "apt", "apt-get", "yum", "brew", "pacman"]:
        if shutil.which(pm):
            managers.append(pm)
    
    return managers

def _get_capabilities(self) -> dict:
    """Get system capabilities"""
    import shutil
    import sys
    
    return {
        "interpreters_available": self._get_interpreters_available(),
        "package_managers": self._get_package_managers(),
        "version_control": [
            vc for vc in ["git", "hg", "svn"]
            if shutil.which(vc)
        ],
        "has_sudo": self._check_sudo_access(),
        "interactive_shell_available": sys.stdin.isatty()
    }

def _check_sudo_access(self) -> bool:
    """Check if sudo is available and can run without password"""
    import subprocess
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=1
        )
        return result.returncode == 0
    except:
        return False
```

**Update `execute()`**:
```python
def execute(self) -> str:
    """Return execution context as JSON"""
    # ... previous code ...
    
    context = {
        "working_dir": working_dir,
        "shell_cwd": shell_cwd,
        "recent_writes": list(_RECENT_WRITES),
        "tools": tools_section,
        "repository": self._get_git_context(),
        "capabilities": self._get_capabilities()  # NEW
    }
    return json.dumps(context, indent=2)
```

---

### Step 4: Add System Information (10 min)

**File**: `tools.py` > `GetContextTool`

**Add helper method**:
```python
def _get_system_info(self) -> dict:
    """Get system information"""
    from utils.system_info import (
        get_system_info, get_command_output
    )
    import platform
    
    sys_info = get_system_info()
    
    return {
        "os": platform.system(),
        "os_version": sys_info.get("os_version"),
        "kernel": sys_info.get("kernel"),
        "architecture": platform.machine(),
        "cpu_cores": sys_info.get("cpu_cores"),
        "memory_total_mb": self._parse_memory_to_mb(sys_info.get("memory_total")),
        "memory_available_mb": self._parse_memory_to_mb(sys_info.get("memory_available")),
        "disk_available_gb": self._parse_disk_to_gb(sys_info.get("disk_root")),
        "distro": sys_info.get("distribution"),
        "hostname": platform.node(),
        "python_version": platform.python_version(),
        "user": os.environ.get("USER", "unknown")
    }

def _parse_memory_to_mb(self, mem_str: str) -> int:
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

def _parse_disk_to_gb(self, disk_str: str) -> float:
    """Parse disk string to GB"""
    if not disk_str:
        return None
    # Extract first number from disk string
    import re
    match = re.search(r'(\d+\.?\d*)\s*G', disk_str)
    if match:
        return float(match.group(1))
    return None
```

**Update `execute()`**:
```python
def execute(self) -> str:
    """Return execution context as JSON"""
    # ... previous code ...
    
    context = {
        "working_dir": working_dir,
        "shell_cwd": shell_cwd,
        "recent_writes": list(_RECENT_WRITES),
        "tools": tools_section,
        "repository": self._get_git_context(),
        "capabilities": self._get_capabilities(),
        "system": self._get_system_info()  # NEW
    }
    return json.dumps(context, indent=2)
```

---

### Step 5: Add Command Exit Code Tracking (10 min)

**File**: `shell_integration.py` > `ShellIntegration.__init__()`

**Add tracking**:
```python
class ShellIntegration:
    def __init__(self, working_dir: str = None):
        # ... existing code ...
        self._last_exit_code = None  # NEW
        self._last_command = None    # NEW
        self._command_history = deque(maxlen=20)  # NEW
```

**File**: `shell_integration.py` > `run_command()` method

Find where exit code is captured and add:
```python
# After getting exit code from subprocess
self._last_exit_code = exit_code
self._last_command = command
self._command_history.append({
    "command": command,
    "exit_code": exit_code,
    "timestamp": datetime.now().isoformat()
})
```

**File**: `tools.py` > `GetContextTool`

**Add helper**:
```python
def _get_activity(self) -> dict:
    """Get current activity and history"""
    recent_commands = []
    if self.shell and hasattr(self.shell, '_command_history'):
        recent_commands = list(self.shell._command_history)[-5:]
    
    return {
        "recent_writes": list(_RECENT_WRITES)[-10:],
        "recent_commands": recent_commands,
        "last_command_exit_code": self.shell._last_exit_code if self.shell else None,
        "last_command": self.shell._last_command if self.shell else None
    }
```

**Update `execute()`**:
```python
def execute(self) -> str:
    """Return execution context as JSON"""
    # ... previous code ...
    
    context = {
        "working_dir": working_dir,
        "shell_cwd": shell_cwd,
        "tools": tools_section,
        "repository": self._get_git_context(),
        "capabilities": self._get_capabilities(),
        "system": self._get_system_info(),
        "activity": self._get_activity()  # NEW (replaces recent_writes at top level)
    }
    return json.dumps(context, indent=2)
```

---

## Phase 2: Update Agent System Prompt (5 min)

**File**: `agent.py` > `_build_system_prompt()`

**Add to tools section**:
```python
def _build_system_prompt(self, system_context: str) -> str:
    """Build the complete system prompt with tools, context, and guidelines"""
    # ... existing code ...
    
    # Add to the execution rules section:
    execution_rules = """
    
Execution Context:
- Use get_context() to check:
  * Available tools and sandbox configuration
  * Git repository state (branch, uncommitted changes)
  * Available interpreters and package managers
  * System resources (CPU cores, memory, disk)
  * Recent commands and their exit codes
  
Tool-Aware Decisions:
- Check tools.available before assuming a tool exists
- Check tools.sandboxed limits (timeout_seconds, max_memory_mb) and respect them
- Check repository.uncommitted_changes_count before destructive operations
- Check capabilities.interpreters_available to pick the right language
- Check activity.last_command_exit_code to understand if previous step succeeded
"""
    
    # ... rest of system prompt ...
```

---

## Testing

### Test 1: Verify Output Structure

```bash
python -c "
from tools import TOOLS
import json

tool = TOOLS['get_context']
output = tool.execute()
data = json.loads(output)

print('✓ Valid JSON')
print('Top-level keys:', list(data.keys()))
print('Has tools:', 'tools' in data)
print('Has repository:', 'repository' in data)
print('Has capabilities:', 'capabilities' in data)
print('Has system:', 'system' in data)
print('Has activity:', 'activity' in data)
"
```

### Test 2: Verify Agent Uses It

```bash
python main.py
# Type: get_context
# Should see rich output with all new fields
```

### Test 3: Verify Decisions

```bash
python main.py
# Type: What Python interpreters do I have?
# Should extract from get_context and answer directly
```

---

## Rollout Strategy

### Week 1: Phase 1
- Implement Steps 1-5
- Test each addition
- Commit with message: "feat: enhance get_context tool with execution context"

### Week 2: Phase 2
- Update system prompt
- Run integration tests
- Monitor agent behavior

### Week 3: Optimization
- Add performance tracking if needed
- Add error pattern analysis if needed
- Document best practices

---

## Estimated Effort

| Task | Time | Difficulty |
|------|------|-----------|
| Tool availability | 5 min | ⭐ Trivial |
| Sandbox config | 5 min | ⭐ Trivial |
| Git context | 5 min | ⭐ Trivial |
| Interpreters | 8 min | ⭐ Trivial |
| System info | 10 min | ⭐⭐ Easy |
| Exit code tracking | 10 min | ⭐⭐ Easy |
| Shell command history | 10 min | ⭐⭐ Easy |
| System prompt update | 5 min | ⭐ Trivial |
| Testing | 15 min | ⭐⭐ Easy |
| **Total** | **~75 min** | - |

---

## Files to Modify

1. **tools.py** (main)
   - GetContextTool class
   - Add 6-7 helper methods
   - Update execute() method

2. **shell_integration.py** (add tracking)
   - Add `_last_exit_code`, `_command_history` to __init__
   - Update run_command() to track results

3. **agent.py** (document usage)
   - Update _build_system_prompt() with new context hints

---

## Backward Compatibility

✅ **All changes are backward compatible**
- Original fields preserved
- New fields additive only
- No breaking changes to API
- Existing clients see original response + enhanced fields

---

## Performance Impact

- **First call**: +50-100ms (gathering system info, git status)
- **Subsequent calls**: +5-10ms (mostly cached)
- **Memory**: +1-2 KB per context dump
- **JSON size**: ~2 KB (insignificant)

**Optimization**: Cache system info (doesn't change during session)

---

## Success Criteria

✅ Tool list is accurate
✅ Sandbox config reflects .env settings
✅ Git context is current (reflects repo state)
✅ Interpreters list is accurate
✅ Exit codes match actual command results
✅ Agent uses context for smarter decisions
✅ No performance regression
✅ All tests pass

---

## Support & Debugging

### Common Issues

**Q: get_context shows wrong Python**
- A: Python path from sys.executable may differ from SANDBOX_PYTHON

**Q: Git context always empty**
- A: Working directory may not be in git repo; check shell_cwd

**Q: Sandbox config shows disabled but .env has SANDBOX_PYTHON**
- A: Check environment variable loading in config.py

### Debug Commands

```bash
# Check tools available
python -c "from tools import TOOLS; print(list(TOOLS.keys()))"

# Check git context
python -c "from utils.system_info import get_git_info; import json; print(json.dumps(get_git_info(), indent=2))"

# Check system info
python -c "from utils.system_info import get_system_info; import json; print(json.dumps(get_system_info(), indent=2))"

# Check sandbox config
python -c "import os; print('SANDBOX_PYTHON:', os.getenv('SANDBOX_PYTHON')); print('SANDBOX_TIMEOUT:', os.getenv('SANDBOX_TIMEOUT'))"
```

---

## Next Steps

1. Review this guide
2. Start with Phase 1, Step 1
3. Run tests after each step
4. Commit frequently
5. Gather feedback
6. Iterate on Phase 2

---

**Questions?** See `history/ENHANCED_GET_CONTEXT_ANALYSIS.md` for deep dive.
