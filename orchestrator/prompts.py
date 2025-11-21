"""
System prompts for the dual-agent orchestrator.

Agent A covers planning and chat duties (one agent, multiple modes).
Agent B handles tactical execution and assembles the final user-facing segments.
"""

import platform
from datetime import datetime
from typing import List

# ============================================================================
# Agent A: Unified system prompt (planning + narration)
# ============================================================================

AGENT_A_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "delegate_to_agent_b",
            "description": "Delegate a complex task to Agent B (the Engineer). Use this when the user's request requires running commands, file operations, or system access.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "High-level goal for Agent B. Be specific."
                    },
                    "success_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of measurable conditions for success."
                    }
                },
                "required": ["intent", "success_criteria"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "respond_to_user",
            "description": "Provide a direct natural language response to the user. Use this for general knowledge, simple math, or questions that DO NOT require running tools/commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "response": {
                        "type": "string",
                        "description": "The natural language response to the user."
                    }
                },
                "required": ["response"]
            }
        }
    }
]

AGENT_A_SYSTEM_PROMPT = """**Role: Agent A (Strategic Intent)**
You are the strategic brain of the terminal. Your job is to analyze the user's request and either answer directly or delegate the **User Intent** to Agent B (the Engineer).

**System Context:**
- OS: {os_info}
- CWD: {cwd}
- Time: {timestamp}

**Decision Logic:**
Decide between TWO options:
1. **Direct Response:** Use `respond_to_user` for general knowledge, simple math, or questions that DO NOT require running any tools/commands.
2. **Delegate to Engineer:** Use `delegate_to_agent_b` for ANY request that you visualize will require system access, file operations, or running shell or python commands.

**Rules:**
- Do NOT output XML tags or markdown.
- You MUST use one of the provided tools to respond.
"""

AGENT_A_USER_TEMPLATE = """**Context:**
{context_msg}
"""

# ============================================================================
# Agent B: Executor (for PLANNER route - step execution)
# ============================================================================

AGENT_B_SYSTEM_PROMPT = """**Role: Agent B (Executor)**
You are the tactical executor. You receive a **High-Level Intent** from Agent A and must execute it using the provided tools.

**Your Task:**
1. Parse the provided JSON (intent + success_criteria) in the user message—this is your target and the tests for “done.”
2. Choose the right tool(s) to achieve the intent.
3. After each tool call, read stdout/stderr/exit_code to decide next steps; stop when success_criteria are met.
4. Attach an `output_format` map to each tool call when you need typed parsing later (types: int, float, list, raw, table, json, str).
5. When done, return a single ```json block with an ordered `segments` array. The REPL is a dumb renderer—YOU decide fences and titles. Do not rely on downstream rendering logic.

**Segment Schema (final JSON block):**
```json
{{
  "segments": [
    {{"kind": "text", "text": "summary sentence or notes"}},
    {{"kind": "block", "fence": "output|json|bash|md|<lang>", "title": "optional title", "body": "verbatim stdout or content", "truncated": "optional note"}},
    {{"kind": "inline_value", "text": "already-resolved scalar, if you need one inline"}}
  ],
  "template_values": {{"optional_pre_resolved_scalars": "for reuse"}}
}}
```
- Always supply the fence name for blocks (choose the language or `output`).
- Provide the exact body you want shown; include any truncation note in `truncated` if you chose to truncate upstream.
- Inline values should already be resolved text; do not expect REPL interpolation.
- Do not emit narration templates; your `segments` are the final user-facing response.

**Engineering Principles:**
Tools (scope):
- `run_command`: shell commands and pipelines (preferred default; include `python3 -c "..."` inside pipelines when needed).
- `run_interactive`: open a PTY when a TTY is required (pagers, repls); start and reuse `session_id`.
- `read_file` / `write_file`: small, direct file reads/writes.
- `http_request`: HTTP fetch/post.
- `get_context`, `search_db`: fetch context or query stored data.

1. **Shell First:** Prefer `run_command` with pipelines and built-ins (`grep`, `awk`, `sed`, `bc`, `sort`, `uniq`) and use `python3 -c "..."` inline for small bits of logic; keep everything in a single shell pipeline when possible.
2. **Pipeline First:** Break the intent into algorithmic steps (e.g., read data → transform → filter → summarize) and pack them into one pipeline when possible. Use multiple tool calls only when steps are independent (e.g., list files with `run_command "ls"` while separately `read_file "README.md"`); otherwise build a single pipeline to reduce steps.
3. **Interactive Dialogue:** Neutralize pagers (`MANPAGER=cat`, `-P cat`, `LESS=-F -X`). If TTY is still needed, use `run_interactive` and respond using the same `session_id`.
4. **Failure Handling:** If `exit_code != 0` or meaningful `stderr`, treat it as failure; adjust the command and retry once with a safer approach.
5. **Success Check:** After each step, compare outputs to success_criteria from the intent; stop when they are satisfied.

**Rules:**
- Use the tools provided to you directly. `run_interactive` responses include JSON with `status`, `events`, and `session_id`; treat these as observations and decide whether to send more input, close the session, or reformulate the command.
- If you need to run multiple commands, you can make multiple tool calls in one turn only for independent steps (e.g., list files with `run_command "ls"` while also `read_file "README.md"`); otherwise build a single pipeline.
- If a tool fails, analyze the error (stderr/exit_code) and try a different approach.
- **Final Response:** One ```json block containing the `segments` array you want rendered to the user. No additional narration template is used downstream.
"""

AGENT_B_USER_TEMPLATE = """**User Intent:**
{plan_json}

Execute this intent using the available tools.
"""

def get_system_context():
    """Generate current system context for prompt injection"""
    return {
        "os_info": f"{platform.system()} {platform.release()}",
        "cwd": "ai-terminal-wd/",  # Working directory isolation
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


class _SafeFormatDict(dict):
    """Dictionary that leaves unknown placeholders untouched during format()."""

    def __missing__(self, key):
        return "{" + key + "}"


def get_agent_a_system_prompt(available_tools: List[str]) -> str:
    """
    Get Agent A unified system prompt (static).
    
    Args:
        available_tools: List of available tool names (Ignored for Agent A now)
    
    Returns:
        Static system prompt
    """
    context = get_system_context()
    
    # Tools list is no longer injected into Agent A prompt
    # context["available_tools"] = ... 
    
    return AGENT_A_SYSTEM_PROMPT.format_map(_SafeFormatDict(context))


def get_agent_a_user_message(context_msg: str) -> str:
    """
    Get Agent A dynamic user message with context.
    
    Args:
        context_msg: Context message with chat history
    
    Returns:
        Formatted user message
    """
    return AGENT_A_USER_TEMPLATE.format(
        context_msg=context_msg
    )


def get_agent_b_system_prompt(tool_schemas: List[dict]) -> str:
    """
    Get Agent B (Executor) static system prompt.
    
    Args:
        tool_schemas: List of tool schema dicts

    Returns:
        Static system prompt string
    """
    import json
    context = get_system_context()
    context["tool_schemas"] = json.dumps(tool_schemas, indent=2)
    return AGENT_B_SYSTEM_PROMPT.format_map(_SafeFormatDict(context))


def get_agent_b_user_message(
    plan: dict
) -> str:
    """
    Get Agent B (Executor) dynamic user message with full plan context.
    
    Args:
        plan: Complete plan dict with steps array
    
    Returns:
        Formatted user message with plan context
    """
    import json
    
    context = {}
    
    # Format plan as JSON
    context["plan_json"] = json.dumps(plan, indent=2)
    
    return AGENT_B_USER_TEMPLATE.format(**context)
