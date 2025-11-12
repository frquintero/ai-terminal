"""
Unit tests for plan validation (Phase 3)

Tests:
- Plan schema validation
- JSON parsing from LLM responses
- Tool availability checking
- Retry hint generation
"""

import json
import unittest

from orchestrator.plan_schema import (
    validate_plan_structure,
    validate_tool_availability,
    EXAMPLE_PLAN_SIMPLE,
    EXAMPLE_PLAN_MULTI_STEP,
    EXAMPLE_PLAN_INVALID_NO_STEPS,
    EXAMPLE_PLAN_INVALID_WRONG_TYPE,
    EXAMPLE_PLAN_INVALID_MISSING_FIELD
)
from orchestrator.plan_validator import PlanValidator, PlanValidationError


class TestPlanStructureValidation(unittest.TestCase):
    """Test plan_schema.validate_plan_structure()"""
    
    def test_valid_simple_plan(self):
        """Valid single-step plan passes"""
        valid, error = validate_plan_structure(EXAMPLE_PLAN_SIMPLE)
        self.assertTrue(valid)
        self.assertIsNone(error)
    
    def test_valid_multi_step_plan(self):
        """Valid multi-step plan passes"""
        valid, error = validate_plan_structure(EXAMPLE_PLAN_MULTI_STEP)
        self.assertTrue(valid)
        self.assertIsNone(error)
    
    def test_invalid_no_steps(self):
        """Empty steps array fails"""
        valid, error = validate_plan_structure(EXAMPLE_PLAN_INVALID_NO_STEPS)
        self.assertFalse(valid)
        self.assertIn("at least 1 step", error)
    
    def test_invalid_wrong_type(self):
        """Steps as string instead of array fails"""
        valid, error = validate_plan_structure(EXAMPLE_PLAN_INVALID_WRONG_TYPE)
        self.assertFalse(valid)
        self.assertIn("must be array", error)
    
    def test_invalid_missing_field(self):
        """Step missing required tool_args fails"""
        valid, error = validate_plan_structure(EXAMPLE_PLAN_INVALID_MISSING_FIELD)
        self.assertFalse(valid)
        self.assertIn("missing required 'tool_args'", error)
    
    def test_invalid_not_dict(self):
        """Plan as list fails"""
        valid, error = validate_plan_structure(["not", "a", "dict"])
        self.assertFalse(valid)
        self.assertIn("Plan must be object", error)
    
    def test_invalid_missing_steps_key(self):
        """Plan without 'steps' key fails"""
        valid, error = validate_plan_structure({"wrong": "key"})
        self.assertFalse(valid)
        self.assertIn("missing required 'steps'", error)
    
    def test_invalid_too_many_steps(self):
        """Plan with >10 steps fails"""
        many_steps = {
            "steps": [
                {
                    "tool_name": "run_command",
                    "tool_args": {"command": f"echo step{i}"},
                    "description": f"Step {i}"
                }
                for i in range(11)
            ]
        }
        valid, error = validate_plan_structure(many_steps)
        self.assertFalse(valid)
        self.assertIn("max 10", error)
    
    def test_invalid_empty_tool_name(self):
        """Empty tool_name fails"""
        plan = {
            "steps": [{
                "tool_name": "",
                "tool_args": {},
                "description": "Test"
            }]
        }
        valid, error = validate_plan_structure(plan)
        self.assertFalse(valid)
        self.assertIn("cannot be empty", error)
    
    def test_invalid_tool_args_not_object(self):
        """tool_args as string fails"""
        plan = {
            "steps": [{
                "tool_name": "test",
                "tool_args": "not an object",
                "description": "Test"
            }]
        }
        valid, error = validate_plan_structure(plan)
        self.assertFalse(valid)
        self.assertIn("'tool_args' must be object", error)


class TestToolAvailabilityValidation(unittest.TestCase):
    """Test plan_schema.validate_tool_availability()"""
    
    def test_valid_available_tools(self):
        """Plan with all available tools passes"""
        plan = EXAMPLE_PLAN_SIMPLE
        available = ["run_command", "write_file", "read_file"]
        valid, error = validate_tool_availability(plan, available)
        self.assertTrue(valid)
        self.assertIsNone(error)
    
    def test_invalid_unknown_tool(self):
        """Plan with unknown tool fails"""
        plan = {
            "steps": [{
                "tool_name": "unknown_tool",
                "tool_args": {},
                "description": "Test"
            }]
        }
        available = ["run_command", "write_file"]
        valid, error = validate_tool_availability(plan, available)
        self.assertFalse(valid)
        self.assertIn("Unknown tool 'unknown_tool'", error)
    
    def test_multi_step_all_available(self):
        """Multi-step plan with all tools available passes"""
        plan = EXAMPLE_PLAN_MULTI_STEP
        available = ["run_command", "write_file", "read_file"]
        valid, error = validate_tool_availability(plan, available)
        self.assertTrue(valid)
        self.assertIsNone(error)


class TestPlanValidatorParsing(unittest.TestCase):
    """Test PlanValidator._parse_json()"""
    
    def setUp(self):
        self.validator = PlanValidator(available_tools=["run_command"])
    
    def test_parse_clean_json(self):
        """Parse clean JSON without markup"""
        json_str = '{"steps": [{"tool_name": "run_command", "tool_args": {}, "description": "Test"}]}'
        result = self.validator._parse_json(json_str)
        self.assertIsInstance(result, dict)
        self.assertIn("steps", result)
    
    def test_parse_markdown_code_block(self):
        """Parse JSON from ```json markdown block"""
        text = '''Here is the plan:
```json
{"steps": [{"tool_name": "run_command", "tool_args": {}, "description": "Test"}]}
```
Hope this helps!'''
        result = self.validator._parse_json(text)
        self.assertIsInstance(result, dict)
        self.assertIn("steps", result)
    
    def test_parse_generic_code_block(self):
        """Parse JSON from generic ``` code block"""
        text = '''```
{"steps": [{"tool_name": "run_command", "tool_args": {}, "description": "Test"}]}
```'''
        result = self.validator._parse_json(text)
        self.assertIsInstance(result, dict)
        self.assertIn("steps", result)
    
    def test_parse_with_surrounding_text(self):
        """Extract JSON from text with explanations"""
        text = '''Let me create a plan for you.
{"steps": [{"tool_name": "run_command", "tool_args": {}, "description": "Test"}]}
This should work!'''
        result = self.validator._parse_json(text)
        self.assertIsInstance(result, dict)
        self.assertIn("steps", result)
    
    def test_parse_invalid_json_fails(self):
        """Invalid JSON raises JSONDecodeError"""
        with self.assertRaises(json.JSONDecodeError):
            self.validator._parse_json("not valid json at all")


class TestPlanValidatorFullValidation(unittest.TestCase):
    """Test PlanValidator.validate() end-to-end"""
    
    def setUp(self):
        self.validator = PlanValidator(available_tools=["run_command", "write_file"])
    
    def test_validate_success(self):
        """Valid plan JSON passes full validation"""
        json_str = json.dumps({
            "steps": [{
                "tool_name": "run_command",
                "tool_args": {"command": "ls"},
                "description": "List files"
            }]
        })
        plan = self.validator.validate(json_str)
        self.assertIsInstance(plan, dict)
        self.assertEqual(len(plan["steps"]), 1)
    
    def test_validate_invalid_json(self):
        """Invalid JSON raises PlanValidationError"""
        with self.assertRaises(PlanValidationError) as ctx:
            self.validator.validate("not json")
        self.assertIn("Invalid JSON", str(ctx.exception))
    
    def test_validate_invalid_structure(self):
        """Invalid structure raises PlanValidationError"""
        json_str = json.dumps({"steps": []})  # Empty steps
        with self.assertRaises(PlanValidationError) as ctx:
            self.validator.validate(json_str)
        self.assertIn("structure validation failed", str(ctx.exception))
    
    def test_validate_unknown_tool(self):
        """Unknown tool raises PlanValidationError"""
        json_str = json.dumps({
            "steps": [{
                "tool_name": "unknown_tool",
                "tool_args": {},
                "description": "Test"
            }]
        })
        with self.assertRaises(PlanValidationError) as ctx:
            self.validator.validate(json_str)
        self.assertIn("Tool availability validation failed", str(ctx.exception))


class TestPlanValidatorRetryHints(unittest.TestCase):
    """Test PlanValidator retry hint generation"""
    
    def setUp(self):
        self.validator = PlanValidator(available_tools=["run_command"])
    
    def test_hints_for_invalid_json(self):
        """Invalid JSON returns helpful hint"""
        plan, hint = self.validator.validate_with_hints("not json")
        self.assertIsNone(plan)
        self.assertIn("not valid JSON", hint)
        self.assertIn("no markdown", hint)
    
    def test_hints_for_missing_field(self):
        """Missing field returns helpful hint"""
        json_str = json.dumps({
            "steps": [{
                "tool_name": "run_command",
                "description": "Missing tool_args"
            }]
        })
        plan, hint = self.validator.validate_with_hints(json_str)
        self.assertIsNone(plan)
        self.assertIn("missing required", hint)
    
    def test_hints_for_unknown_tool(self):
        """Unknown tool returns helpful hint"""
        json_str = json.dumps({
            "steps": [{
                "tool_name": "fake_tool",
                "tool_args": {},
                "description": "Test"
            }]
        })
        plan, hint = self.validator.validate_with_hints(json_str)
        self.assertIsNone(plan)
        self.assertIn("Unknown tool", hint)
    
    def test_hints_for_empty_steps(self):
        """Empty steps returns helpful hint"""
        json_str = json.dumps({"steps": []})
        plan, hint = self.validator.validate_with_hints(json_str)
        self.assertIsNone(plan)
        self.assertIn("at least one step", hint)
    
    def test_hints_for_too_many_steps(self):
        """Too many steps returns helpful hint"""
        json_str = json.dumps({
            "steps": [
                {"tool_name": "run_command", "tool_args": {}, "description": f"Step {i}"}
                for i in range(11)
            ]
        })
        plan, hint = self.validator.validate_with_hints(json_str)
        self.assertIsNone(plan)
        self.assertIn("too many steps", hint)
    
    def test_no_hint_for_valid_plan(self):
        """Valid plan returns plan and no hint"""
        json_str = json.dumps({
            "steps": [{
                "tool_name": "run_command",
                "tool_args": {"command": "ls"},
                "description": "List files"
            }]
        })
        plan, hint = self.validator.validate_with_hints(json_str)
        self.assertIsNotNone(plan)
        self.assertIsNone(hint)


if __name__ == "__main__":
    unittest.main()
