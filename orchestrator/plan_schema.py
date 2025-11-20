"""
Plan JSON schema and validation for Agent A (Planner/Chat)

Agent A supports TWO response types:
1. Execution plan handoff (intent + success_criteria)
2. Direct response (no tools needed)

Schema goals:
- Keep Agent A lightweight; it delegates execution and final rendering to Agent B.
- Avoid narration templates; Agent B assembles the final user-facing segments.
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
    
    Validates structure for both response types.
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
    "intent": "List files in /tmp with details",
    "success_criteria": [
        "Command executes successfully",
        "Output includes file names"
    ]
}

EXAMPLE_PLAN_INVALID_WRONG_TYPE = {
    "intent": 123,
    "success_criteria": "not-an-array"
}
