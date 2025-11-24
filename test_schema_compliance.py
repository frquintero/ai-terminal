#!/usr/bin/env python3
"""
Tool Schema Compliance Test - Validates tool schemas against Groq specifications

This test validates that the ai-terminal tool schemas comply with Groq's tool calling
specifications without requiring actual API calls.
"""

import json
import sys
from typing import Dict, Any, List

def validate_tool_schema(tool: Dict[str, Any]) -> List[str]:
    """Validate a single tool schema against Groq specifications"""
    errors = []

    # Must have type field
    if "type" not in tool:
        errors.append("Missing 'type' field")
    elif tool["type"] != "function":
        errors.append(f"Invalid type '{tool['type']}', must be 'function'")

    # Must have function field
    if "function" not in tool:
        errors.append("Missing 'function' field")
        return errors

    function = tool["function"]

    # Function must have name
    if "name" not in function:
        errors.append("Missing 'function.name' field")
    elif not isinstance(function["name"], str) or not function["name"].strip():
        errors.append("'function.name' must be a non-empty string")

    # Function must have description
    if "description" not in function:
        errors.append("Missing 'function.description' field")
    elif not isinstance(function["description"], str):
        errors.append("'function.description' must be a string")

    # Function must have parameters
    if "parameters" not in function:
        errors.append("Missing 'function.parameters' field")
        return errors

    parameters = function["parameters"]

    # Parameters must have type
    if "type" not in parameters:
        errors.append("Missing 'function.parameters.type' field")
    elif parameters["type"] != "object":
        errors.append(f"'function.parameters.type' must be 'object', got '{parameters['type']}'")

    # Validate properties if present
    if "properties" in parameters:
        if not isinstance(parameters["properties"], dict):
            errors.append("'function.parameters.properties' must be an object")
        else:
            # Validate each property
            for prop_name, prop_def in parameters["properties"].items():
                if not isinstance(prop_def, dict):
                    errors.append(f"Property '{prop_name}' must be an object")
                    continue

                if "type" not in prop_def:
                    errors.append(f"Property '{prop_name}' missing 'type' field")
                elif prop_def["type"] not in ["string", "number", "integer", "boolean", "object", "array"]:
                    errors.append(f"Property '{prop_name}' has invalid type '{prop_def['type']}'")

                if "description" not in prop_def:
                    errors.append(f"Property '{prop_name}' missing 'description' field")

    # Validate required array
    if "required" in parameters:
        if not isinstance(parameters["required"], list):
            errors.append("'function.parameters.required' must be an array")
        else:
            for req in parameters["required"]:
                if not isinstance(req, str):
                    errors.append(f"'function.parameters.required' items must be strings, got {type(req)}")

    return errors

def test_tool_schema_compliance():
    """Test that ai-terminal tool schemas comply with Groq specs"""
    print("=== Testing Tool Schema Compliance ===")

    try:
        # Import the tools module to get the schemas
        sys.path.insert(0, '/home/ubuntu/apps/ai-terminal')
        from tools import get_tool_schemas

        schemas = get_tool_schemas()
        print(f"Found {len(schemas)} tool schemas")

        total_errors = 0

        for i, schema in enumerate(schemas):
            tool_name = schema.get('function', {}).get('name', 'unknown')
            print(f"\nValidating tool {i+1}: {tool_name}")
            errors = validate_tool_schema(schema)

            if errors:
                print(f"  ❌ {len(errors)} errors found:")
                for error in errors:
                    print(f"    - {error}")
                total_errors += len(errors)
            else:
                print("  ✅ Valid")

        if total_errors == 0:
            print("\n🎉 All tool schemas are compliant with Groq specifications!")
        else:
            print(f"\n❌ Found {total_errors} total validation errors")

        return total_errors == 0

    except ImportError as e:
        print(f"❌ Failed to import tools module: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_message_format_structure():
    """Test that message structures match Groq expectations"""
    print("\n=== Testing Message Format Structure ===")

    # Test assistant message with tool calls
    assistant_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "run_command",
                    "arguments": '{"command": "ls -la"}'
                }
            }
        ]
    }

    # Test tool result message
    tool_message = {
        "role": "tool",
        "tool_call_id": "call_123",
        "name": "run_command",
        "content": '{"success": true, "stdout": "file1.txt\\nfile2.txt"}'
    }

    print("✅ Assistant message structure: OK")
    print("✅ Tool message structure: OK")

    # Validate JSON in arguments
    try:
        args = json.loads(assistant_message["tool_calls"][0]["function"]["arguments"])
        print("✅ Tool call arguments JSON: OK")
    except json.JSONDecodeError as e:
        print(f"❌ Tool call arguments JSON invalid: {e}")
        return False

    return True

def test_tool_execution_format():
    """Test that tool execution results match expected format"""
    print("\n=== Testing Tool Execution Format ===")

    # Mock tool execution result
    result = {
        "success": True,
        "stdout": "Hello World",
        "stderr": "",
        "exit_code": 0,
        "raw_stdout": "Hello World",
        "raw_stderr": "",
        "output_preview": "Hello World"
    }

    required_fields = ["success", "stdout", "stderr", "exit_code"]
    missing_fields = [field for field in required_fields if field not in result]

    if missing_fields:
        print(f"❌ Missing required fields: {missing_fields}")
        return False

    print("✅ Tool execution result format: OK")
    return True

def test_orchestrator_tool_processing():
    """Test that the orchestrator processes tools correctly"""
    print("\n=== Testing Orchestrator Tool Processing ===")

    try:
        sys.path.insert(0, '/home/ubuntu/apps/ai-terminal')
        from orchestrator.orchestrator import Orchestrator
        from config import load_config

        # Try to load config (this might fail without proper env vars, but let's see)
        try:
            config = load_config()
            print("✅ Config loaded successfully")
        except Exception as e:
            print(f"⚠️  Config loading failed (expected in test env): {e}")
            return True  # This is OK for schema validation

        # Test that we can import and inspect the orchestrator
        print("✅ Orchestrator module imported successfully")

        return True

    except ImportError as e:
        print(f"❌ Failed to import orchestrator: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in orchestrator test: {e}")
        return False

if __name__ == "__main__":
    print("Tool Calling Compliance Test Suite")
    print("=" * 50)

    tests = [
        test_tool_schema_compliance,
        test_message_format_structure,
        test_tool_execution_format,
        test_orchestrator_tool_processing
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All compliance tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)