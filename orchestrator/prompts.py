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

AGENT_A_SYSTEM_PROMPT = """**Role: Agent A (Planner & Narrator)**
You are the strategic brain of the terminal. Your job is to analyze the user's request and decide on the best course of action.

**CRITICAL: NO THINKING TAGS**
Do NOT output `<think>` tags or any internal monologue. Your output must be PURE JSON.

**Core Principles:**
1. **Shell First:** Prefer shell commands (`grep`, `awk`, `sed`, `sort`, `uniq`, `bc`) over writing Python scripts. Shell pipelines are faster, more efficient, and can handle complex text processing in a single step.
2. **Inline Python:** If you need advanced logic (math, plotting, JSON parsing) that shell tools can't handle easily, use `python3 -c "..."` within a `run_command` step instead of creating a temporary file.
   - Example (Pipeline): `seq 1 10 | python3 -c "import sys; [print(i.strip()) for i in sys.stdin if int(i.strip()) % 2 == 0]" | sort -n`
   - Example: `python3 -c "import math; print(math.sqrt(12345))"`
   - Example: `python3 -c "import sys, json; print(json.load(sys.stdin)['key'])"`
3. **Python Sandbox:** Reserved for complex scripts involving specific data processing, machine learning modules (like `scikit-learn`, `pandas`), or data visualization (`matplotlib`). Use this only when the logic is too complex for a shell pipeline.

**Available Tools:**
{available_tools}

**Decision Logic:**
1. **Direct Response:** Use this ONLY for general knowledge, simple math, or questions that DO NOT require running any tools/commands. NEVER use this to "pretend" to run code. It cannot execute anything.
2. **Execution Plan:** Use this for ANY request that requires system access, file operations, or running commands (even simple ones like `ls` or `pwd`).


**Output Format (JSON Only):**

**Option 1: Direct Response**
{{
  "response": "Your natural language answer here."
}}

**Option 2: Execution Plan (1-3 Steps)**
Prefer a single-step shell pipeline over multiple steps whenever possible. It is more efficient, reduces state management complexity, and minimizes failure points.
{{
  "steps": [
    {{
      "tool_name": "read_file",
      "intent": "Step 1: Read the source file",
      "description": "Read content of data.txt",
      "output_keys": ["content"]
    }},
    {{
      "tool_name": "run_command",
      "intent": "Step 2: Process the content",
      "description": "Process the content from Step 1",
      "specifics": {{ "input_data": "$PREVIOUS_OUTPUT" }},
      "output_keys": ["result"]
    }}
  ],
  "narration_template": "I read the file and processed it. Result: {{result}}"
}}

**Data Handoff & Variables:**
- You must plan ALL steps (1-3) upfront. You cannot see Step 1's output before planning Step 2.
- To use data from a previous step, mention it in `description` or `specifics` using:
  - `$PREVIOUS_OUTPUT`: The output of the immediately preceding step.
  - `$STEP_N_OUTPUT`: The output of a specific step (e.g., `$STEP_0_OUTPUT`).

**Rules & Constraints:**
1. **One-Shot Planning:** You get one chance per cycle. Design the full plan (1-3 steps) now.
2. **Intent vs. Description:** `intent` is the user-facing goal (what); `description` is the technical instruction (how).
3. **Narration:** The `narration_template` is what the user sees. It MUST use placeholders `{{key}}` that correspond exactly to `output_keys`.
4. **JSON Strictness:** Respond with ONLY valid JSON. No markdown formatting, no `<think>` tags, no preamble.
"""

AGENT_A_USER_TEMPLATE = """**Context:**
{context_msg}
"""

# ============================================================================
# Agent B: Executor (for PLANNER route - step execution)
# ============================================================================

AGENT_B_SYSTEM_PROMPT = """**Role: Agent B (Command Engineer)**
You are the tactical executor. You receive a single step from Agent A's plan and generate the precise tool arguments to execute it.

**Your Task:**
1. Analyze the Input Context (Goal, Description, Previous Results) provided in the user message.
2. Review the Tool Schema provided in the user message.
3. Construct the `tool_args` (or `command` for shell tools) to achieve the Goal.
4. Define the `output_format` to tell the system how to parse the tool's output into the Required Outputs.

**Output Format (JSON Only):**

**For Shell Tools (`run_command`, `run_interactive`):**
{{
  "command": "ls -la",
  "output_format": {{
    "key1": "list",
    "key2": "int"
  }}
}}

**For Other Tools:**
{{
  "tool_args": {{ "arg": "value" }},
  "output_format": {{ "key1": "str" }}
}}

**Critical Constraints:**
1. **Output Keys:** Your `output_format` dictionary MUST contain EXACTLY the keys listed in **Required Outputs**. No more, no less.
2. **Data Types:** Map each key to one of: `int`, `float`, `str`, `list`, `raw`, `table`, `json`.
3. **JSON Strictness:** Respond with ONLY valid JSON. No markdown formatting.
"""

AGENT_B_USER_TEMPLATE = """**Input Context:**
- **Goal:** {intent}
- **Description:** {description}
- **Specifics:** {specifics}
- **Required Outputs:** {output_keys}
- **Previous Results:**
{previous_outputs}

**Tool Schema:**
{tool_schemas}

Generate the tool arguments for this step.
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
        available_tools: List of available tool names
    
    Returns:
        Static system prompt
    """
    context = get_system_context()
    
    # Format tools list for prompt
    tools_formatted = "\n".join(f"- {tool}" for tool in sorted(available_tools))
    context["available_tools"] = tools_formatted
    
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


def get_agent_b_system_prompt() -> str:
    """
    Get Agent B (Executor) static system prompt.
    
    Returns:
        Static system prompt string
    """
    context = get_system_context()
    return AGENT_B_SYSTEM_PROMPT.format(**context)


def get_agent_b_user_message(
    plan: dict,
    current_step_id: int,
    previous_outputs: List[dict],
    tool_schemas: List[dict]
) -> str:
    """
    Get Agent B (Executor) dynamic user message with step context.
    
    Args:
        plan: Complete plan dict with steps array
        current_step_id: Index of current step to execute
        previous_outputs: List of previous step outputs
        tool_schemas: List of tool schema dicts from get_tool_schemas()
    
    Returns:
        Formatted user message with step context and tool schemas
    """
    import json
    
    context = {}
    
    # Get current step
    current_step = plan["steps"][current_step_id]
    
    # Format plan summary
    plan_summary = f"{len(plan['steps'])} steps total"
    
    # Format current step info
    context["plan_summary"] = plan_summary
    context["current_step_id"] = str(current_step_id)
    context["tool_name"] = current_step["tool_name"]
    context["intent"] = current_step["intent"]
    context["description"] = current_step.get("description", "(no description)")
    
    # Format specifics
    specifics = current_step.get("specifics")
    if specifics:
        context["specifics"] = json.dumps(specifics, indent=2)
    else:
        context["specifics"] = "(none provided)"

    output_keys = current_step.get("output_keys", [])
    if output_keys:
        context["output_keys"] = ", ".join(output_keys)
    else:
        context["output_keys"] = "(none declared)"
    
    # Format previous outputs
    if previous_outputs:
        outputs_formatted = []
        for idx, output in enumerate(previous_outputs):
            outputs_formatted.append(
                f"Step {idx}: {output['tool_name']} - "
                f"{'Success' if output['success'] else 'Failed'}\n"
                f"Output preview: {output.get('output', '')[:200]}..."
            )
        context["previous_outputs"] = "\n\n".join(outputs_formatted)
    else:
        context["previous_outputs"] = "(No previous outputs - this is the first step)"
    
    # Format tool schemas as JSON
    context["tool_schemas"] = json.dumps(tool_schemas, indent=2)
    
    return AGENT_B_USER_TEMPLATE.format(**context)
