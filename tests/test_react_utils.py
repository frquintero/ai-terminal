import json
from types import SimpleNamespace

from agent import MiniAgent


def test_extract_json_object_handles_fenced_blocks():
    payload = """Action:
    ```json
    {
        "tool": "run_command",
        "arguments": {"command": "ls"}
    }
    ```
    """
    extracted = MiniAgent._extract_json_object(payload)
    assert json.loads(extracted) == {
        "tool": "run_command",
        "arguments": {"command": "ls"}
    }


def test_parse_react_directives_reads_thought_action_and_final():
    message = (
        "Thought: gather info\n"
        "Action: {\"tool\": \"run_command\", \"arguments\": {\"command\": \"pwd\"}}\n"
        "Final Answer: done"
    )
    parsed = MiniAgent._parse_react_directives(message)
    assert parsed["thought"] == "gather info"
    assert parsed["action"] == {
        "tool": "run_command",
        "arguments": {"command": "pwd"}
    }
    assert parsed["final_answer"] == "done"


def test_format_observation_truncates_long_outputs():
    long_output = "x" * (MiniAgent.MAX_TOOL_OUTPUT_CHARS + 50)
    observation_text = MiniAgent._format_observation_content(
        "run_command",
        long_output,
        success=True,
        exit_code=0,
        error_msg=None
    )
    assert "Observation:" in observation_text
    assert "...[truncated" in observation_text


def test_summarize_action_prefers_human_friendly_details():
    summary = MiniAgent._summarize_action("run_command", {"command": "ls"})
    assert summary == "run_command: ls"
    summary = MiniAgent._summarize_action("read_file", {"file_path": "foo.txt"})
    assert summary == "read_file: foo.txt"


def test_plan_reminder_text_includes_thought_and_actions():
    reminder = MiniAgent._build_plan_reminder_text(
        "Use a single ls | wc pipeline",
        ["run_command: ls *.csv | wc -l"]
    )
    assert reminder is not None
    assert "Thought -> Use a single ls | wc pipeline" in reminder
    assert "run_command: ls *.csv | wc -l" in reminder


def test_normalize_tool_calls_assigns_ids_and_strings():
    class SimpleCall:
        def __init__(self):
            self.id = None
            self.type = "function"
            self.function = SimpleNamespace(
                name="run_command",
                arguments={"command": "ls"}
            )
    normalized = MiniAgent._normalize_tool_calls([SimpleCall()])
    assert normalized and normalized[0]["id"].startswith("call-")
    assert normalized[0]["function"]["name"] == "run_command"
    assert isinstance(normalized[0]["function"]["arguments"], str)


def test_sanitize_history_removes_orphan_tool_outputs():
    agent = MiniAgent.__new__(MiniAgent)
    agent.message_history = [
        {"role": "system", "content": "test"},
        {"role": "assistant", "content": "Action", "tool_calls": [
            {"function": {"name": "run_command", "arguments": "{\"command\": \"ls\"}"}}
        ]},
        {"role": "tool", "content": "ok", "tool_call_id": "missing"}
    ]
    agent._log = lambda *args, **kwargs: None  # stub
    agent._sanitize_history_tool_calls()
    assert len(agent.message_history) == 2
    assert all(msg.get("role") != "tool" for msg in agent.message_history)
