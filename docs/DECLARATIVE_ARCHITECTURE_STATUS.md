# Declarative Architecture Status

**Date:** November 19, 2025
**Status:** Completed

## Overview

The system has been successfully migrated from an iterative "Agent A -> Agent B -> Execute -> Agent B -> Execute" loop to a **Declarative Architecture**.

## Key Changes

### 1. One-Shot Execution Manifest
- **Agent B (Engineer)** is now called exactly **ONCE** per plan.
- Instead of generating one step at a time, Agent B generates a complete **Execution Manifest** containing concrete tool calls for ALL steps in the plan.
- This reduces latency (fewer LLM round-trips) and token usage.

### 2. Variable Substitution
- Since Agent B generates all steps upfront, it cannot know the actual output of Step 0 when defining Step 1.
- We introduced a variable system:
  - `$PREVIOUS_OUTPUT`: Refers to the output of the immediately preceding step.
  - `$STEP_N_OUTPUT`: Refers to the output of Step N (0-indexed).
- **Structured Access**: Variables support dot notation to access specific fields of the structured tool output:
  - `$PREVIOUS_OUTPUT.stdout`
  - `$STEP_0_OUTPUT.exit_code`
  - `$STEP_0_OUTPUT.json.key`

### 3. Structured Tool Outputs
- All tools in `tools.py` now return a `Dict[str, Any]` instead of a simple string.
- Standard fields: `success`, `stdout`, `stderr`, `exit_code`, `output` (legacy fallback).
- This enables precise variable substitution.

### 4. Orchestrator Logic
- `orchestrator/orchestrator.py` was refactored to:
  1. Call Agent A to get the high-level Plan.
  2. Call Agent B (via `_get_execution_manifest`) to get the full list of tool calls.
  3. Iterate through the manifest locally, executing tools and performing variable substitution at runtime.

## Verification

- **Unit Tests**: `tests/test_orchestrator.py` updated and passed.
- **E2E Tests**: `tests/test_e2e_planner.py` updated and passed.

## Next Steps

- Monitor the system for any edge cases where variable substitution might fail (e.g., complex nested JSON).
- Consider adding more sophisticated variable transformations (e.g., string slicing, regex extraction) if needed in the future.
