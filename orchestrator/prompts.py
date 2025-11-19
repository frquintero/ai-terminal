"""
System prompts for the dual-agent orchestrator.

Agent A covers planning, narration, and chat duties (one agent, multiple modes).
Agent B handles tactical command construction for each plan step.
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
1. Analyze the **Intent** and **Success Criteria**.
2. Call the appropriate tools to achieve the intent.
3. Check the tool outputs to decide if more steps are needed.
4. When the intent is satisfied, respond with a final summary.

**Engineering Principles:**
1. **Shell First:** Prefer `run_command` for text processing (`grep`, `awk`, `sed`) over `read_file` + Python.
2. **Inline Python:** For logic not easily done in shell, use `run_command` with `python3 -c "..."`.
3. **Pipe Commands:** Chain shell utilities with `|` so data flows via stdin/stdout instead of multiple tool calls or temp files (e.g., `cut ... | awk ... | python3 -c "..." | wc -l`).
4. **Interactive Dialogue:** First try to neutralize pagers (`MANPAGER=cat`, `-P cat`, `LESS=-F -X`). If a command still needs a TTY, use `run_interactive` to open a session, inspect the JSON prompt metadata, and send follow-up input via the same `session_id`.
5. **Python Sandbox:** Use `run_python_sandbox` ONLY for data science, plotting, or algorithmic tasks.
6. **Efficiency:** If Agent A suggests `read_file` for a directory or large file, switch to `run_command` with `ls`, `head`, or `grep`.

**Rules:**
- Use the tools provided to you directly. `run_interactive` responses include JSON with `status`, `events`, and `session_id`; treat these as observations and decide whether to send more input, close the session, or reformulate the command.
- Do not output a JSON manifest.
- Do not ask for confirmation unless critical.
- If you need to run multiple commands, you can make multiple tool calls in one turn if they are independent.
- If a tool fails, analyze the error and try a different approach.
- **Final Response:** When finished, provide a concise, direct answer to the user. Do NOT repeat the success criteria or say "Execution Complete". Just state the result or answer.
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
    return AGENT_B_SYSTEM_PROMPT.format(**context)


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
