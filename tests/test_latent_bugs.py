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

def test_flush_pending_tool_history_prunes_tool_entries():
    """Pending tool calls should be removed once they are flushed"""
    from agent import MiniAgent

    agent = MiniAgent()
    system_msg = agent.message_history[0]
    assistant_entry = {"role": "assistant", "content": "", "tool_calls": [{"id": "call-abc", "type": "function", "function": {"name": "read_file", "arguments": "{\"file_path\": \"notes.txt\"}"}}]}
    tool_message = {"role": "tool", "content": "output", "tool_call_id": "call-abc"}
    agent.message_history.extend([assistant_entry, tool_message, {"role": "user", "content": "later"}])

    agent._pending_tool_history = {
        "tool_call_ids": {"call-abc"},
    }
    agent._flush_pending_tool_history()

    assert assistant_entry not in agent.message_history, "Assistant tool call should be removed"
    assert all(
        msg.get("tool_call_id") != "call-abc"
        for msg in agent.message_history
        if msg.get("role") == "tool"
    ), "Tool output should be removed"
    assert agent.message_history[0] == system_msg, "System message must remain"

    print("✓ Pending tool history is pruned after flush")

def test_trim_history_skips_trim_when_pending():
    """Do not drop tool anchors while pending"""
    from agent import MiniAgent

    agent = MiniAgent()
    agent.MAX_HISTORY_MESSAGES = 3
    system_msg = agent.message_history[0]
    assistant_entry = {"role": "assistant", "content": "", "tool_calls": [{"id": "call-xyz", "type": "function", "function": {"name": "run_command", "arguments": "{\"command\": \"echo hi\"}"}}]}
    tool_message = {"role": "tool", "content": "output", "tool_call_id": "call-xyz"}
    agent.message_history = [
        system_msg,
        {"role": "user", "content": "first"},
        assistant_entry,
        tool_message,
        {"role": "user", "content": "second"},
    ]
    agent._pending_tool_history = {"tool_call_ids": {"call-xyz"}}

    agent._trim_history()
    assert len(agent.message_history) >= 4, "History should not trim while pending"
    assert any(
        msg.get("role") == "assistant" and msg.get("tool_calls")
        for msg in agent.message_history
    ), "Assistant tool call must remain while pending"

    agent._pending_tool_history = None
    agent._trim_history()
    assert len(agent.message_history) <= agent.MAX_HISTORY_MESSAGES, "History should trim once pending cleared"

    print("✓ Pending tool anchors survive trimming until flush")

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
    agent.MAX_HISTORY_MESSAGES = 6
    agent.message_history = [agent.message_history[0]]
    
    # Fill history so trimming definitely runs
    for i in range(6):
        agent.message_history.append({"role": "user", "content": f"prep {i}"})
    
    # Add a message with large tool output
    large_output = "x" * 20000  # Larger than MAX_TOOL_OUTPUT_CHARS
    tool_call_id = "test123"
    agent.message_history.append({
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": tool_call_id,
            "type": "function",
            "function": {"name": "run_command", "arguments": "{\"command\": \"echo hi\"}"}
        }]
    })
    agent.message_history.append({
        "role": "tool",
        "content": large_output,
        "tool_call_id": tool_call_id
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
        test_flush_pending_tool_history_prunes_tool_entries()
        test_trim_history_skips_trim_when_pending()
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
