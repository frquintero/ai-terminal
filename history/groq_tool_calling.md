# OUTDATED DO NOT USE

# Groq Tool-Calling Migration Plan

## 1. Scope & Goals
- Adopt Groq's local tool-calling contract end-to-end so Agent A and Agent B never invent tool names.
- Promote `respond_to_user` to a first-class tool registered in every Agent invocation that may deliver a user-facing reply.
- Preserve structured responses (segments + policy_contract) for auditability while removing phantom "json" fallbacks.

## 2. respond_to_user Schema
- Required fields:
  - `segments`: ordered list of `{kind, text|body, fence, metadata}` objects mirroring the REPL renderer (`kind` ∈ {text, block, inline_value}).
  - `policy_contract`: structured object capturing rules, citations, and compliance notes; cannot be empty (must include at least one `rules` entry).
  - `policy_summary`: short plain-text recap of the applied policy checks.
  - `attachments` (optional): array of files or references.
- Example payload:
```json
{
  "name": "respond_to_user",
  "arguments": {
    "segments": [
      {"kind": "text", "text": "Listing complete.", "metadata": {"code_block": false}}
    ],
    "policy_contract": {
      "rules": [
        {"id": "files-only", "status": "passed", "details": "No forbidden paths accessed."}
      ]
    },
    "policy_summary": "Policy ok; shared basic ls output.",
    "attachments": []
  }
}
```

## 3. Orchestrator Changes
- Update agent tool loops to register `respond_to_user` alongside operational tools (e.g., `run_command`, `read_file`).
- On receiving `respond_to_user`, validate payload, log it, render the outward message, and exit the loop; no fallback tool names allowed.
- Remove legacy handling of fabricated `json` or similar placeholders.
- Ensure `cycle_failures` and `llm_call_fails` capture factual snapshots when Groq rejects a request (tool mismatch, bad schema, etc.).

## 4. Prompt & Documentation Updates
- Revise Agent A/B prompt templates (`orchestrator/prompts.py`) so examples and schema reminders reference `respond_to_user` and demonstrate valid payloads.
- Surface the contract summary in README and Agent guidance so planners know final responses are structured tool calls.
- Update any auxiliary docs (e.g., `history/version-3-architecture.md`) to align with the new policy engine and no-fallback stance.

## 5. Validation Strategy
- Use `preview_prompts.py` (replacement for the old debug helper) to inspect rendered prompts after changes.
- Run smoke cycles (e.g., simple `ls` task) to ensure Groq accepts tool usage and that final assistant messages come via `respond_to_user`.
- Inspect `logs/orchestrator.db` tables (`llm_traces`, `llm_call_fails`, `cycle_failures`) to confirm no `json` or missing-tool errors remain.
- Extend tests if needed to cover the new tool registry and final-response handling.
