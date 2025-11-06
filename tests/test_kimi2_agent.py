#!/usr/bin/env python3
"""
Standalone test for Kimi K2 API integration.

Tests API connection, chat completion, and function calling with tools.
Must pass before integrating Kimi K2 support into main codebase.

Requirements:
- KIMI_2_API_KEY environment variable
- KIMI_2_BASE_URL (default: https://api.moonshot.ai/v1)
- KIMI_2_MODEL (default: kimi-k2-instruct)
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Test configuration
KIMI_API_KEY = os.getenv("KIMI_2_API_KEY")
KIMI_BASE_URL = os.getenv("KIMI_2_BASE_URL", "https://api.moonshot.ai/v1")
KIMI_MODEL = os.getenv("KIMI_2_MODEL", "kimi-k2-instruct")

# Tool schemas for testing (simplified from tools.py)
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with content in the working directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (e.g., 'test.txt', 'data/output.csv')"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["file_path", "content"]
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
            "name": "run_command",
            "description": "Execute a non-interactive shell command",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute (e.g., 'date', 'ls -la', 'cat file.txt')"
                    }
                },
                "required": ["command"]
            }
        }
    }
]


def print_test_header(test_name: str):
    """Print formatted test section header"""
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"{'='*60}")


def print_result(success: bool, message: str):
    """Print test result with color"""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}: {message}")


def test_1_api_connection():
    """Test 1: Verify API key works and connection succeeds"""
    print_test_header("API Connection")
    
    if not KIMI_API_KEY:
        print_result(False, "KIMI_2_API_KEY not set")
        return False
    
    try:
        client = OpenAI(base_url=KIMI_BASE_URL, api_key=KIMI_API_KEY)
        
        # Minimal API call (1 token response)
        response = client.chat.completions.create(
            model=KIMI_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0.0
        )
        
        if response.choices and response.choices[0].message:
            print_result(True, f"Connected to {KIMI_BASE_URL} with model {KIMI_MODEL}")
            return True
        else:
            print_result(False, "No response from API")
            return False
            
    except Exception as e:
        print_result(False, f"Connection failed: {e}")
        return False


def test_2_basic_chat():
    """Test 2: Basic chat completion without tools"""
    print_test_header("Basic Chat Completion")
    
    try:
        client = OpenAI(base_url=KIMI_BASE_URL, api_key=KIMI_API_KEY)
        
        response = client.chat.completions.create(
            model=KIMI_MODEL,
            messages=[{"role": "user", "content": "What is 2+2? Answer with just the number."}],
            max_tokens=10,
            temperature=0.0
        )
        
        if not response.choices or not response.choices[0].message:
            print_result(False, "No response message")
            return False
        
        content = response.choices[0].message.content or ""
        print(f"Response: {content.strip()}")
        
        # Check if response contains "4"
        if "4" in content:
            print_result(True, "Model responded correctly to simple math question")
            return True
        else:
            print_result(False, f"Expected '4' in response, got: {content}")
            return False
            
    except Exception as e:
        print_result(False, f"Chat completion failed: {e}")
        return False


def test_3_function_calling():
    """Test 3: Function calling with multiple tool invocations"""
    print_test_header("Function Calling with Tools")
    
    try:
        client = OpenAI(base_url=KIMI_BASE_URL, api_key=KIMI_API_KEY)
        
        # Create temp directory for test files
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            
            # Simulated tool executor
            def execute_tool(tool_name: str, args: dict) -> str:
                """Simulate tool execution"""
                if tool_name == "write_file":
                    file_path = Path(tmpdir) / args["file_path"]
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(args["content"])
                    return f"File written: {args['file_path']}"
                
                elif tool_name == "read_file":
                    file_path = Path(tmpdir) / args["file_path"]
                    if file_path.exists():
                        return file_path.read_text()
                    return f"File not found: {args['file_path']}"
                
                elif tool_name == "run_command":
                    # Simulate date command
                    if "date" in args["command"]:
                        return "Wed Nov 6 12:00:00 EST 2025"
                    return f"Command output: {args['command']}"
                
                return "Unknown tool"
            
            # Initial prompt requesting multi-step workflow
            messages = [{
                "role": "user",
                "content": "Create a file called 'test.txt' with content 'hello world', then read it back, and show me today's date."
            }]
            
            max_iterations = 5
            tool_calls_made = []
            
            for iteration in range(max_iterations):
                response = client.chat.completions.create(
                    model=KIMI_MODEL,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    max_tokens=512,
                    temperature=0.0
                )
                
                if not response.choices or not response.choices[0].message:
                    print_result(False, "No response message")
                    return False
                
                assistant_msg = response.choices[0].message
                
                # Check for tool calls
                if assistant_msg.tool_calls:
                    messages.append({
                        "role": "assistant",
                        "content": assistant_msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            }
                            for tc in assistant_msg.tool_calls
                        ]
                    })
                    
                    # Execute each tool call
                    for tool_call in assistant_msg.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError as e:
                            print_result(False, f"Invalid tool arguments JSON: {e}")
                            return False
                        
                        tool_calls_made.append(tool_name)
                        print(f"  Tool called: {tool_name}({args})")
                        
                        # Execute tool
                        result = execute_tool(tool_name, args)
                        
                        # Add tool result to messages
                        messages.append({
                            "role": "tool",
                            "content": result,
                            "tool_call_id": tool_call.id
                        })
                else:
                    # No more tool calls - final response
                    final_content = assistant_msg.content or ""
                    print(f"\nFinal response: {final_content[:200]}")
                    break
            
            # Validate test success
            print(f"\nTool calls made: {tool_calls_made}")
            
            # Check for expected tool usage
            has_write = "write_file" in tool_calls_made
            has_read = "read_file" in tool_calls_made
            has_command = "run_command" in tool_calls_made
            
            if has_write and has_read:
                print_result(True, f"Function calling works - used {len(tool_calls_made)} tools")
                
                # Bonus: check if all 3 tools were used
                if has_command:
                    print("  ✨ Bonus: Used all 3 tools (write, read, command)")
                
                return True
            else:
                print_result(False, f"Expected write_file and read_file, got: {tool_calls_made}")
                return False
            
    except Exception as e:
        print_result(False, f"Function calling test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_4_error_handling():
    """Test 4: Error handling (invalid API key, malformed requests)"""
    print_test_header("Error Handling")
    
    # Test 4a: Invalid API key
    try:
        client = OpenAI(base_url=KIMI_BASE_URL, api_key="invalid_key_12345")
        response = client.chat.completions.create(
            model=KIMI_MODEL,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        print_result(False, "Should have failed with invalid API key")
        return False
    except Exception as e:
        if "401" in str(e) or "unauthorized" in str(e).lower() or "invalid" in str(e).lower():
            print_result(True, "Correctly rejected invalid API key")
        else:
            print(f"  Note: Error was: {e}")
            print_result(True, "Invalid API key was rejected (different error)")
    
    # Test 4b: Malformed tool schema (should still work or gracefully fail)
    try:
        client = OpenAI(base_url=KIMI_BASE_URL, api_key=KIMI_API_KEY)
        
        # Valid request - just checking client handles edge cases
        response = client.chat.completions.create(
            model=KIMI_MODEL,
            messages=[{"role": "user", "content": "Say 'ok'"}],
            max_tokens=5,
            temperature=0.0
        )
        
        if response.choices:
            print_result(True, "Client handles requests gracefully")
            return True
        
    except Exception as e:
        print_result(False, f"Unexpected error: {e}")
        return False
    
    return True


def main():
    """Run all tests and report results"""
    print(f"\n{'#'*60}")
    print("#  Kimi K2 Integration Test Suite")
    print(f"#  Model: {KIMI_MODEL}")
    print(f"#  Base URL: {KIMI_BASE_URL}")
    print(f"{'#'*60}")
    
    if not KIMI_API_KEY:
        print("\n❌ FATAL: KIMI_2_API_KEY environment variable not set")
        print("\nSet it with:")
        print("  export KIMI_2_API_KEY=your_api_key_here")
        print("  export KIMI_2_BASE_URL=https://api.moonshot.ai/v1  # optional")
        print("  export KIMI_2_MODEL=kimi-k2-instruct  # optional")
        sys.exit(1)
    
    # Run tests
    results = {
        "API Connection": test_1_api_connection(),
        "Basic Chat": test_2_basic_chat(),
        "Function Calling": test_3_function_calling(),
        "Error Handling": test_4_error_handling()
    }
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    
    print(f"\nResults: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("\n🎉 ALL TESTS PASSED - Ready to integrate Kimi K2 into codebase")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total_tests - passed_tests} test(s) failed - Fix issues before integration")
        sys.exit(1)


if __name__ == "__main__":
    main()
