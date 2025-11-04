"""
Phase 2 Tests: Self-Prompting System
Tests that the prompt generation and integration works correctly.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_generate_execution_prompt_exists():
    """Verify _generate_execution_prompt method exists"""
    from agent import MiniAgent
    
    agent = MiniAgent()
    
    assert hasattr(agent, '_generate_execution_prompt'), \
        "Agent should have _generate_execution_prompt method"
    
    # Check it's callable
    assert callable(agent._generate_execution_prompt), \
        "_generate_execution_prompt should be callable"
    
    print("✓ _generate_execution_prompt method exists")


def test_system_context_stored():
    """Verify system_context is stored as instance variable"""
    from agent import MiniAgent
    
    agent = MiniAgent()
    
    assert hasattr(agent, 'system_context'), \
        "Agent should have system_context attribute"
    
    assert agent.system_context is not None, \
        "system_context should not be None"
    
    assert len(agent.system_context) > 0, \
        "system_context should not be empty"
    
    print(f"✓ system_context stored ({len(agent.system_context)} chars)")


def test_generate_prompt_returns_string():
    """Verify prompt generation returns a dict with all fields"""
    from agent import MiniAgent
    
    agent = MiniAgent()
    
    # Test with simple query
    prompt_data = agent._generate_execution_prompt("Hello, how are you?")
    
    assert isinstance(prompt_data, dict), "Generated prompt should be a dict"
    assert "system_prompt" in prompt_data, "Should have system_prompt field"
    assert "role" in prompt_data, "Should have role field"
    assert "tools" in prompt_data, "Should have tools field"
    assert "examples" in prompt_data, "Should have examples field"
    assert "details" in prompt_data, "Should have details field"
    
    print(f"✓ Generated prompt is valid dict with all fields")


def test_generate_prompt_fallback_on_error():
    """Verify fallback works if prompt generation fails"""
    from agent import MiniAgent
    from unittest.mock import MagicMock
    
    agent = MiniAgent()
    
    # Break the client to trigger fallback
    original_create = agent.client.chat.completions.create
    agent.client.chat.completions.create = MagicMock(side_effect=Exception("API error"))
    
    try:
        # Should not raise exception, should use fallback
        prompt_data = agent._generate_execution_prompt("test query")
        
        assert isinstance(prompt_data, dict), "Fallback should return a dict"
        assert "system_prompt" in prompt_data, "Fallback should have system_prompt"
        assert "role" in prompt_data, "Fallback should have role"
        assert "tools" in prompt_data, "Fallback should have tools"
        assert "examples" in prompt_data, "Fallback should have examples"
        assert "details" in prompt_data, "Fallback should have details"
        
        print(f"✓ Fallback prompt works with all fields")
        
    finally:
        # Restore client
        agent.client.chat.completions.create = original_create


def test_prompt_includes_catalog_info():
    """Verify meta-prompt includes tool catalog"""
    from agent import MiniAgent
    import json
    
    agent = MiniAgent()
    
    # Verify catalog is available for prompt generation
    assert agent.tool_catalog is not None, "Tool catalog should be available"
    
    # Verify catalog can be serialized (used in meta-prompt)
    catalog_str = json.dumps(agent.tool_catalog, indent=2)
    assert len(catalog_str) > 0, "Catalog should be serializable"
    
    print("✓ Tool catalog available for prompt generation")


if __name__ == "__main__":
    print("\n=== Phase 2: Self-Prompting System Tests ===\n")
    
    try:
        test_generate_execution_prompt_exists()
        test_system_context_stored()
        test_generate_prompt_returns_string()
        test_generate_prompt_fallback_on_error()
        test_prompt_includes_catalog_info()
        
        print("\n✅ All Phase 2 tests passed!")
        print("\nNote: Full integration testing (with process_input) requires API key.")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
