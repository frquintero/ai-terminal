## Removing Heuristic Shell Analysis — Execution Plan

### Objectives
- Replace legacy heuristic + regex detection in `command_parser.py` with a deterministic, policy-driven analyzer that enumerates explicitly allowed/blocked behaviors.
- Update `tools.run_command` (and any downstream guardrails) to consume the new analyzer verdicts rather than ad-hoc booleans or narrative fallbacks.
- Expand automated tests (parser + orchestrator) to cover the deterministic policy, ensuring shell pipelines/redirections and wrapper stacks stay safe without heuristics.

### Constraints
1. No regexes or heuristic guesswork for interactive detection — policies must be explicit tables/rules.
2. No fallback storytelling: guards must return factual verdicts/logs only.
3. Maintain current safety posture (interactive commands still blocked) while eliminating outdated lists like `ALWAYS_INTERACTIVE`, `PYTHONS`, etc.
4. Keep planning artifacts within `history/`.

### Work Breakdown
1. **Policy Design**
   - Introduce immutable policy data (Python dict or external YAML/JSON) that enumerates command classes:
     - `allowed_when` clauses (e.g., requires `-c`, script args, or stdin binding).
     - `blocked_when` clauses (e.g., missing required flags or running shells without `-c`).
     - Wrapper affordances (sudo/env/timeouts) captured via structured metadata rather than heuristics.
   - Define canonical verdict enums (`ALLOW`, `BLOCK_INTERACTIVE`, etc.) to share between parser + tools.

2. **Parser Refactor**
   - Reuse existing AST building (`SimpleCommand`, wrappers, redirections) but remove `is_interactive_command`.
   - Add a `PolicyEngine.evaluate(context)` that walks the AST, checks policy clauses, and returns a structured verdict (status + factual reason string).
   - Ensure evaluation logic only uses explicit token comparisons and argument positions (no regex).

3. **Tool Guard Integration**
   - Update `tools.run_command` (and any callers) to consume policy verdicts:
     - Block commands when verdict = `BLOCK_*`, surfacing factual reason text.
     - Remove legacy fallback strings / heuristic references.
   - Ensure orchestrator logging/reporting only echoes factual data (no narrative fallbacks).

4. **Testing**
   - Update `tests/test_command_parser_ast.py` to reflect deterministic policy (e.g., explicit allow/block cases, pipelines, heredocs).
   - Extend `tests/test_orchestrator.py` to assert pipe-from → run_command chains respect new policy.
   - Add new tests covering wrapper stacks (e.g., `sudo timeout python3 script.py`) and ensure interactive detection relies solely on policy data.

5. **Validation**
   - Run targeted pytest suites (`tests/test_command_parser_ast.py`, `tests/test_orchestrator.py`, plus any new files).
   - Document any notable behavioral changes for reviewers within commit message / PR notes.

### Deliverables
- Deterministic policy definition + engine.
- Refactored command parsing + tool guard code free of heuristics/regex.
- Updated tests demonstrating the new behavior.
- Passing test results captured in the final response.

### Interpreter/Tool Policy Decisions (v3 Alignment)
- Guided by the v3 architecture's "go upstream" philosophy, interpreters that can run deterministically in batch mode (Perl, PHP, Lua-family, etc.) now receive explicit policies instead of inheriting blanket bans. Each policy encodes the exact flags or script args that make the executable non-interactive (e.g., `perl -e`, `php script.php`, `lua script.lua`, stdin-bound runs).
- Database CLIs (MySQL, PostgreSQL, Redis, Mongo) move out of the catch‑all block list and gain policies that require execute/file flags (`-e`, `-c`, `-f`, `--eval`, `--pipe`) or piped/stdin input. This satisfies the architecture guidance to unlock non-interactive pipelines while still defaulting to run_interactive when a prompt is inevitable.
- `sqlite3` now has a deterministic handler: we allow execution only when `-batch` is present, when stdin is already bound (pipe/heredoc), or when a true inline SQL argument is supplied after the database positional. Options that consume parameters (`-cmd`, `-init`, etc.) are parsed explicitly so the policy never misclassifies interactive sessions as safe.
- **DB CLI audit (psql, mongo, redis-cli, mysql):** Existing policies already whitelist the canonical non-interactive switches (`psql -c/--command/--file`, `mongo --eval` or inline script.js, `redis-cli --eval/--pipe/-x`, `mysql -e/--execute/--init-command`) and rely on stdin binding for the remaining cases, so no additional flags were necessary after review.
