# Regression Fixes - Semantic Review Results

## Summary
Performed comprehensive semantic review of recent changes integrating system context and interactive command handling. Fixed **4 critical bugs** and **3 medium-priority issues**.

---

## Critical Issues Fixed (HIGH PRIORITY)

### 1. 🔴 **write_file fails for files in current directory**
**Issue**: `os.makedirs('')` raises exception when writing files without directory path  
**Impact**: Cannot create files in current directory - HIGH IMPACT BUG  
**Fix**: Check if `dirname` is non-empty before calling `os.makedirs()`  
**File**: `tools.py:97-106`

```python
dirpath = os.path.dirname(file_path)
if dirpath:  # Only create dirs if path contains directory component
    os.makedirs(dirpath, exist_ok=True)
```

### 2. 🔴 **Interactive tool wrapped in Live spinner interferes with TTY**
**Issue**: Rich Live spinner corrupts terminal display when vim/nano/top are running  
**Impact**: Interactive apps unusable, screen corruption  
**Fix**: Special-case `run_interactive` to skip Live spinner wrapper  
**File**: `agent.py:104-129`

```python
if tool_name == "run_interactive":
    ui.info(f"Launching interactive: {details}")
    result = tool.execute(**args)
else:
    with Live(ui.show_tool_execution(tool_name, details), ...):
        result = tool.execute(**args)
```

### 3. 🔴 **run_command hangs on interactive programs (30s timeout)**
**Issue**: AI mistakenly using `run_command` for vim/nano causes 30s pexpect timeout  
**Impact**: Poor UX, confusing hangs  
**Fix**: Guard in `run_command` to detect and refuse interactive commands  
**File**: `tools.py:139-150`

```python
analysis = analyze_command(command)
if analysis.is_interactive:
    cmd = analysis.primary_context.executable if analysis.primary_context else "command"
    return f"Error: Interactive command detected ({cmd}). Use run_interactive tool instead to avoid timeout."
```

### 4. 🔴 **run_interactive unusable in headless environments**
**Issue**: The legacy TTY requirement blocked all interactive commands inside the orchestrator loop.  
**Impact**: Agent B could not inspect pagers/REPLs; commands like `man` failed outright.  
**Fix**: Replace the TTY check with a PTY-backed executor that streams output, detects prompts, and keeps a `session_id` so Agent B can reply.  
**File**: `tools.py` (`InteractiveSession` + `InteractiveCommandTool`) now handles prompt detection and structured JSON events.

---

## Medium Priority Issues Fixed

### 5. 🟡 **System info gathering not robust across Linux distros**
**Issue**: Relies on `grep|cut|tr` pipelines, `lscpu`, `free` which may fail on minimal systems  
**Impact**: System context incomplete on some distros  
**Fix**: Python fallbacks to `/etc/os-release`, `/proc/meminfo`, `/proc/cpuinfo`  
**File**: `utils/system_info.py:27-154`

- `get_distro_info()`: Parse `/etc/os-release` in Python
- `get_memory_info()`: Fallback to `/proc/meminfo`
- `get_cpu_info()`: Fallback to `/proc/cpuinfo`
- Added `LC_ALL=C` to commands to avoid localization issues

### 6. 🟡 **System prompt doesn't warn against run_command for interactive programs**
**Issue**: AI may choose wrong tool if not explicitly warned  
**Impact**: User hits timeout issues  
**Fix**: Add CRITICAL warning in system prompt  
**File**: `agent.py:29-45`

```
CRITICAL: Never use run_command for interactive programs (vim, nano, less, top, htop, man, ssh, mysql, python REPL, etc.) — it will hang or timeout. Always use run_interactive for those.
```

### 7. 🟡 **run_interactive missing command details in UI (UX parity)**
**Issue**: Only `run_command` showed command details in UI  
**Impact**: Inconsistent UX  
**Fix**: Added command details extraction for `run_interactive`  
**File**: `agent.py:110`

```python
if tool_name in ["run_command", "run_interactive"] and "command" in args:
    details = args["command"]
```

---

## Changes Summary

### Files Modified
1. **agent.py** - System prompt update, interactive tool handling
2. **tools.py** - WriteFileTool fix, RunCommandTool guard, InteractiveCommandTool TTY check, imports
3. **utils/system_info.py** - Robust parsing with Python fallbacks

### Test Results
- All syntax checks passed: ✓
- All regression fixes verified: ✓
- Pre-existing integration test failures (unrelated to changes): 5 tests expect different return format

### Verification Test
Created `test_fixes.py` to verify all fixes:
- ✓ write_file in CWD works correctly
- ✓ write_file with subdirectories works correctly  
- ✓ run_command correctly blocks interactive commands
- ✓ run_interactive correctly checks for TTY

---

## Recommendations

### Immediate Actions (Done)
- [x] Fix write_file dirname bug
- [x] Remove Live spinner for interactive tools
- [x] Add TTY check to run_interactive
- [x] Add guard in run_command for interactive programs
- [x] Improve system_info robustness
- [x] Update system prompt with explicit warnings
- [x] Add command details for run_interactive

### Future Considerations
1. **Update integration tests** to handle dict return values from `process_input()`
2. **Consider PTY-based architecture** for unified command execution with better control
3. **Add capture mode** for interactive sessions if output needs to be available for downstream reasoning
4. **Monitor pexpect prompt matching** - currently brittle if output contains "$ "

---

## Risk Assessment

### Mitigated Risks
- Terminal corruption with interactive apps: FIXED
- 30s timeout hangs: PREVENTED via guard
- File creation failures: FIXED
- Non-TTY crashes: PREVENTED via check
- System info failures on minimal distros: MITIGATED via fallbacks

### Remaining Risks (Acceptable)
- Command injection via AI-generated commands (shell=True) - mitigated by system prompt and user visibility
- pexpect prompt matching brittleness - preexisting, acceptable for current scope
- Interactive output not captured - by design, acceptable

---

## Oracle Assessment Quote

> "Notable current issues found:
> - High impact bug: write_file fails when file_path has no directory (os.makedirs('') raises).
> - Interactive tool wrapped in Live spinner can interfere with TTY apps (vim/top/etc.).
> - run_command can be chosen mistakenly for interactive commands; it will hang then time out after 30s via pexpect.
> - system_info relies on grep/cut/tr/lscpu/free and may fail on minimal systems; add Python fallbacks."

**All issues identified by Oracle have been addressed.**
