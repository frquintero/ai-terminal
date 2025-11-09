#!/usr/bin/env python3
"""
Test script to verify latent bug fixes
"""

import sys
import os
from tools import RunCommandTool, InteractiveCommandTool

def test_interactive_detection_sudo():
    """Test that sudo vim is detected as interactive"""
    tool = RunCommandTool()
    
    result = tool.execute("sudo vim test.txt")
    assert "interactive command" in result.lower(), f"Should block sudo vim: {result}"
    assert "run_interactive" in result.lower(), f"Should suggest run_interactive: {result}"
    
    result = tool.execute("sudo nano test.txt")
    assert "interactive command" in result.lower(), f"Should block sudo nano: {result}"
    
    result = tool.execute("doas vim test.txt")
    assert "interactive command" in result.lower(), f"Should block doas vim: {result}"
    
    print("✓ Interactive detection catches sudo/doas correctly")

def test_interactive_detection_path():
    """Test that /usr/bin/vim is detected as interactive"""
    tool = RunCommandTool()
    
    result = tool.execute("/usr/bin/vim test.txt")
    assert "interactive command" in result.lower(), f"Should block /usr/bin/vim: {result}"
    
    result = tool.execute("/bin/nano test.txt")
    assert "interactive command" in result.lower(), f"Should block /bin/nano: {result}"
    
    print("✓ Interactive detection catches absolute paths correctly")

def test_interactive_detection_with_flags():
    """Test that vim with flags is detected as interactive"""
    tool = RunCommandTool()
    
    result = tool.execute("vim -n test.txt")
    assert "interactive command" in result.lower(), f"Should block vim with flags: {result}"
    
    result = tool.execute("top -b -n 1")
    assert "interactive command" in result.lower(), f"Should block top with flags: {result}"
    
    print("✓ Interactive detection catches commands with flags correctly")

def test_non_interactive_allowed():
    """Test that non-interactive commands are allowed"""
    tool = RunCommandTool()
    
    # These should NOT be blocked (though they may fail to execute in test env)
    result = tool.execute("ls -la")
    assert "interactive command" not in result.lower(), f"Should allow ls: {result}"
    
    result = tool.execute("echo hello")
    # Should execute or give shell error, but not interactive error
    assert "interactive command" not in result.lower(), f"Should allow echo: {result}"
    
    print("✓ Non-interactive commands are not blocked")

def test_shell_integration_prompt():
    """Test that shell uses unique prompt sentinel"""
    from shell_integration import ShellIntegration
    
    shell = ShellIntegration()
    assert hasattr(shell, 'PROMPT'), "Should have PROMPT attribute"
    assert shell.PROMPT == "__AI_PROMPT__$ ", f"Unexpected prompt: {shell.PROMPT}"
    
    # Cleanup
    shell.close()
    
    print("✓ Shell uses unique prompt sentinel")

def test_message_history_trimming():
    """Test that agent trims message history"""
    from agent import MiniAgent
    
    agent = MiniAgent()
    
    # Verify trim configuration exists
    assert hasattr(agent, 'MAX_HISTORY_MESSAGES'), "Should have MAX_HISTORY_MESSAGES"
    assert hasattr(agent, 'MAX_TOOL_OUTPUT_CHARS'), "Should have MAX_TOOL_OUTPUT_CHARS"
    assert hasattr(agent, '_trim_history'), "Should have _trim_history method"
    
    # Test trimming with excessive messages
    initial_len = len(agent.message_history)
    
    # Add many messages
    for i in range(100):
        agent.message_history.append({"role": "user", "content": f"test {i}"})
    
    # Trim
    agent._trim_history()
    
    # Should be trimmed to MAX_HISTORY_MESSAGES
    assert len(agent.message_history) <= agent.MAX_HISTORY_MESSAGES, \
        f"History should be trimmed to {agent.MAX_HISTORY_MESSAGES}, got {len(agent.message_history)}"
    
    # First message should still be system message
    assert agent.message_history[0]["role"] == "system", "First message should be system"
    
    print("✓ Message history trimming works correctly")

def test_trim_history_preserves_tool_calls():
    """Ensure trimming keeps latest assistant tool_call anchor"""
    from agent import MiniAgent
    
    agent = MiniAgent()
    agent.MAX_HISTORY_MESSAGES = 6  # Force aggressive trimming
    
    # Reset to only the system message for deterministic ordering
    agent.message_history = [agent.message_history[0]]
    
    # Add some older chatter
    for i in range(5):
        agent.message_history.append({"role": "user", "content": f"before {i}"})
    
    tool_call_id = "call-123"
    agent.message_history.append({
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": tool_call_id,
            "type": "function",
            "function": {"name": "run_command", "arguments": "{}"}
        }]
    })
    agent.message_history.append({
        "role": "tool",
        "content": "result",
        "tool_call_id": tool_call_id
    })
    
    # Add more chatter to push the tool_call out of the normal window
    for i in range(10):
        agent.message_history.append({"role": "user", "content": f"after {i}"})
    
    agent._trim_history()
    
    # The assistant message with tool_calls must still be present
    assert any(
        msg.get("role") == "assistant" and msg.get("tool_calls")
        for msg in agent.message_history
    ), "Latest assistant tool_call message should be preserved"
    
    print("✓ Trim history preserves pending tool calls")

def test_tool_output_truncation():
    """Test that large tool outputs are truncated"""
    from agent import MiniAgent
    
    agent = MiniAgent()
    
    # Add a message with large tool output
    large_output = "x" * 20000  # Larger than MAX_TOOL_OUTPUT_CHARS
    agent.message_history.append({
        "role": "tool",
        "content": large_output,
        "tool_call_id": "test123"
    })
    
    # Trim
    agent._trim_history()
    
    # Find the tool message
    tool_msg = None
    for msg in agent.message_history:
        if msg.get("role") == "tool" and msg.get("tool_call_id") == "test123":
            tool_msg = msg
            break
    
    if tool_msg:
        assert len(tool_msg["content"]) <= agent.MAX_TOOL_OUTPUT_CHARS + 100, \
            f"Tool output should be truncated, got {len(tool_msg['content'])}"
        assert "truncated" in tool_msg["content"], "Should mention truncation"
    
    print("✓ Tool output truncation works correctly")

if __name__ == "__main__":
    print("Testing latent bug fixes...\n")
    
    try:
        test_interactive_detection_sudo()
        test_interactive_detection_path()
        test_interactive_detection_with_flags()
        test_non_interactive_allowed()
        test_shell_integration_prompt()
        test_message_history_trimming()
        test_trim_history_preserves_tool_calls()
        test_tool_output_truncation()
        
        print("\n✓ All latent bug fixes verified!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
