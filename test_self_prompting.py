#!/usr/bin/env python3
"""Test self-prompting: show JSON from meta-LLM and final prompt"""

from agent import MiniAgent
import json

def test_self_prompting():
    """Test that JSON from meta-LLM is properly used to build final prompt"""
    
    print("=" * 80)
    print("SELF-PROMPTING TEST")
    print("=" * 80)
    
    # Create agent
    agent = MiniAgent()
    
    # Test query
    test_query = "Read data.csv and create a histogram"
    
    print(f"\n📝 USER QUERY: {test_query}")
    print("-" * 80)
    
    # Step 1: Get JSON from meta-LLM
    print("\n🤖 Step 1: Meta-LLM generates prompt JSON...")
    prompt_data = agent._generate_execution_prompt(test_query)
    
    print("\n📦 JSON RETURNED BY META-LLM:")
    print(json.dumps(prompt_data, indent=2))
    
    # Step 2: Build final prompt (simulate what process_input does)
    print("\n🔨 Step 2: Building final prompt from JSON...")
    
    prompt_parts = []
    
    # Role definition
    if prompt_data.get("role"):
        prompt_parts.append(f"You are: {prompt_data['role']}")
    
    # Core instruction
    if prompt_data.get("system_prompt"):
        prompt_parts.append(prompt_data["system_prompt"])
    
    # Recommended tools
    if prompt_data.get("tools") and len(prompt_data["tools"]) > 0:
        tools_list = ", ".join(prompt_data["tools"])
        prompt_parts.append(f"\nRelevant tools for this task: {tools_list}")
    
    # Usage examples
    if prompt_data.get("examples") and len(prompt_data["examples"]) > 0:
        prompt_parts.append("\nKey patterns to follow:")
        for example in prompt_data["examples"]:
            prompt_parts.append(f"- {example}")
    
    # Additional details
    if prompt_data.get("details"):
        prompt_parts.append(f"\nAdditional guidance: {prompt_data['details']}")
    
    # Combine all parts
    custom_prompt = "\n".join(prompt_parts)
    
    # Append system context to generated prompt
    full_prompt = f"{custom_prompt}\n\n{agent.system_context}"
    
    print("\n✅ FINAL PROMPT SENT TO MAIN LLM:")
    print("=" * 80)
    print(full_prompt)
    print("=" * 80)
    
    print(f"\n📊 STATS:")
    print(f"  - Prompt length: {len(full_prompt)} characters")
    print(f"  - Role: {prompt_data.get('role', 'N/A')}")
    print(f"  - Tools recommended: {len(prompt_data.get('tools', []))}")
    print(f"  - Examples included: {len(prompt_data.get('examples', []))}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_self_prompting()
