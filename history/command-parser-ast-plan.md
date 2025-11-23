# Command Parser AST Rewrite Plan

## Objective
Replace the current `shlex`-based command parsing guard with a true shell parser so we can correctly classify interactive commands (e.g., allow `python3 - <<'PY' ...`). The new solution must interpret shell grammar (pipelines, redirections, heredocs, env assignments, wrappers) without falling back to `shlex`.

## Guiding Principles
- **Eliminate shlex**: No parsing decisions may rely on `shlex.split()`. A single-shell grammar pass (e.g., `bashlex`) provides the AST.
- **Fail-safe but accurate**: Continue blocking genuinely interactive tools, but stop flagging non-interactive cases (stdin redirection, pipelines) as REPLs.
- **Encapsulated context**: Produce a structured `CommandContext` object instead of free-form tuples, so future rules (Node, Ruby, custom tools) consume the same rich metadata.
- **Comprehensive testing**: Add regression tests for heredocs, pipes, and wrapper combinations plus existing suites to prevent regressions.

## Implementation Steps
1. **Introduce Shell Parser Dependency**
   - Add `bashlex` (or comparable pure-Python shell parser) to `requirements.txt` and `setup.py`.
   - Create a thin wrapper module (e.g., `command_parser/ast_parser.py`) that exposes `parse_command_ast(cmd_str) -> ParsedCommand` to shield the rest of the code from parser internals.

2. **Build CommandContext Model**
   - Define a dataclass `CommandContext` capturing:
     - `executable`: resolved first command binary (after wrappers/env)
     - `argv`: argument list exactly as executed
     - `wrappers`: ordered wrappers (sudo, env, timeout, etc.)
     - `env_overrides`
     - `stdin_bound`: bool (true if `<`, `<<`, `<<<`, here-doc, or pipe feeds stdin)
     - `stdout_redirected`, `stderr_redirected`
     - `pipeline_position`: first/solo command vs. mid/last in pipeline
   - Populate the dataclass by traversing the AST once, handling control operators, env assignments, and heredoc bodies.

3. **Rewrite `parse_command`**
   - Replace the `shlex.split()` and wrapper peeling logic with the AST-driven `CommandContext`.
   - Update wrapper detection to rely on AST nodes rather than token strings.
   - Return `(is_interactive, reason)` but base the decision entirely on the new context object.

4. **Enhance Interpreter Heuristics**
   - Update `is_interactive_command()` signatures to accept `CommandContext`.
   - Extend Python/Node/Ruby logic:
     - Treat `argv[1] == '-'` as non-interactive when `stdin_bound` is `True` (covers heredocs, `< file`, and upstream pipes).
     - Respect pipeline position (e.g., `printf ... | python3 -`).
     - Preserve existing checks for `-c`, `-m`, script paths, etc.
   - Keep editor/pager detection as-is but leveraged through context.

5. **Integrate with ToolExecutor**
   - Ensure `tools.ToolExecutor.execute()` calls the new parser module instead of the old `shlex` helper.
   - Remove any leftover `shlex.split()` usage in safety guards (including command name extraction). Use data from `CommandContext` for error messages.

6. **Testing & Validation**
   - Add unit tests covering:
     - `python3 - <<'PY'` heredoc (should be non-interactive)
     - `printf 'print(\"x\")' | python3 -`
     - Existing block cases (e.g., bare `python3`, `node`, `man`, `vim`) ensuring they remain interactive.
     - Wrapper combos (`timeout 10 python3 -c ...`, `env VAR=1 python3 script.py`).
   - Update existing suites that currently import `parse_command` to account for the new API if necessary.
   - Run full test suite to confirm no regressions.

7. **Docs & Cleanup**
   - Document the new parser behavior in `docs/` or `history/version-3-architecture.md` if needed.
   - Remove obsolete helper functions tied exclusively to `shlex` tokenization once migrated.

## Open Questions / Risks
- **Parser Coverage**: `bashlex` handles POSIX-ish Bash syntax; confirm it supports all command patterns used in cycles. If not, consider `oil-language` or another parser.
- **Performance**: Ensure AST parsing doesn’t add noticeable latency. Add simple benchmarking if needed.
- **Wrapper Handling**: Re-implement `WRAPPER_HANDLERS` as AST transformations or keep them but feed them token lists derived from AST nodes.

## Next Actions
1. Implement parser wrapper + `CommandContext`.
2. Port existing detection logic to the new context.
3. Backfill tests and documentation.
