"""
Plan validation for Agent A output

Validates JSON structure and tool availability before execution.
Two-phase validation:
1. JSON parsing + structure validation
2. Tool availability check
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.plan_schema import (
    validate_plan_structure,
    validate_tool_availability
)


class PlanValidationError(Exception):
    """Raised when plan validation fails"""
    pass


class PlanValidator:
    """
    Validates Agent A plans before execution.
    
    Usage:
        validator = PlanValidator(available_tools=["run_command", "write_file"])
        plan = validator.validate(llm_response)
    """
    
    def __init__(self, available_tools: List[str]):
        """
        Initialize validator with available tools.
        
        Args:
            available_tools: List of tool names from TOOLS.keys()
        """
        self.available_tools = available_tools
    
    def validate(self, llm_response: str) -> Dict[str, Any]:
        """
        Validate LLM response and extract plan.
        
        Args:
            llm_response: Raw text response from Agent A
        
        Returns:
            Validated plan dict
        
        Raises:
            PlanValidationError: If validation fails
        
        Process:
        1. Parse JSON from response
        2. Validate structure
        3. Validate tool availability
        """
        # Phase 1: Parse JSON
        try:
            plan = self._parse_json(llm_response)
        except json.JSONDecodeError as e:
            raise PlanValidationError(
                f"Invalid JSON from Agent A: {e}\n\n"
                f"Response was:\n{llm_response[:500]}"
            )
        
        # Phase 2: Validate structure
        valid, error = validate_plan_structure(plan)
        if not valid:
            raise PlanValidationError(
                f"Plan structure validation failed: {error}\n\n"
                f"Plan was:\n{json.dumps(plan, indent=2)[:500]}"
            )
        
        # Phase 3: Validate tools
        valid, error = validate_tool_availability(plan, self.available_tools)
        if not valid:
            raise PlanValidationError(
                f"Tool availability validation failed: {error}\n\n"
                f"Plan was:\n{json.dumps(plan, indent=2)[:500]}"
            )
        
        return plan
    
    def _parse_json(self, text: str) -> Any:
        """
        Parse JSON from LLM response, handling common issues.
        
        LLMs sometimes wrap JSON in markdown code blocks or add explanations.
        This attempts to extract just the JSON portion.
        
        Args:
            text: Raw LLM response
        
        Returns:
            Parsed JSON object
        
        Raises:
            json.JSONDecodeError: If JSON cannot be parsed
        """
        # Strip whitespace
        text = text.strip()
        
        # Try direct parse first (happy path)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code block
        if "```json" in text:
            # Extract content between ```json and ```
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                json_text = text[start:end].strip()
                return json.loads(json_text)
        
        # Try extracting from generic code block
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                json_text = text[start:end].strip()
                return json.loads(json_text)
        
        # Try finding first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_text = text[start:end+1]
            return json.loads(json_text)
        
        # Give up, let JSONDecodeError propagate
        return json.loads(text)
    
    def validate_with_hints(self, llm_response: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Validate plan and return hints for retry if validation fails.
        
        Args:
            llm_response: Raw text response from Agent A
        
        Returns:
            (plan, error_hint) tuple
            - If valid: (plan_dict, None)
            - If invalid: (None, error_hint_for_retry)
        
        This is used for retry logic - the error_hint is sent back to Agent A.
        """
        try:
            plan = self.validate(llm_response)
            return plan, None
        except PlanValidationError as e:
            # Generate helpful error hint for retry
            error_hint = self._generate_retry_hint(str(e))
            return None, error_hint
    
    def _generate_retry_hint(self, error: str) -> str:
        """
        Generate helpful hint for Agent A to fix the plan.
        
        Args:
            error: Error message from validation
        
        Returns:
            Hint message to send back to Agent A
        """
        # Extract key error info
        if "Invalid JSON" in error:
            return (
                "Your response was not valid JSON. "
                "Remember: respond with ONLY the JSON plan, no markdown formatting, "
                "no explanations. Just the JSON object starting with { and ending with }."
            )
        
        if "missing required" in error.lower():
            return (
                f"Plan validation failed: {error}\n\n"
                "Each step must have: tool_name (string), intent (string), description (string)."
            )
        
        if "Unknown tool" in error:
            return (
                f"Plan validation failed: {error}\n\n"
                "Use only tools from the available tools list. Check the tool name spelling."
            )
        
        if "must have at least 1 step" in error:
            return (
                "Plan must have at least one step. "
                "Create a plan with steps array containing at least one step."
            )
        
        if "max 10" in error.lower():
            return (
                "Plan has too many steps (max 10). "
                "Simplify the plan or use shell pipelines to combine steps."
            )
        
        # Generic hint
        return (
            f"Plan validation failed: {error}\n\n"
            "Please generate a valid JSON plan following the schema:\n"
            '{"steps": [{"tool_name": "...", "intent": "...", "description": "..."}]}'
        )
