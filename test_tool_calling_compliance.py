#!/usr/bin/env python3
"""
Tool Calling Compliance Test

Tests specific compliance with Groq tool calling specifications,
checking message formats, tool call structures, and error handling.
"""

import json
import os
from typing import Dict, Any, List
from groq import Groq

# Initialize Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def simple_calculator(expression: str) -> str:
    """Simple calculator that returns JSON"""
    try:
        result = eval(expression)
        return json.dumps({"result": result, "expression": expression})
    except Exception as e:
        return json.dumps({"error": str(e), "expression": expression})

def get_weather(location: str, unit: str = "celsius") -> str:
    """Weather function with multiple parameters"""
    mock_weather = {
        "New York": {"temp_c": 22, "temp_f": 72, "condition": "Sunny"},
        "London": {"temp_c": 18, "temp_f": 64, "condition": "Rainy"},
        "Tokyo": {"temp_c": 26, "temp_f": 79, "condition": "Cloudy"}
    }

    if location in mock_weather:
        data = mock_weather[location]
        if unit == "fahrenheit":
            temp = data["temp_f"]
        else:
            temp = data["temp_c"]
        return json.dumps({
            "location": location,
            "temperature": temp,
            "unit": unit,
            "condition": data["condition"]
        })
    return json.dumps({"error": "Location not found", "location": location})

# Function registry
available_functions = {
    "simple_calculator": simple_calculator,
    "get_weather": get_weather,
}

# Tool schemas following Groq specs exactly
tools = [
    {
        "type": "function",
        "function": {
            "name": "simple_calculator",
            "description": "Evaluate a mathematical expression and return the result",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate (e.g., '25 * 4 + 10')"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather information for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city name (e.g., 'New York', 'London', 'Tokyo')"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit (default: celsius)"
                    }
                },
                "required": ["location"]
            }
        }
    }
]

def test_tool_call_structure():
    """Test that tool calls have the correct structure per Groq specs"""
    print("=== Testing Tool Call Structure ===")

    messages = [
        {"role": "user", "content": "What is 15 + 27?"}
    ]

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.1
    )

    # Validate response structure
    assert response.choices[0].finish_reason == "tool_calls", f"Expected finish_reason 'tool_calls', got '{response.choices[0].finish_reason}'"

    message = response.choices[0].message
    assert message.role == "assistant", f"Expected role 'assistant', got '{message.role}'"
    assert hasattr(message, 'tool_calls'), "Message should have tool_calls attribute"
    assert message.tool_calls is not None, "tool_calls should not be None"
    assert len(message.tool_calls) > 0, "Should have at least one tool call"

    # Validate tool call structure
    for tc in message.tool_calls:
        assert tc.id is not None, "Tool call should have an id"
        assert tc.type == "function", f"Expected type 'function', got '{tc.type}'"
        assert hasattr(tc, 'function'), "Tool call should have function attribute"
        assert tc.function.name in available_functions, f"Unknown function: {tc.function.name}"

        # Test JSON parsing of arguments
        try:
            args = json.loads(tc.function.arguments)
            assert isinstance(args, dict), "Arguments should parse to a dict"
        except json.JSONDecodeError as e:
            assert False, f"Invalid JSON in arguments: {e}"

    print("✓ Tool call structure is valid")
    return response

def test_tool_execution_and_response():
    """Test complete tool execution and response formatting"""
    print("\n=== Testing Tool Execution and Response ===")

    messages = [
        {"role": "user", "content": "Calculate 15 + 27"}
    ]

    # Get tool calls
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.1
    )

    # Add assistant message to conversation
    messages.append(response.choices[0].message)

    # Execute tools and build tool result messages
    tool_results = []
    for tc in response.choices[0].message.tool_calls:
        function_name = tc.function.name
        function_args = json.loads(tc.function.arguments)

        print(f"Executing: {function_name}({function_args})")

        function_to_call = available_functions[function_name]
        function_response = function_to_call(**function_args)

        print(f"Response: {function_response}")

        # Validate function response is valid JSON
        try:
            parsed_response = json.loads(function_response)
            assert isinstance(parsed_response, dict), "Function response should be a JSON object"
        except json.JSONDecodeError as e:
            assert False, f"Function returned invalid JSON: {e}"

        # Build tool result message per Groq specs
        tool_result = {
            "role": "tool",
            "tool_call_id": tc.id,
            "name": tc.function.name,
            "content": function_response
        }
        tool_results.append(tool_result)

    # Add tool results to messages
    messages.extend(tool_results)

    # Get final response
    final_response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        temperature=0.1
    )

    final_message = final_response.choices[0].message
    assert final_message.role == "assistant", f"Expected role 'assistant', got '{final_message.role}'"
    assert final_message.content is not None, "Final response should have content"
    assert not hasattr(final_message, 'tool_calls') or final_message.tool_calls is None, "Final response should not have tool_calls"

    print(f"✓ Final response: {final_message.content}")
    return final_response

def test_parallel_tool_calls():
    """Test parallel tool calls (multiple tools in one request)"""
    print("\n=== Testing Parallel Tool Calls ===")

    messages = [
        {"role": "user", "content": "Calculate 10 + 5 and get weather for New York"}
    ]

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.1
    )

    message = response.choices[0].message
    assert hasattr(message, 'tool_calls') and message.tool_calls, "Should have tool calls"

    tool_calls = message.tool_calls
    print(f"Number of parallel tool calls: {len(tool_calls)}")

    # Should call both calculator and weather
    function_names = {tc.function.name for tc in tool_calls}
    assert "simple_calculator" in function_names, "Should call calculator"
    assert "get_weather" in function_names, "Should call weather"

    # Add assistant message
    messages.append(message)

    # Execute all tools
    tool_results = []
    for tc in tool_calls:
        function_name = tc.function.name
        function_args = json.loads(tc.function.arguments)

        function_to_call = available_functions[function_name]
        function_response = function_to_call(**function_args)

        tool_results.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "name": tc.function.name,
            "content": function_response
        })

    messages.extend(tool_results)

    # Get final response
    final_response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        temperature=0.1
    )

    print(f"✓ Parallel execution completed: {final_response.choices[0].message.content}")
    return final_response

def test_tool_choice_control():
    """Test tool_choice parameter control"""
    print("\n=== Testing Tool Choice Control ===")

    messages = [
        {"role": "user", "content": "Hello, how are you?"}
    ]

    # Test tool_choice="none"
    response_none = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        tool_choice="none",
        temperature=0.1
    )

    message_none = response_none.choices[0].message
    assert not hasattr(message_none, 'tool_calls') or message_none.tool_calls is None, "Should not have tool calls with tool_choice='none'"
    assert message_none.content is not None, "Should have direct response"

    print("✓ tool_choice='none' works correctly")

    # Test tool_choice="required"
    response_required = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        tool_choice="required",
        temperature=0.1
    )

    message_required = response_required.choices[0].message
    assert hasattr(message_required, 'tool_calls') and message_required.tool_calls, "Should have tool calls with tool_choice='required'"

    print("✓ tool_choice='required' works correctly")

def test_error_scenarios():
    """Test error handling scenarios"""
    print("\n=== Testing Error Scenarios ===")

    # Test with invalid tool arguments
    messages = [
        {"role": "user", "content": "Calculate something invalid"}
    ]

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.1
    )

    if response.choices[0].message.tool_calls:
        messages.append(response.choices[0].message)

        for tc in response.choices[0].message.tool_calls:
            if tc.function.name == "simple_calculator":
                # Simulate function error
                error_response = json.dumps({"error": "Invalid expression"})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": error_response
                })

        # Get response after error
        final_response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=tools,
            temperature=0.1
        )

        print(f"✓ Error handling response: {final_response.choices[0].message.content}")

def run_compliance_tests():
    """Run all compliance tests"""
    print("Running Groq Tool Calling Compliance Tests")
    print("=" * 50)

    try:
        test_tool_call_structure()
        test_tool_execution_and_response()
        test_parallel_tool_calls()
        test_tool_choice_control()
        test_error_scenarios()

        print("\n" + "=" * 50)
        print("✅ All compliance tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise

if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY"):
        print("Please set GROQ_API_KEY environment variable")
        exit(1)

    run_compliance_tests()</content>
<parameter name="filePath">/home/ubuntu/apps/ai-terminal/test_tool_calling_compliance.py