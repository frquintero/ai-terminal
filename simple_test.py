#!/usr/bin/env python3
"""
Simple Tool Calling Test
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

if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY"):
        print("Set GROQ_API_KEY")
        exit(1)

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    messages = [{"role": "user", "content": "What is 25 * 4?"}]

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.1
    )

    print(f"Finish reason: {response.choices[0].finish_reason}")

    if response.choices[0].message.tool_calls:
        print("Tool calls found")
        for tc in response.choices[0].message.tool_calls:
            print(f"Tool: {tc.function.name}, Args: {tc.function.arguments}")
    else:
        print("No tool calls")