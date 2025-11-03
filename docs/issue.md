# Issue: Agent Hangs on Interactive Package Manager Commands and Sudo

## Summary
The AI terminal agent hangs indefinitely when users run package manager commands (like `yay -Syu` or `pacman -Syu`) that require interactive confirmation, or when using `sudo` commands that require password authentication.

## Bug Evidence
From database logs (session_id 2):
- **Entry 45**: User requested `yay -Syu`
- **Entry 46**: Agent called `run_command` tool with `yay -Syu`
- **Missing Entry 47**: No tool result was ever logged - command never returned
- **Entry 67** (later retry): Command with `--devel --timeupdate` timed out after 60s

## Root Causes

### 1. Package Manager Interactive Prompts
- Commands like `yay -Syu` and `pacman -Syu` require user confirmation (Y/n prompts)
- Current `RunCommandTool` only checks for known interactive commands (vim, nano, top, etc.)
- `yay` and `pacman` are NOT in the `INTERACTIVE_COMMANDS` list
- The agent sends the command and waits indefinitely for output that never comes
- Eventually times out after 60 seconds

### 2. Sudo Password Prompts
- `shell_integration.py` has a `run_sudo_command()` method (lines 250-340) that handles sudo password prompts
- However, NO tool is exposed for this functionality in `tools.py`
- When users try to run `sudo` commands via `run_command`, they hang waiting for password input
- The agent has no way to handle privileged operations properly

### 3. Missing Non-Interactive Flag Detection
- Package managers CAN be run non-interactively with flags like `--noconfirm`
- Current implementation doesn't distinguish between:
  - `yay -Syu` (interactive - hangs)
  - `yay -Syu --noconfirm` (non-interactive - should work)

## Proposed Solution

### Strategy
Add **smart guards** instead of blanket blocking - don't add yay/pacman to INTERACTIVE_COMMANDS since they can be non-interactive with proper flags.

### Implementation Plan

#### 1. Add Package Manager Guard in `RunCommandTool.execute`
- Detect `yay`/`pacman` commands with prompt-prone operations (S/U/R flags)
- If missing `--noconfirm`, return clear error with guidance
- If `--noconfirm` present, allow execution
- Error message example: 
  ```
  "Error: Package manager command 'yay' may prompt for confirmation. 
   Add --noconfirm to use run_command, or use run_interactive for manual control.
   If root is required, use run_sudo_command."
  ```

#### 2. Add Sudo Detection Guard in `RunCommandTool.execute`
- If command starts with `sudo` or `doas`, return error redirecting to `run_sudo_command` tool
- Prevents password prompt hangs
- Error message example:
  ```
  "Error: This command uses sudo. Use run_sudo_command to handle password prompts safely."
  ```

#### 3. Create New `SudoRunCommandTool`
- Expose the existing `ShellIntegration.run_sudo_command()` method as a proper tool
- Schema parameters:
  - `command` (string, required): The sudo command to execute
  - `password` (string, optional): Sudo password
  - `timeout` (integer, optional): Command timeout in seconds
- Include same package manager guard logic (check for --noconfirm)

#### 4. Update Tool Descriptions
- Update `run_command` description to clarify it's non-interactive only
- Add guidance about package managers requiring `--noconfirm` flag
- Add guidance about using `run_sudo_command` for sudo operations

#### 5. Create Comprehensive Tests
- Test `yay -Syu` without `--noconfirm` (should return error, not hang)
- Test `yay -Syu --noconfirm` (should execute)
- Test `pacman -Syu` without `--noconfirm` (should return error)
- Test `pacman -Syu --noconfirm` (should execute)
- Test `sudo pacman -Syu` via `run_command` (should return error directing to `run_sudo_command`)
- Test `run_sudo_command` with correct password
- Test `run_sudo_command` with incorrect password
- Test `run_sudo_command` with package manager requiring `--noconfirm`

## Benefits
- ✅ Prevents hangs with actionable error messages
- ✅ Allows non-interactive package manager use with `--noconfirm`
- ✅ Properly handles sudo commands with password prompts
- ✅ No breaking changes or complex abstractions
- ✅ Agent can auto-correct by following error guidance

## Files Modified
1. `tools.py` - Added guards and `SudoRunCommandTool`
2. `shell_integration.py` - Fixed sudo password prompt flow
3. `agent.py` - Added SecretStore, password injection, pause/resume
4. `main.py` - Added getpass password prompt handling
5. `tests/test_package_manager_sudo.py` - Comprehensive test suite

## Implementation Complete
**Architectural Solution:** Pause/Resume with SecretStore
- Agent pauses when sudo password needed
- Prompts user securely with getpass (hidden input)
- Caches password in-memory for session
- Auto-injects on subsequent sudo commands
- Never logs or sends passwords to LLM

## References
- Thread: T-0378a174-4d17-4193-898f-040f067a9cfa (database logging implementation)
- Oracle consultation: Confirmed analysis and recommended minimal fix approach
- Database logs: Session 2, entries 45-68
