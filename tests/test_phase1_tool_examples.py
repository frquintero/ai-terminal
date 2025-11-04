"""
Phase 1 Tests: Tool Examples and Catalog
Tests that usage_examples are properly added and catalog is built correctly.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_base_tool_has_usage_examples_property():
    """Verify BaseTool has usage_examples property"""
    from tools import BaseTool
    import inspect
    
    # Check that usage_examples is defined in BaseTool
    assert hasattr(BaseTool, 'usage_examples'), "BaseTool should have usage_examples property"
    
    # Verify it's a property
    assert isinstance(inspect.getattr_static(BaseTool, 'usage_examples'), property), \
        "usage_examples should be a property"
    
    print("✓ BaseTool has usage_examples property")


def test_sandbox_tool_has_examples():
    """Verify RunPythonSandboxTool has usage examples with SANDBOX_PROJECT pattern"""
    from tools import TOOLS
    
    sandbox_tool = TOOLS.get("run_python_sandbox")
    assert sandbox_tool is not None, "run_python_sandbox tool should exist"
    
    examples = sandbox_tool.usage_examples
    assert examples is not None, "sandbox tool should have examples"
    assert len(examples) > 0, "sandbox tool should have at least one example"
    
    # Check that at least one example mentions SANDBOX_PROJECT
    has_sandbox_project = any("SANDBOX_PROJECT" in ex for ex in examples)
    assert has_sandbox_project, "At least one example should mention SANDBOX_PROJECT pattern"
    
    print(f"✓ Sandbox tool has {len(examples)} examples with SANDBOX_PROJECT pattern")


def test_run_command_has_examples():
    """Verify run_command has examples"""
    from tools import TOOLS
    
    cmd_tool = TOOLS.get("run_command")
    assert cmd_tool is not None, "run_command tool should exist"
    
    examples = cmd_tool.usage_examples
    assert examples is not None, "run_command should have examples"
    assert len(examples) > 0, "run_command should have at least one example"
    
    print(f"✓ run_command has {len(examples)} examples")


def test_write_file_has_examples():
    """Verify write_file has examples"""
    from tools import TOOLS
    
    write_tool = TOOLS.get("write_file")
    assert write_tool is not None, "write_file tool should exist"
    
    examples = write_tool.usage_examples
    assert examples is not None, "write_file should have examples"
    assert len(examples) > 0, "write_file should have at least one example"
    
    print(f"✓ write_file has {len(examples)} examples")


def test_interactive_has_examples():
    """Verify run_interactive has examples"""
    from tools import TOOLS
    
    interactive_tool = TOOLS.get("run_interactive")
    assert interactive_tool is not None, "run_interactive tool should exist"
    
    examples = interactive_tool.usage_examples
    assert examples is not None, "run_interactive should have examples"
    assert len(examples) > 0, "run_interactive should have at least one example"
    
    print(f"✓ run_interactive has {len(examples)} examples")


def test_tool_catalog_built():
    """Verify agent builds tool catalog correctly"""
    from agent import MiniAgent
    
    agent = MiniAgent()
    
    # Check catalog exists
    assert hasattr(agent, 'tool_catalog'), "Agent should have tool_catalog attribute"
    assert agent.tool_catalog is not None, "tool_catalog should not be None"
    assert "tools" in agent.tool_catalog, "catalog should have 'tools' key"
    
    tools = agent.tool_catalog["tools"]
    assert len(tools) > 0, "catalog should have at least one tool"
    
    print(f"✓ Tool catalog built with {len(tools)} tools")


def test_catalog_includes_examples():
    """Verify catalog includes examples for tools that have them"""
    from agent import MiniAgent
    
    agent = MiniAgent()
    tools = agent.tool_catalog["tools"]
    
    # Find sandbox tool in catalog
    sandbox_entry = next((t for t in tools if t["name"] == "run_python_sandbox"), None)
    assert sandbox_entry is not None, "Sandbox tool should be in catalog"
    assert "examples" in sandbox_entry, "Sandbox tool should have examples in catalog"
    assert len(sandbox_entry["examples"]) > 0, "Sandbox examples should not be empty"
    
    # Check SANDBOX_PROJECT pattern is in examples
    has_pattern = any("SANDBOX_PROJECT" in ex for ex in sandbox_entry["examples"])
    assert has_pattern, "Catalog should include SANDBOX_PROJECT pattern in examples"
    
    print(f"✓ Catalog includes {len(sandbox_entry['examples'])} examples for sandbox tool")


def test_catalog_json_serializable():
    """Verify tool catalog is JSON serializable"""
    from agent import MiniAgent
    import json
    
    agent = MiniAgent()
    
    # Should not raise exception
    try:
        json_str = json.dumps(agent.tool_catalog, indent=2)
        assert len(json_str) > 0, "JSON string should not be empty"
        
        # Verify we can deserialize it back
        parsed = json.loads(json_str)
        assert "tools" in parsed, "Parsed catalog should have 'tools' key"
        
        print("✓ Tool catalog is JSON-serializable")
    except Exception as e:
        raise AssertionError(f"Catalog should be JSON serializable: {e}")


if __name__ == "__main__":
    print("\n=== Phase 1: Tool Examples & Catalog Tests ===\n")
    
    try:
        test_base_tool_has_usage_examples_property()
        test_sandbox_tool_has_examples()
        test_run_command_has_examples()
        test_write_file_has_examples()
        test_interactive_has_examples()
        test_tool_catalog_built()
        test_catalog_includes_examples()
        test_catalog_json_serializable()
        
        print("\n✅ All Phase 1 tests passed!")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
