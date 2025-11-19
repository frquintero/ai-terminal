"""
Plan JSON schema and validation for Agent A (Planner/Narrator)

Agent A supports TWO response types:
1. Execution Plan with narration template
2. Direct response (no tools needed)

Schema goals:
- Declarative description of required outputs via `output_keys`
- Final narration controlled by Agent A through `narration_template`
- Single-source narrator: Agent A always produces the final user message
"""

from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Agent A Response Schema (Two-Way Contract)
# ============================================================================

# 1. Execution Plan (tools required)
EXECUTION_PLAN_SCHEMA = {
    "type": "object",
    "required": ["steps", "narration_template"],
    "properties": {
        "narration_template": {
            "type": "string",
            "description": "Template referencing {output_keys} from all steps"
        },
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "object",
                "required": ["tool_name", "intent", "output_keys"],
                "properties": {
                    "tool_name": {"type": "string"},
                    "intent": {"type": "string"},
                    "description": {"type": "string"},
                    "specifics": {
                        "type": "object",
                        "description": "Concrete details for Agent B (e.g. file content, specific args)"
                    },
                    "output_keys": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"}
                    }
                }
            }
        }
    }
}

# 2. Direct Response (no tool usage)
RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["response"],
    "properties": {
        "response": {
            "type": "string",
            "description": "Final natural-language reply to the user"
        }
    }
}


# ============================================================================
# Validation Functions
# ============================================================================

def detect_response_type(plan: Any) -> Optional[str]:
    """
    Detect which response type Agent A sent.
    
    Returns:
        "execution_plan" | "response" | None
    """
    if not isinstance(plan, dict):
        return None
    
    if "steps" in plan:
        return "execution_plan"
    if "response" in plan:
        return "response"
    return None


def validate_plan_structure(plan: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate plan structure against schema (three-way contract).
    
    Args:
        plan: Parsed JSON object from Agent A
    
    Returns:
        (valid: bool, error_message: Optional[str])
    
    Validates structure for all three response types.
    Does NOT validate tool existence - that's done separately.
    """
    # Must be dict
    if not isinstance(plan, dict):
        return False, f"Response must be object, got {type(plan).__name__}"
    
    # Detect response type
    response_type = detect_response_type(plan)
    
    if response_type is None:
        return False, (
            "Response must be one of:\n"
            '1. Execution plan: {"steps": [...], "narration_template": "..."}\n'
            '2. Direct response: {"response": "..."}'
        )
    
    # Validate based on type
    if response_type == "execution_plan":
        return _validate_execution_plan(plan)
    elif response_type == "response":
        return _validate_response(plan)
    
    return False, f"Unknown response type: {response_type}"


def _validate_execution_plan(plan: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate execution plan structure."""
    steps = plan["steps"]
    
    if not isinstance(steps, list):
        return False, f"'steps' must be array, got {type(steps).__name__}"
    if len(steps) == 0:
        return False, "Plan must have at least 1 step"
    if len(steps) > 10:
        return False, f"Plan has {len(steps)} steps (max 10). Consider breaking into multiple queries."
    
    template = plan.get("narration_template")
    if not isinstance(template, str):
        return False, f"'narration_template' must be string, got {type(template).__name__}"
    if not template.strip():
        return False, "'narration_template' cannot be empty"
    
    # Validate each step
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            return False, f"Step {idx} must be object, got {type(step).__name__}"
        
        # Required fields
        if "tool_name" not in step:
            return False, f"Step {idx} missing required 'tool_name'"
        if "intent" not in step:
            return False, f"Step {idx} missing required 'intent'"
        if "output_keys" not in step:
            return False, f"Step {idx} missing required 'output_keys'"
        
        # Type checks
        if not isinstance(step["tool_name"], str):
            return False, f"Step {idx} 'tool_name' must be string"
        if not isinstance(step["intent"], str):
            return False, f"Step {idx} 'intent' must be string"
        if "description" in step and not isinstance(step["description"], str):
            return False, f"Step {idx} 'description' must be string if provided"
        if "specifics" in step and not isinstance(step["specifics"], dict):
            return False, f"Step {idx} 'specifics' must be object (dict) if provided"
        
        # Non-empty checks
        if not step["tool_name"].strip():
            return False, f"Step {idx} 'tool_name' cannot be empty"
        if not step["intent"].strip():
            return False, f"Step {idx} 'intent' cannot be empty"
        if "description" in step and not step["description"].strip():
            return False, f"Step {idx} 'description' cannot be empty"
        
        output_keys = step["output_keys"]
        if not isinstance(output_keys, list):
            return False, f"Step {idx} 'output_keys' must be array, got {type(output_keys).__name__}"
        if len(output_keys) == 0:
            return False, f"Step {idx} 'output_keys' must have at least one entry"
        seen = set()
        for key in output_keys:
            if not isinstance(key, str):
                return False, f"Step {idx} output key must be string, got {type(key).__name__}"
            key_stripped = key.strip()
            if not key_stripped:
                return False, f"Step {idx} output key cannot be empty"
            if key_stripped in seen:
                return False, f"Step {idx} output key '{key_stripped}' is duplicated"
            seen.add(key_stripped)
            # normalize list entries in place
        step["output_keys"] = [k.strip() for k in output_keys]
    
    return True, None


def _validate_response(plan: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate direct response structure."""
    response = plan["response"]
    
    if not isinstance(response, str):
        return False, f"'response' must be string, got {type(response).__name__}"
    if not response.strip():
        return False, "'response' cannot be empty"
    
    return True, None


def validate_tool_availability(plan: Dict[str, Any], available_tools: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Validate that all tools in plan exist in TOOLS registry.
    
    Args:
        plan: Validated plan dict
        available_tools: List of available tool names from TOOLS.keys()
    
    Returns:
        (valid: bool, error_message: Optional[str])
    """
    available_set = set(available_tools)
    
    for idx, step in enumerate(plan["steps"]):
        tool_name = step["tool_name"]
        
        if tool_name not in available_set:
            return False, f"Step {idx}: Unknown tool '{tool_name}'. Available: {sorted(available_set)}"
    
    return True, None


# ============================================================================
# Example Plans (for testing and documentation)
# ============================================================================

EXAMPLE_PLAN_SIMPLE = {
    "steps": [
        {
            "tool_name": "run_command",
            "intent": "list all files and directories in /tmp with details",
            "description": "List files in /tmp directory",
            "output_keys": ["files"]
        }
    ],
    "narration_template": "Here are the files in /tmp:\n{files}"
}

EXAMPLE_PLAN_MULTI_STEP = {
    "steps": [
        {
            "tool_name": "run_command",
            "intent": "find Python files in current directory, limit to first 10 results",
            "description": "Find first 10 Python files",
            "output_keys": ["py_files"]
        },
        {
            "tool_name": "run_command",
            "intent": "count lines in all Python files",
            "description": "Count lines in Python files",
            "output_keys": ["line_counts"]
        },
        {
            "tool_name": "write_file",
            "intent": "create a file named report.txt with text 'Analysis complete'",
            "description": "Write summary report",
            "output_keys": ["report_path"]
        }
    ],
    "narration_template": (
        "Found these Python files:\n{py_files}\n\n"
        "Line counts:\n{line_counts}\n\n"
        "Report saved to {report_path}"
    )
}

EXAMPLE_PLAN_INVALID_NO_STEPS = {
    "steps": [],
    "narration_template": "Nothing to do"
}

EXAMPLE_PLAN_INVALID_WRONG_TYPE = {
    "steps": "not an array",
    "narration_template": "Invalid"
}

EXAMPLE_PLAN_INVALID_MISSING_FIELD = {
    "steps": [
        {
            "tool_name": "run_command",
            "intent": "Example intent",
            "description": "Missing output_keys"
        }
    ],
    "narration_template": "Result: {value}"
}
