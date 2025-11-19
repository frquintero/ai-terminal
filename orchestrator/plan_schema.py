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
    "required": ["intent"],
    "properties": {
        "intent": {
            "type": "string",
            "description": "High-level goal for Agent B"
        },
        "success_criteria": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of conditions for success"
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
    
    if "intent" in plan:
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
            '1. Execution plan: {"intent": "...", "success_criteria": [...]}\n'
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
    intent = plan.get("intent")
    
    if not isinstance(intent, str):
        return False, f"'intent' must be string, got {type(intent).__name__}"
    if not intent.strip():
        return False, "'intent' cannot be empty"
    
    success_criteria = plan.get("success_criteria")
    if success_criteria is not None:
        if not isinstance(success_criteria, list):
            return False, f"'success_criteria' must be array, got {type(success_criteria).__name__}"
        for idx, criteria in enumerate(success_criteria):
            if not isinstance(criteria, str):
                return False, f"Success criteria {idx} must be string"
    
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
    # Agent A no longer suggests tools, so this validation is skipped for Agent A plans
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
