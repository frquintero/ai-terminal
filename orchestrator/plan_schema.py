"""
Plan JSON schema and validation for Agent A (Planner)

Agent A supports THREE response types:
1. Execution Plan: Multi-step task with tools
2. Clarification Request: Ask user for clarification
3. Delegation: Route to Agent C for direct answer

Schema is designed to be:
- Simple enough for LLM to generate reliably (95%+ success)
- Expressive enough to capture multi-step workflows
- Aligned with "Shell-First" philosophy (prefer single shell commands over multi-step plans)
"""

from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Agent A Response Schema (Three-Way Contract)
# ============================================================================

# Agent A can respond with ONE OF THREE formats:

# 1. Execution Plan (for clear execution tasks)
EXECUTION_PLAN_SCHEMA = {
    "type": "object",
    "required": ["steps"],
    "properties": {
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,  # Conservative limit - most tasks should be <5 steps
            "items": {
                "type": "object",
                "required": ["tool_name", "intent", "description"],
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "Tool to execute (must exist in TOOLS registry)"
                    },
                    "intent": {
                        "type": "string",
                        "description": "High-level intent describing what to accomplish with this tool"
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what this step does"
                    }
                }
            }
        }
    }
}

# 2. Clarification Request (for ambiguous queries)
CLARIFICATION_SCHEMA = {
    "type": "object",
    "required": ["clarify"],
    "properties": {
        "clarify": {
            "type": "string",
            "description": "Question to ask user for clarification"
        }
    }
}

# 3. Delegation to Agent C (for simple informational questions)
DELEGATION_SCHEMA = {
    "type": "object",
    "required": ["delegate_to_chat"],
    "properties": {
        "delegate_to_chat": {
            "type": "string",
            "description": "Reason for delegating to Agent C"
        }
    }
}

# Combined schema (oneOf)
PLAN_SCHEMA = {
    "oneOf": [
        EXECUTION_PLAN_SCHEMA,
        CLARIFICATION_SCHEMA,
        DELEGATION_SCHEMA
    ]
}


# ============================================================================
# Validation Functions
# ============================================================================

def detect_response_type(plan: Any) -> Optional[str]:
    """
    Detect which response type Agent A sent.
    
    Args:
        plan: Parsed JSON object from Agent A
    
    Returns:
        "execution_plan" | "clarification" | "delegation" | None
    """
    if not isinstance(plan, dict):
        return None
    
    if "steps" in plan:
        return "execution_plan"
    elif "clarify" in plan:
        return "clarification"
    elif "delegate_to_chat" in plan:
        return "delegation"
    else:
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
            '1. Execution plan: {"steps": [...]}\n'
            '2. Clarification: {"clarify": "question"}\n'
            '3. Delegation: {"delegate_to_chat": "reason"}'
        )
    
    # Validate based on type
    if response_type == "execution_plan":
        return _validate_execution_plan(plan)
    elif response_type == "clarification":
        return _validate_clarification(plan)
    elif response_type == "delegation":
        return _validate_delegation(plan)
    
    return False, f"Unknown response type: {response_type}"


def _validate_execution_plan(plan: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate execution plan structure."""
    steps = plan["steps"]
    
    # steps must be list
    if not isinstance(steps, list):
        return False, f"'steps' must be array, got {type(steps).__name__}"
    
    # Must have at least 1 step
    if len(steps) == 0:
        return False, "Plan must have at least 1 step"
    
    # Conservative limit
    if len(steps) > 10:
        return False, f"Plan has {len(steps)} steps (max 10). Consider breaking into multiple queries."
    
    # Validate each step
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            return False, f"Step {idx} must be object, got {type(step).__name__}"
        
        # Required fields
        if "tool_name" not in step:
            return False, f"Step {idx} missing required 'tool_name'"
        if "intent" not in step:
            return False, f"Step {idx} missing required 'intent'"
        if "description" not in step:
            return False, f"Step {idx} missing required 'description'"
        
        # Type checks
        if not isinstance(step["tool_name"], str):
            return False, f"Step {idx} 'tool_name' must be string"
        if not isinstance(step["intent"], str):
            return False, f"Step {idx} 'intent' must be string"
        if not isinstance(step["description"], str):
            return False, f"Step {idx} 'description' must be string"
        
        # Non-empty checks
        if not step["tool_name"].strip():
            return False, f"Step {idx} 'tool_name' cannot be empty"
        if not step["intent"].strip():
            return False, f"Step {idx} 'intent' cannot be empty"
        if not step["description"].strip():
            return False, f"Step {idx} 'description' cannot be empty"
    
    return True, None


def _validate_clarification(plan: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate clarification request structure."""
    clarify = plan["clarify"]
    
    if not isinstance(clarify, str):
        return False, f"'clarify' must be string, got {type(clarify).__name__}"
    
    if not clarify.strip():
        return False, "'clarify' cannot be empty"
    
    return True, None


def _validate_delegation(plan: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate delegation request structure."""
    delegate = plan["delegate_to_chat"]
    
    if not isinstance(delegate, str):
        return False, f"'delegate_to_chat' must be string, got {type(delegate).__name__}"
    
    if not delegate.strip():
        return False, "'delegate_to_chat' cannot be empty"
    
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
            "description": "List files in /tmp directory"
        }
    ]
}

EXAMPLE_PLAN_MULTI_STEP = {
    "steps": [
        {
            "tool_name": "run_command",
            "intent": "find Python files in current directory, limit to first 10 results",
            "description": "Find first 10 Python files"
        },
        {
            "tool_name": "run_command",
            "intent": "count lines in all Python files",
            "description": "Count lines in Python files"
        },
        {
            "tool_name": "write_file",
            "intent": "create a file named report.txt with text 'Analysis complete'",
            "description": "Write summary report"
        }
    ]
}

EXAMPLE_PLAN_INVALID_NO_STEPS = {
    "steps": []
}

EXAMPLE_PLAN_INVALID_WRONG_TYPE = {
    "steps": "not an array"
}

EXAMPLE_PLAN_INVALID_MISSING_FIELD = {
    "steps": [
        {
            "tool_name": "run_command",
            "description": "Missing intent field"
        }
    ]
}
