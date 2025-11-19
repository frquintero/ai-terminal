"""
Plan Validator - Validates Agent A's JSON output.

Ensures the plan adheres to the schema defined in plan_schema.py.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.plan_schema import validate_plan_structure, validate_tool_availability


class PlanValidationError(Exception):
    """Raised when plan validation fails."""
    pass


class PlanValidator:
    """
    Validates execution plans from Agent A.
    
    Usage:
        validator = PlanValidator(available_tools=["run_command", ...])
        plan, error = validator.validate_with_hints(json_string)
    """
    
    def __init__(self, available_tools: List[str]):
        self.available_tools = available_tools
    
    def validate_with_hints(self, json_text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Parse and validate JSON plan, returning helpful error hints if invalid.
        
        Args:
            json_text: Raw JSON string from LLM
            
        Returns:
            (plan_dict, None) if valid
            (None, error_hint_string) if invalid
        """
        # 1. Parse JSON
        try:
            plan = self._parse_json(json_text)
        except json.JSONDecodeError as e:
            return None, f"Invalid JSON format: {str(e)}"
        except ValueError as e:
            return None, str(e)
            
        # 2. Validate Structure
        valid_structure, struct_error = validate_plan_structure(plan)
        if not valid_structure:
            return None, f"Schema violation: {struct_error}"
            
        # 3. Validate Tools (only for execution plans)
        if "steps" in plan:
            valid_tools, tool_error = validate_tool_availability(plan, self.available_tools)
            if not valid_tools:
                return None, f"Tool error: {tool_error}"
        
        return plan, None

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """
        Robust JSON parsing that handles markdown code blocks.
        """
        import re
        
        # Remove <think> blocks
        clean_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # Extract from markdown blocks if present
        matches = re.findall(r'```json\s*(.*?)\s*```', clean_text, re.DOTALL)
        if matches:
            # Use the last block (allows for scratchpad blocks)
            json_text = matches[-1].strip()
        else:
            # Fallback: try to find generic code blocks
            matches = re.findall(r'```\s*(\{.*?\})\s*```', clean_text, re.DOTALL)
            if matches:
                json_text = matches[-1].strip()
            else:
                # Try to parse the raw text if it looks like JSON
                json_text = clean_text.strip()
                if not (json_text.startswith('{') and json_text.endswith('}')):
                     raise ValueError("No JSON object found in response (must start with { and end with })")

        return json.loads(json_text)
