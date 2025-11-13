"""
Plan validation for Agent A output

Validates JSON structure and tool availability before execution.
Supports two response types:
1. Execution plan with narration template
2. Direct response (no tools)
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.plan_schema import (
    validate_plan_structure,
    validate_tool_availability,
    detect_response_type
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
        Validate LLM response and extract execution plan or direct response.
        """
        # Phase 1: Parse JSON
        try:
            response = self._parse_json(llm_response)
        except json.JSONDecodeError as e:
            raise PlanValidationError(
                f"Invalid JSON from Agent A: {e}\n\n"
                f"Response was:\n{llm_response[:500]}"
            )
        
        # Phase 2: Validate structure
        valid, error = validate_plan_structure(response)
        if not valid:
            raise PlanValidationError(
                f"Response structure validation failed: {error}\n\n"
                f"Response was:\n{json.dumps(response, indent=2)[:500]}"
            )
        
        # Phase 3: Validate tools (execution plans only)
        response_type = detect_response_type(response)
        if response_type == "execution_plan":
            valid, error = validate_tool_availability(response, self.available_tools)
            if not valid:
                raise PlanValidationError(
                    f"Tool availability validation failed: {error}\n\n"
                    f"Plan was:\n{json.dumps(response, indent=2)[:500]}"
                )
        elif response_type != "response":
            raise PlanValidationError("Unknown response type from Agent A")
        
        return response
    
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
        Validate response and return hints for retry if validation fails.
        
        Args:
            llm_response: Raw text response from Agent A
        
        Returns:
            (response, error_hint) tuple
            - If valid: (response_dict, None)
            - If invalid: (None, error_hint_for_retry)
        
        This is used for retry logic - the error_hint is sent back to Agent A.
        """
        try:
            response = self.validate(llm_response)
            return response, None
        except PlanValidationError as e:
            # Generate helpful error hint for retry
            error_hint = self._generate_retry_hint(str(e))
            return None, error_hint
    
    def _generate_retry_hint(self, error: str) -> str:
        """
        Generate helpful hint for Agent A to fix the response.
        
        Args:
            error: Error message from validation
        
        Returns:
            Hint message to send back to Agent A
        """
        # Extract key error info
        if "Invalid JSON" in error:
            return (
                "Your response was not valid JSON. "
                "Remember: respond with ONLY the JSON, no markdown formatting, "
                "no explanations. Just the JSON object starting with { and ending with }."
            )
        
        if "Response must be one of" in error:
            return (
                f"Response validation failed: {error}\n\n"
                "Choose ONE of the supported response types:\n"
                '1. Execution plan: {"steps": [...], "narration_template": "..."}\n'
                '2. Direct response: {"response": "..."}'
            )
        
        if "missing required" in error.lower():
            return (
                f"Response validation failed: {error}\n\n"
                "Each step must have: tool_name (string), intent (string), output_keys (array of unique strings)."
            )
        
        if "Unknown tool" in error:
            return (
                f"Tool validation failed: {error}\n\n"
                "Use only tools from the available tools list. Check the tool name spelling."
            )
        
        if "must have at least 1 step" in error:
            return (
                "Execution plan must have at least one step. "
                "Create a plan with steps array containing at least one step."
            )
        
        if "max 10" in error.lower():
            return (
                "Plan has too many steps (max 10). "
                "Simplify the plan or use shell pipelines to combine steps."
            )
        
        if "cannot be empty" in error:
            return (
                f"Validation failed: {error}\n\n"
                "All fields must have non-empty values."
            )
        
        # Generic hint
        return (
            f"Response validation failed: {error}\n\n"
            "Please generate a valid JSON response following one of the schemas:\n"
            '1. {"steps": [{"tool_name": "...", "intent": "...", "description": "..."}]}\n'
                '2. {"response": "final message"}'
            )
