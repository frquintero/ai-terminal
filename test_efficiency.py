"""Test script to debug tool calling efficiency for simple commands"""

from agent import MiniAgent
import sys

def test_simple_commands():
    """Test agent with simple commands and track tool calls"""
    
    test_cases = [
        "ls",
        "ls all py files"
    ]
    
    print("=" * 80)
    print("EFFICIENCY TEST - Tracking Tool Calls")
    print("=" * 80)
    
    for i, user_input in enumerate(test_cases, 1):
        print(f"\n\n{'=' * 80}")
        print(f"TEST CASE {i}: '{user_input}'")
        print(f"{'=' * 80}\n")
        
        # Create fresh agent for each test
        agent = MiniAgent()
        
        # Process input
        result = agent.process_input(user_input)
        
        print(f"\n{'=' * 80}")
        print(f"RESULT for '{user_input}':")
        print(f"{'=' * 80}")
        print(f"Steps taken: {result.get('steps', 0)}")
        print(f"Elapsed time: {result.get('elapsed_time', 0):.2f}s")
        print(f"Error: {result.get('error', 'None')}")
        print(f"\nResponse:")
        print(result.get('content', 'No content'))
        print(f"{'=' * 80}\n")
    
    print("\n\nTEST COMPLETE")
    print("Review the [DEBUG] lines above to see which tools were called for each test case")

if __name__ == "__main__":
    test_simple_commands()
