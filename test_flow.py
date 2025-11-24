#!/usr/bin/env python3
"""
Tool Calling Flow Test - Check message formatting and compliance
"""

import json
import os
from groq import Groq

def calculate(expression: str) -> str:
    try:
        result = eval(expression)
        return json.dumps({"result": result})
    except Exception as e:
        return json.dumps({"error": str(e)})

available_functions = {"calculate": calculate}

tools = [{
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Calculate math expression",
        "parameters": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"]
        }
    }
}]

def test_full_flow():
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    messages = [{"role": "user", "content": "What is 25 * 4?"}]

    print("1. Initial request:")
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.1
    )

    print(f"   Finish reason: {response.choices[0].finish_reason}")
    print(f"   Message role: {response.choices[0].message.role}")

    if response.choices[0].message.tool_calls:
        print(f"   Tool calls: {len(response.choices[0].message.tool_calls)}")

        # Check tool call structure
        tc = response.choices[0].message.tool_calls[0]
        print(f"   Tool call ID: {tc.id}")
        print(f"   Tool type: {tc.type}")
        print(f"   Function name: {tc.function.name}")
        print(f"   Arguments: {tc.function.arguments}")

        # Validate JSON
        try:
            args = json.loads(tc.function.arguments)
            print(f"   Parsed args: {args}")
        except:
            print("   ERROR: Invalid JSON in arguments")
            return

        # Add assistant message to conversation
        messages.append(response.choices[0].message)

        print("\n2. Executing tool:")
        function_response = calculate(args["expression"])
        print(f"   Function response: {function_response}")

        # Add tool result
        tool_result = {
            "role": "tool",
            "tool_call_id": tc.id,
            "name": tc.function.name,
            "content": function_response
        }
        messages.append(tool_result)
        print(f"   Tool result message: {tool_result}")

        print("\n3. Final request:")
        final_response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=tools,
            temperature=0.1
        )

        print(f"   Final finish reason: {final_response.choices[0].finish_reason}")
        print(f"   Final message: {final_response.choices[0].message.content}")

        print("\n4. Message history:")
        for i, msg in enumerate(messages):
            print(f"   {i}: {msg['role']} - {msg.get('content', 'N/A')[:50]}...")

if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY"):
        print("Set GROQ_API_KEY")
        exit(1)

    test_full_flow()