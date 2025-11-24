# Tool Calling Issues in ai-terminal

## Problem Summary

The current Agent B tool-calling implementation in `orchestrator/orchestrator.py` diverges from the Groq local tool-calling patterns described in `history/grok_tool_calling_model.md`. As a result, the system does not fully exploit the model's native agentic behavior and multi-tool capabilities.

## Key Problems

1. **Forced termination via `respond_to_user` tool**
- The orchestrator introduces a synthetic `respond_to_user` tool that is treated as the only "legitimate" way for Agent B to finish a cycle.
- When Agent B calls `respond_to_user`, the loop forcefully exits, regardless of whether the model might naturally want additional tool turns.
- This is not part of the Groq tool-calling model; it is a local convention that the LLM must learn, and it competes with the model's native behavior of ending when there are no further `tool_calls`.

2. **Loop shape differs from Groq agentic loop pattern**
- ai-terminal uses a bounded `for loop_idx in range(max_loops)` around the LLM calls.
- The break conditions are dominated by `respond_to_user_called` and a "no tool calls" condition, rather than a canonical "while tool_calls and iteration < max_iterations" loop.
- This makes the loop more brittle and less aligned with the examples in `grok_tool_calling_model.md`, where the model continues requesting tools until it is ready to answer without tools.

3. **Missing explicit `tool_choice` configuration**
- In `llm_client.py`, when `tools` are provided, `tool_choice` is only sent if a non-empty value is explicitly passed.
- The Agent B loop calls `llm_client.call` with `tools=tools` but does not pass `tool_choice="auto"`.
- Groq examples consistently send `tool_choice="auto"` when using tools, to clearly signal that tool calling is enabled and under model control.
- Relying on implicit defaults may lead to inconsistent or suboptimal tool-calling behavior.

4. **Underuse of multi-turn, multi-tool patterns**
- The current architecture assumes that Agent B will eventually call `respond_to_user` in the same tool-calling pass where it finishes its reasoning.
- In contrast, the Groq docs show multi-turn patterns where the model:
  - Issues one or more tool calls,
  - Receives and processes tool results,
  - Optionally issues additional tool calls, and
  - Finally returns a non-tool response once it has enough information.
- ai-terminal technically loops and can handle multiple tool turns, but the presence and expectation of `respond_to_user` as a terminal tool discourages the model from using the natural "no more tool_calls" termination signal.

## Behavioral Consequences

- The model's agentic capabilities are constrained: instead of freely chaining tools until it is ready to answer, it is steered toward producing a `respond_to_user` call to end the cycle.
- Complex tasks that would benefit from several rounds of tool use and reflection may be prematurely terminated once the model learns that `respond_to_user` is the preferred way to conclude.
- The orchestrator is doing extra, non-standard work to encode finalization logic that the model can already handle via its normal completion behavior.

## Desired Behavior (Per Groq Docs)

According to `history/grok_tool_calling_model.md` and the Groq documentation:

- The application should:
  - Call the model with `messages` plus a list of `tools` and `tool_choice="auto"`.
  - Inspect `response.choices[0].message.tool_calls`.
  - If there are tool calls, execute them locally and append tool results back into `messages` as `role: "tool"` messages.
  - Call the model again with the updated `messages`, repeating while there are tool calls and until a maximum iteration cap is reached.
  - When the model returns a response without `tool_calls`, treat that as the final answer.
- Termination is therefore driven by the model naturally stopping its use of tools, not by a synthetic "finalization tool" that the model is forced to invoke.

## Proposed Direction for ai-terminal

1. **Align loop with Groq agentic pattern**
- Replace the current `for`-based loop with a condition that continues while the last assistant message includes `tool_calls` and a maximum iteration limit has not been reached.
- Keep appending assistant messages and tool results to the shared `messages` list, as shown in the Groq examples.

2. **Remove `respond_to_user` as a required terminator**
- Stop treating `respond_to_user` as the only valid way to conclude Agent B.
- Instead, treat any assistant message without `tool_calls` as a valid final response.
- If a specialized response structure is still desired (segments, policy contract, attachments), that can be requested via instructions in the system prompt and parsed from the final assistant message content, rather than encoded as a tool.

3. **Set `tool_choice` explicitly when using tools**
- When `tools` are provided to `llm_client.call` for Agent B, pass `tool_choice="auto"` so that the underlying model is clearly in tool-calling mode.
- This brings the runtime behavior in line with the concrete examples from `grok_tool_calling_model.md`.

4. **Let the model use multi-tool, multi-turn flows naturally**
- Allow the model to:
  - Issue multiple tool calls in a single turn (already supported via iterating over `msg.tool_calls`).
  - Request further tool calls in subsequent turns without being forced to finalize via `respond_to_user`.
- Use the maximum-iteration safeguard as the primary guardrail against infinite loops, rather than a synthetic finalization tool.

## Expected Benefits

- Closer alignment with Groq's documented local tool-calling model, reducing surprises and subtle bugs.
- Better exploitation of the model's built-in agentic capabilities, especially for long, multi-step tasks.
- Simpler mental model: the orchestrator becomes a straightforward implementation of the Groq examples, rather than teaching the LLM project-specific control tools.
- Reduced coupling between model behavior and a custom `respond_to_user` interface, making it easier to change models or prompts without re-teaching finalization semantics.

## Open Questions

- How much of the existing `respond_to_user` payload (segments, policy contract, attachments) is essential, and what is the minimal shape we still need from Agent B?
- Should the final response shape be specified via `response_format` JSON schema, or purely via instructions in the system prompt?
- Do we want any additional safeguards (beyond `max_iterations`) to detect degenerate tool-calling loops?

This document should serve as the reference for why the current tool-calling flow is problematic and how we intend to realign it with the Groq local tool-calling and agentic loop patterns described in `history/grok_tool_calling_model.md`. 