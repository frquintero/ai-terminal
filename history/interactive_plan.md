# Interactive Execution Upgrade Plan

## 1. Diagnose Current Failure Modes
- **Issue**: Historically, commands like `man`, `less`, and REPLs were blocked by `run_command` as "interactive" while `run_interactive` required a TTY, leaving no functional path.
- **Objective**: Understand exactly where the pipeline drops interactive work and what signals Agent B receives today.
- **Approach**: Audit `command_parser` guards, ToolExecutor response payloads, and Agent B message flow to map the current capabilities and missing metadata. Document which modules short-circuit interactive commands, how `run_interactive` enforces TTY presence, and how the orchestrator flattens tool results into plain text when replying to Agent B.
- **Expected Result**: Shared baseline of current constraints to inform architecture changes; confirm root causes beyond single-command anecdotes.

## 2. Design PTY-Backed Executor
- **Issue**: There is no way to run true interactive programs because ToolExecutor lacks a PTY channel.
- **Objective**: Introduce a PTY-based tool (likely using `pexpect` or the stdlib `pty` module) that can run interactive commands headlessly.
- **Approach**: Prototype a new executor that streams output incrementally, enforces timeouts, and emits structured events (stdout chunks, prompts, exit status) to the orchestrator.
- **Expected Result**: Reliable runtime layer capable of handling pagers, curses apps, and REPLs without blocking or requiring a real terminal.

## 3. Build Prompt-Aware Dialogue Bridge
- **Issue**: Even with PTY support, Agent B currently receives only raw text; it cannot see prompt metadata or know when input is required.
- **Objective**: Define a schema for PTY events (e.g., `{"type": "prompt", "text": "Press y to continue"}`) and pipe them back through ToolExecutor so Agent B can act on them.
- **Approach**: Extend ToolExecutor responses and Agent B tool messages to include structured fields (events, suggested actions, timestamps). Update Agent B prompt to explain how to interpret these cues.
- **Expected Result**: Agent B perceives interactive prompts as explicit observations and can plan deterministic follow-up actions (send input, adjust command, abort).

## 4. Modernize Command Classification
- **Issue**: `command_parser` labels many commands as interactive regardless of flags or environment tweaks, preventing shell-first adaptations.
- **Objective**: Make detection context-aware so commands neutralized via flags (`man -P cat`, `python -c`) pass through `run_command` whenever safe.
- **Approach**: Parse wrappers, env assignments, and key options before deciding; only fall back to PTY when we cannot safely auto-neuter the interaction.
- **Expected Result**: Agent B keeps the fast `run_command` path for transformed commands, reserving PTY sessions for genuinely interactive scenarios.

## 5. Update Agent B Guidance & Tooling
- **Issue**: Prompts and tool docs do not mention the PTY dialog, nor do they encourage interaction-aware strategies.
- **Objective**: Teach Agent B how to request PTY runs, interpret prompt events, and prefer non-interactive transformations when available.
- **Approach**: Revise the system prompt, tool schemas, and usage examples to highlight: (a) convert to non-interactive when possible, (b) otherwise request PTY and wait for prompt events before sending input.
- **Expected Result**: Consistent agent behavior that mirrors operator best practices and reduces accidental hangs or misuse of the PTY channel.

## 6. Validate with Tests & Telemetry
- **Issue**: Without regression coverage we could reintroduce hangs or misclassifications.
- **Objective**: Add tests covering both the new detector logic and PTY conversation flow; instrument telemetry to monitor adoption and edge failures.
- **Approach**: Write unit/integration tests (e.g., `pytest tests/test_interactive_flow.py`) plus metrics hooks recording how often PTY prompts occur, average prompt-response latency, and fallback rates.
- **Expected Result**: Confidence that interactive workflows are stable before release and data to guide further tuning.
