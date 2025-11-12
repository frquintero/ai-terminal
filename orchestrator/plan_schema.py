"""
Plan JSON schema and validation for Agent A (Planner)

Defines the structure that Agent A must generate for multi-step tasks.
Schema is designed to be:
- Simple enough for LLM to generate reliably (95%+ success)
- Expressive enough to capture multi-step workflows
- Aligned with "Shell-First" philosophy (prefer single shell commands over multi-step plans)
"""

from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Plan JSON Schema
# ============================================================================

PLAN_SCHEMA = {
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


# ============================================================================
# Validation Functions
# ============================================================================

def validate_plan_structure(plan: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate plan structure against schema.
    
    Args:
        plan: Parsed JSON object from Agent A
    
    Returns:
        (valid: bool, error_message: Optional[str])
    
    Does NOT validate tool existence - that's done separately by validator.
    """
    # Must be dict
    if not isinstance(plan, dict):
        return False, f"Plan must be object, got {type(plan).__name__}"
    
    # Must have 'steps' key
    if "steps" not in plan:
        return False, "Plan missing required 'steps' array"
    
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
