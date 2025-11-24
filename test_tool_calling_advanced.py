#!/usr/bin/env python3
"""
Advanced Tool Calling Test - AI Terminal Style

Tests tool calling patterns similar to the ai-terminal implementation,
including agentic loops and structured responses.
"""

import json
import os
from typing import Dict, Any, List
from groq import Groq

# Initialize Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Mock tools similar to ai-terminal
def run_command(command: str) -> str:
    """Mock command execution"""
    if "ls" in command:
        return json.dumps({
            "success": True,
            "stdout": "file1.txt\nfile2.txt\ndirectory/",
            "stderr": "",
            "exit_code": 0
        })
    elif "echo" in command:
        output = command.replace("echo ", "")
        return json.dumps({
            "success": True,
            "stdout": output,
            "stderr": "",
            "exit_code": 0
        })
    else:
        return json.dumps({
            "success": False,
            "stdout": "",
            "stderr": f"command not found: {command}",
            "exit_code": 127
        })

def read_file(file_path: str) -> str:
    """Mock file reading"""
    mock_files = {
        "test.txt": "Hello World\nThis is a test file.",
        "config.json": '{"setting": "value", "number": 42}'
    }

    if file_path in mock_files:
        return json.dumps({
            "success": True,
            "content": mock_files[file_path]
        })
    else:
        return json.dumps({
            "success": False,
            "error": f"File not found: {file_path}"
        })

def respond_to_user(segments: List[Dict], policy_contract: Dict, policy_summary: str) -> str:
    """Mock respond_to_user tool"""
    return json.dumps({
        "segments": segments,
        "policy_contract": policy_contract,
        "policy_summary": policy_summary,
        "final_response": True
    })

# Function registry
available_functions = {
    "run_command": run_command,
    "read_file": read_file,
    "respond_to_user": respond_to_user,
}

# Tool schemas (simplified versions of ai-terminal tools)
tools = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to read"
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "respond_to_user",
            "description": "Deliver the final user-facing response",
            "parameters": {
                "type": "object",
                "properties": {
                    "segments": {
                        "type": "array",
                        "description": "Response segments",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["text", "block"]},
                                "text": {"type": "string"},
                                "body": {"type": "string"},
                                "fence": {"type": "string"}
                            }
                        }
                    },
                    "policy_contract": {
                        "type": "object",
                        "description": "Policy compliance information"
                    },
                    "policy_summary": {
                        "type": "string",
                        "description": "Summary of policy checks"
                    }
                },
                "required": ["segments", "policy_contract", "policy_summary"]
            }
        }
    }
]

def test_agentic_loop():
    """Test agentic loop similar to Agent B in ai-terminal"""
    print("=== Testing Agentic Loop (Agent B Style) ===")

    # System prompt similar to Agent B
    system_prompt = """
You are Agent B, an expert system administrator. You execute tasks using available tools.
When you have completed the task, call respond_to_user with structured segments.
"""

    # User message with intent (similar to Agent A delegation)
    user_message = """
Intent: List files in current directory and show contents of test.txt
Success Criteria: Files are listed and test.txt content is displayed
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1
        )

        assistant_message = response.choices[0].message
        print(f"Assistant: {assistant_message.content or 'No content'}")

        # Add assistant message to conversation
        messages.append(assistant_message)

        if not assistant_message.tool_calls:
            print("No tool calls - ending loop")
            break

        # Execute tools
        for tool_call in assistant_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            print(f"Executing: {function_name}")
            print(f"Args: {function_args}")

            function_to_call = available_functions[function_name]

            # Handle different argument patterns
            if function_name == "respond_to_user":
                result = function_to_call(
                    function_args.get("segments", []),
                    function_args.get("policy_contract", {}),
                    function_args.get("policy_summary", "")
                )
            else:
                result = function_to_call(**function_args)

            print(f"Result: {result}")

            # Check if this is respond_to_user
            if function_name == "respond_to_user":
                print("respond_to_user called - ending execution")
                return result

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": result
            })

    print("Max iterations reached")
    return None

def test_error_handling():
    """Test error handling in tool calls"""
    print("\n=== Testing Error Handling ===")

    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Use tools and handle errors gracefully."
        },
        {
            "role": "user",
            "content": "Read the contents of nonexistent.txt"
        }
    ]

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.1
    )

    print(f"Assistant: {response.choices[0].message.content or 'No content'}")

    if response.choices[0].message.tool_calls:
        messages.append(response.choices[0].message)

        for tool_call in response.choices[0].message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            print(f"Executing: {function_name}({function_args})")

            function_to_call = available_functions[function_name]
            function_response = function_to_call(**function_args)

            print(f"Result: {function_response}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": function_response
            })

        # Get final response
        final_response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=tools,
            temperature=0.1
        )

        print(f"Final response: {final_response.choices[0].message.content}")

def test_message_format_compliance():
    """Test that message formats comply with Groq specs"""
    print("\n=== Testing Message Format Compliance ===")

    messages = [
        {"role": "user", "content": "Calculate 10 + 20"}
    ]

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.1
    )

    # Check response format
    choice = response.choices[0]
    message = choice.message

    print(f"Finish reason: {choice.finish_reason}")
    print(f"Message role: {message.role}")
    print(f"Has content: {message.content is not None}")
    print(f"Has tool_calls: {hasattr(message, 'tool_calls') and message.tool_calls is not None}")

    if hasattr(message, 'tool_calls') and message.tool_calls:
        for i, tc in enumerate(message.tool_calls):
            print(f"Tool call {i}: id={tc.id}, type={tc.type}, name={tc.function.name}")
            print(f"  Arguments: {tc.function.arguments}")

            # Test argument parsing
            try:
                args = json.loads(tc.function.arguments)
                print(f"  Parsed args: {args}")
            except json.JSONDecodeError as e:
                print(f"  ERROR: Invalid JSON in arguments: {e}")

if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY"):
        print("Please set GROQ_API_KEY environment variable")
        exit(1)

    test_agentic_loop()
    test_error_handling()
    test_message_format_compliance()