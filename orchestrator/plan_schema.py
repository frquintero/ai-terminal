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
    "required": ["segments", "policy_contract", "policy_summary"],
    "properties": {
        "segments": {
            "type": "array",
            "description": "Ordered list of response segments rendered to the user.",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["text", "block", "inline_value"]},
                    "text": {"type": "string"},
                    "body": {"type": "string"},
                    "fence": {"type": "string"},
                    "title": {"type": "string"},
                    "truncated": {"type": "string"},
                    "metadata": {"type": "object"}
                },
                "required": ["kind"]
            }
        },
        "policy_contract": {
            "type": "object",
            "description": "Structured summary of deterministic policy verdicts.",
            "properties": {
                "rules": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "status": {"type": "string"},
                            "details": {"type": "string"}
                        },
                        "required": ["id", "status"]
                    }
                },
                "notes": {"type": "string"}
            },
            "required": ["rules"]
        },
        "policy_summary": {
            "type": "string",
            "description": "One-sentence recap of the enforced policy status."
        },
        "attachments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "description": {"type": "string"},
                    "content_type": {"type": "string"}
                }
            }
        },
        "template_values": {
            "type": "object",
            "description": "Optional scalar values already computed."
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
    if "segments" in plan:
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
    segments = plan.get("segments")
    if not isinstance(segments, list) or not segments:
        return False, "'segments' must be a non-empty array"
    for idx, segment in enumerate(segments):
        if not isinstance(segment, dict):
            return False, f"Segment {idx} must be an object"
        kind = segment.get("kind")
        if kind not in {"text", "block", "inline_value"}:
            return False, f"Segment {idx} has invalid 'kind': {kind}"

    policy_contract = plan.get("policy_contract")
    if not isinstance(policy_contract, dict):
        return False, "'policy_contract' must be an object"
    rules = policy_contract.get("rules")
    if not isinstance(rules, list) or not rules:
        return False, "'policy_contract.rules' must be a non-empty array"
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            return False, f"policy_contract.rules[{idx}] must be an object"
        rule_id = rule.get("id")
        status = rule.get("status")
        if not isinstance(rule_id, str) or not rule_id.strip():
            return False, f"policy_contract.rules[{idx}].id must be a non-empty string"
        if not isinstance(status, str) or not status.strip():
            return False, f"policy_contract.rules[{idx}].status must be a non-empty string"

    policy_summary = plan.get("policy_summary")
    if not isinstance(policy_summary, str) or not policy_summary.strip():
        return False, "'policy_summary' must be a non-empty string"

    attachments = plan.get("attachments")
    if attachments is not None and not isinstance(attachments, list):
        return False, "'attachments' must be an array when provided"

    template_values = plan.get("template_values")
    if template_values is not None and not isinstance(template_values, dict):
        return False, "'template_values' must be an object when provided"
    
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

EXAMPLE_PLAN_MULTI_STEP = {
    "intent": "List files and check disk usage",
    "success_criteria": [
        "File listing completes",
        "Disk usage is reported"
    ]
}

EXAMPLE_PLAN_INVALID_NO_STEPS = {
    "intent": "",
    "success_criteria": []
}

EXAMPLE_PLAN_INVALID_MISSING_FIELD = {
    "intent": "Test missing field"
}

EXAMPLE_PLAN_INVALID_WRONG_TYPE = {
    "intent": 123,
    "success_criteria": "not-an-array"
}
