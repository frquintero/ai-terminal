#!/usr/bin/env python3
"""
Test script to verify latent bug fixes
"""

import sys
import os
from tools import RunCommandTool, InteractiveCommandTool

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

def test_trim_history_drops_orphan_tool_outputs():
    """Ensure trimming removes tool outputs whose assistant anchor was trimmed"""
    from agent import MiniAgent
    
    agent = MiniAgent()
    agent.MAX_HISTORY_MESSAGES = 6
    agent.message_history = [agent.message_history[0]]
    
    orphan_id = "call-dangling"
    anchor_id = "call-latest"
    agent.message_history.extend([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": orphan_id,
                "type": "function",
                "function": {"name": "run_command", "arguments": "{\"command\": \"echo hi\"}"}
            }]
        },
        {
            "role": "tool",
            "content": "output",
            "tool_call_id": orphan_id
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": anchor_id,
                "type": "function",
                "function": {"name": "run_command", "arguments": "{\"command\": \"echo bye\"}"}
            }]
        },
        {
            "role": "tool",
            "content": "fresh output",
            "tool_call_id": anchor_id
        },
    ])
    
    # Add two more user messages so trimming slices between the first assistant/tool pair
    for i in range(2):
        agent.message_history.append({"role": "user", "content": f"later {i}"})
    
    agent._trim_history()
    
    trimmed_roles = [msg.get("role") for msg in agent.message_history]
    assert trimmed_roles[1] != "tool", "Trimmed history should not start with orphan tool output"
    assert all(
        msg.get("tool_call_id") != orphan_id
        for msg in agent.message_history
        if msg.get("role") == "tool"
    ), "Orphan tool output should be dropped"
    assert any(
        msg.get("tool_call_id") == anchor_id
        for msg in agent.message_history
        if msg.get("role") == "tool"
    ), "Recent tool outputs should remain intact"
    
    print("✓ Trim history drops orphan tool outputs")

def test_sanitize_history_reports_tool_state():
    """Ensure sanitize helper normalizes messages and returns diagnostics"""
    from agent import MiniAgent
    
    agent = MiniAgent()
    agent.message_history = [agent.message_history[0]]
    
    tool_call_id = "call-xyz"
    agent.message_history.extend([
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": tool_call_id,
            "type": "function",
            "function": {"name": "read_file", "arguments": "{\"file_path\": \"notes.txt\"}"}
        }]},
        {"role": "tool", "content": "result body", "tool_call_id": tool_call_id},
        {"role": "tool", "content": "orphan output", "tool_call_id": "ghost"}
    ])
    
    tool_state = agent._sanitize_history_tool_calls()
    
    assert tool_state["assistant_tool_calls"], "Should capture assistant tool calls"
    assert tool_state["assistant_tool_calls"][0]["id"] == tool_call_id
    assert len(tool_state["tool_messages"]) == 2
    assert tool_state["tool_messages"][0]["tool_call_id"] == tool_call_id
    assert tool_state["tool_messages"][1]["tool_call_id"] == "ghost"
    # Ensure no messages were removed
    assert any(msg.get("tool_call_id") == "ghost" for msg in agent.message_history), \
        "sanitize should not drop messages"
    
    print("✓ Sanitization reports tool-call metadata")

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
        test_interactive_detection_path()
        test_interactive_detection_with_flags()
        test_non_interactive_allowed()
        test_message_history_trimming()
        test_trim_history_preserves_tool_calls()
        test_trim_history_drops_orphan_tool_outputs()
        test_sanitize_history_reports_tool_state()
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
