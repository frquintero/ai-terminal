# Python Sandbox: Project File Access Feature

**Implementation Date:** November 3, 2025

## Overview

Enhanced the Python sandbox with configurable read/write access to the project directory. The sandbox now exposes the project directory via the `SANDBOX_PROJECT` environment variable with read-only access by default, preventing accidental modifications to project files.

## Implementation Summary

### 1. Core Changes to `tools.py` (RunPythonSandboxTool)

**Project Directory Mounting:**
- Captures the original working directory (`original_cwd`)
- Creates a symlink `project` inside the sandbox run directory pointing to the project
- Falls back to direct path if symlinks are not supported (e.g., Windows)

**Configurable Write Protection:**
- New environment variable: `SANDBOX_ALLOW_PROJECT_WRITES` (default: `0`)
- When disabled (default), monkey-patches Python's file I/O operations:
  - `builtins.open` - Blocks write modes ('w', 'a', 'x', '+')
  - `os.remove` - Blocks file deletion
  - `os.rename` - Blocks file/directory renaming
  - `shutil.rmtree` - Blocks directory deletion
- When enabled, project directory is fully writable (use with caution)

**Environment Variables:**
- `SANDBOX_ORIGINAL_CWD` - Absolute path to the original working directory
- `SANDBOX_PROJECT` - Path to the project directory mount (may be symlink or direct path)

**Output Enhancements:**
- Added "Project Mount" line showing the mount path and read-only status
- Example: `Project Mount: /path/to/project (Read-Only: True)`

### 2. Configuration Updates (`.env.example`)

Added new environment variable:
```bash
SANDBOX_ALLOW_PROJECT_WRITES=0  # Allow writing to project directory from sandbox (1=yes, 0=no, default: no for safety)
```

### 3. Agent Prompt Updates (`agent.py`)

Updated the system prompt to guide the AI agent:
- Instructs to use `os.environ['SANDBOX_PROJECT']` for accessing project files
- Example pattern: `pd.read_csv(os.path.join(os.environ['SANDBOX_PROJECT'], 'data.csv'))`

### 4. Documentation (`docs/sandbox_examples.md`)

**New Section: "Accessing Project Files"**
- Explains how to use `SANDBOX_PROJECT` environment variable
- Provides example of reading project CSV files with pandas
- Documents the read-only security model
- Warns about enabling write access

**Updated Configuration Section:**
- Added documentation for `SANDBOX_ALLOW_PROJECT_WRITES`
- Warning about security implications of enabling writes

### 5. Testing (`tests/test_sandbox.py`)

Added two comprehensive test cases:

**`test_project_file_read`:**
- Creates a test file in the project directory
- Verifies successful reading via `SANDBOX_PROJECT`
- Confirms the environment variable is set correctly

**`test_project_write_guard`:**
- Creates a protected file in the project directory
- Attempts to write to it with write protection enabled (default)
- Verifies `PermissionError` is raised
- Confirms the original file remains unchanged

**Test Results:** 14/14 passing (2 new tests, 12 existing)

## Security Model

### Read-Only by Default

The project directory is mounted as **read-only by default** to prevent:
- Accidental file modifications
- Data loss from buggy sandbox code
- Unintended side effects during data analysis

### Protection Mechanism

Uses Python monkey-patching to intercept file system operations:
1. Resolves file paths to absolute paths using `os.path.realpath()`
2. Checks if the path is within or equal to the project directory
3. Raises `PermissionError` before executing write operations
4. Allows all other operations (reads, sandbox directory writes)

### When to Enable Writes

Set `SANDBOX_ALLOW_PROJECT_WRITES=1` when:
- You need sandbox code to generate files in the project
- You trust the code being executed
- You understand the risk of file modification/deletion

**Always use with caution!**

## Usage Examples

### Reading Project Files

```python
code = """
import os
import pandas as pd

# Access the project directory
project_dir = os.environ['SANDBOX_PROJECT']

# Read a CSV file from the project
csv_path = os.path.join(project_dir, 'data/sales.csv')
df = pd.read_csv(csv_path)

print(f"Loaded {len(df)} rows")
print(df.describe())
"""
```

### Safe by Default

```python
code = """
import os

project_dir = os.environ['SANDBOX_PROJECT']
file_path = os.path.join(project_dir, 'important.txt')

# This will raise PermissionError
with open(file_path, 'w') as f:
    f.write("This will fail!")
"""
# Result: PermissionError: Sandbox: write to project directory is blocked
```

### Enabling Writes (Advanced)

```bash
# In .env file
SANDBOX_ALLOW_PROJECT_WRITES=1
```

```python
code = """
import os

project_dir = os.environ['SANDBOX_PROJECT']
output_path = os.path.join(project_dir, 'results', 'output.csv')

# This will now work (writes enabled)
with open(output_path, 'w') as f:
    f.write("metric,value\\n1,100\\n2,200")
"""
```

## Architecture Decisions

### Oracle Consultation

This implementation was based on recommendations from the oracle, which suggested:
- Symlink-based project mount for cleaner separation
- Environment variable exposure for discoverability
- Configurable write policy with safe defaults
- Monkey-patching for write protection (simpler than chroot/namespaces)

### Trade-offs

**Chosen: Monkey-patching**
- ✅ Simple implementation
- ✅ No external dependencies
- ✅ Cross-platform compatible
- ✅ Configurable per-environment
- ⚠️ Can be bypassed by determined code (calls `os.unlink`, etc.)

**Not Chosen: Filesystem Namespaces/chroot**
- ❌ Linux-specific
- ❌ Requires root privileges
- ❌ More complex setup
- ✅ Stronger isolation

### Rationale

For local development workflows:
- Monkey-patching provides adequate protection against accidental modifications
- Not designed to protect against malicious code
- Simplicity and cross-platform support prioritized
- Users retain the option to enable writes when needed

## Integration

### Zero Breaking Changes

- Existing sandbox code continues to work unchanged
- Project access is opt-in (scripts don't need to use `SANDBOX_PROJECT`)
- Default behavior is maximally safe (read-only)

### Backward Compatibility

- All existing tests still pass
- No changes to tool schema or execute signature
- Environment variables are additive

## Verification

✅ All 14 unit tests passing  
✅ New features fully tested  
✅ No diagnostic errors  
✅ Documentation complete  
✅ Safe defaults enforced  

## Future Enhancements

Potential improvements for stronger isolation:
1. **Filesystem whitelisting** - Only expose specific project subdirectories
2. **Temporary read-only bind mounts** - OS-level read-only enforcement
3. **Copy-on-write snapshots** - Automatic rollback on errors
4. **Per-script write policies** - Fine-grained control via tool parameters

## Files Modified

1. `tools.py` - Core sandbox implementation
2. `.env.example` - Configuration template
3. `agent.py` - AI prompt guidance
4. `docs/sandbox_examples.md` - User documentation
5. `tests/test_sandbox.py` - Test coverage

## Commits

This feature can be committed as:
```
feat: Add configurable project directory access to Python sandbox

- Mount project directory at SANDBOX_PROJECT env var
- Read-only by default with monkey-patched write guards
- Configurable via SANDBOX_ALLOW_PROJECT_WRITES
- Add tests for file read and write protection
- Update docs and agent prompts
```
