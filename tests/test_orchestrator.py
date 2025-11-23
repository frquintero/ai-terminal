"""
Unit tests for the routerless Orchestrator (Agent A-first flow).

Focuses on Agent A prompts, Agent B normalization, plan execution, and
handle_query bookkeeping without legacy CHAT/SHELL/CACHED branches.
"""

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace


from config import Config
from memory.api import Memory
from orchestrator.orchestrator import Orchestrator, OrchestratorResult, OrchestratorProcessError
from orchestrator.plan_validator import PlanValidator
from orchestrator.prompts import get_agent_a_system_prompt
from orchestrator.routes import Route
from tools import GetContextTool, _SESSION_STATE


class TestOrchestratorPrompts(unittest.TestCase):
    """Test Agent A unified system prompt."""
    
    def test_get_agent_a_system_prompt_lists_tools(self):
        prompt = get_agent_a_system_prompt(["run_command", "read_file"])
        self.assertIn("Agent A", prompt)
        self.assertIn("Strategic Intent", prompt)
        self.assertIn("Data Flow Guidance", prompt)
        self.assertIn("run_command", prompt)


class TestHandleQueryRouterless(unittest.TestCase):
    """Ensure handle_query always flows through Agent A."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        self.config = Mock(spec=Config)
        self.config.model = "gpt-4"
        self.config.max_tokens = 1024
        self.config.temperature = 0.2
        self.config.agent_a_temperature = 0.2
        self.config.agent_b_temperature = 0.0
        self.orchestrator = Orchestrator(self.config, self.memory)

    def tearDown(self):
        self.orchestrator.close()
        os.unlink(self.temp_db.name)

    @patch.object(Orchestrator, "_run_agent_a_cycle")
    def test_handle_query_logs_router_decision(self, mock_agent_a_cycle):
        mock_agent_a_cycle.return_value = OrchestratorResult(
            cycle_id="cycle-1",
            route=Route.PLANNER.value,
            query="ls",
            agent_response="Done",
            execution_result={"success": True}
        )

        result = self.orchestrator.handle_query("ls")

        self.assertEqual(result.agent_response, "Done")
        decision = self.memory.get_router_decision(result.cycle_id)
        self.assertIsNotNone(decision)
        self.assertEqual(decision["route"], Route.PLANNER.value)

    @patch.object(Orchestrator, "_run_agent_a_cycle")
    def test_handle_query_records_latency_and_metrics(self, mock_agent_a_cycle):
        mock_agent_a_cycle.return_value = OrchestratorResult(
            cycle_id="cycle-2",
            route=Route.PLANNER.value,
            query="whoami",
            agent_response="user",
            execution_result={"success": True}
        )

        result = self.orchestrator.handle_query("whoami")

        self.assertGreaterEqual(result.latency_ms, 0)
        decision = self.memory.get_router_decision(result.cycle_id)
        self.assertEqual(decision["confidence"], 1.0)





class TestOrchestratorIntegration(unittest.TestCase):
    """Integration tests with real Memory (no LLM calls)"""
    
    def setUp(self):
        """Create test orchestrator"""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        
        self.config = Mock(spec=Config)
        self.config.model = "test-model"
        self.config.agent_a_temperature = 0.2
        self.config.agent_b_temperature = 0.0
        
        self.orchestrator = Orchestrator(self.config, self.memory)
    
    def tearDown(self):
        """Clean up"""
        self.orchestrator.close()
        os.unlink(self.temp_db.name)
    
    def test_session_created_on_init(self):
        """Orchestrator creates session on initialization"""
        session = self.memory.get_session(self.orchestrator.session_id)
        
        self.assertIsNotNone(session)
        self.assertEqual(session["model"], "test-model")
    
    @patch.object(Orchestrator, "_run_agent_a_cycle")
    def test_cycle_id_generated(self, mock_agent_a_cycle):
        """Each query generates unique cycle_id in Agent A-first flow."""
        mock_agent_a_cycle.return_value = OrchestratorResult(
            cycle_id="cycle-integration",
            route=Route.PLANNER.value,
            query="test query",
            agent_response="Cycle initialized",
            execution_result=None
        )

        result = self.orchestrator.handle_query("test query")

        self.assertIsNotNone(result.cycle_id)
        decision = self.memory.get_router_decision(result.cycle_id)
        self.assertIsNotNone(decision)
        self.assertEqual(decision["query_text"], "test query")
        self.assertEqual(decision["route"], Route.PLANNER.value)

    @patch("orchestrator.orchestrator.LLMClient")
    def test_agent_b_no_output_injects_message(self, mock_llm_client):
        """Agent B loop replaces missing stdout with a helpful fallback."""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="any bat files?"
        )
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({
                    "command": "find . -name '*.bat'",
                    "output_format": {"bat_files": "list"}
                })
            )
        )
        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[tool_call])},
            {"error": None, "message": SimpleNamespace(
                content="```json\n{\"narration_template\":\"Found these files: {bat_files}\"}\n```",
                tool_calls=[]
            )},
            {"error": None, "message": SimpleNamespace(content={
                "segments": [{"kind": "text", "text": "Found these files: {bat_files}"}],
                "template_values": {}
            })}
        ]

        with patch.object(self.orchestrator.tool_executor, "execute", return_value={
            "success": True,
            "stdout": "",
            "stderr": "",
            "raw_stdout": "",
            "raw_stderr": "",
            "exit_code": 0,
            "output_preview": "",
            "error": None,
            "result": "",
            "agent_message": None
        }):
            summary = self.orchestrator._run_agent_b_tool_loop(
                cycle_id=cycle_id,
                query="any bat files?",
                plan={"intent": "find bats", "success_criteria": []}
            )

        fallback = summary["output_values"]["bat_files"]
        self.assertIn("find . -name '*.bat'", fallback)
        self.assertIn("no output", fallback.lower())
        self.assertTrue(summary["output_value_sources"]["bat_files"]["no_output"])
        self.assertEqual(summary["output_value_types"]["bat_files"], "list")
        self.assertEqual(summary["template_values"]["bat_files"], fallback)

    def test_agent_a_context_includes_recent_history(self):
        """Agent A context message lists up to five prior exchanges in newest-first order."""
        for idx in range(1, 6):
            cycle_id = self.memory.create_cycle(
                session_id=self.orchestrator.session_id,
                query=f"what is {idx}"
            )
            self.memory.save_chat_exchange(
                session_id=self.orchestrator.session_id,
                cycle_id=cycle_id,
                user_query=f"what is {idx}",
                agent_response=f"Answer {idx}\n```\nls\n```"
            )

        context = self.orchestrator._build_agent_a_context_message("latest request")

        self.assertIn("These are the previous conversations", context)
        self.assertIn("User is now asking: Latest request", context)
        self.assertIn("1. User query: What is 1 — Cycle", context)
        self.assertIn("5. User query: What is 5 — Cycle", context)
        self.assertNotIn("```", context)

    def test_exception_logs_failure_snapshot(self):
        """Failures triggered by exceptions are persisted to cycle_failures."""
        with patch.object(self.orchestrator, "_run_agent_a_cycle", side_effect=RuntimeError("boom")):
            result = self.orchestrator.handle_query("boom")

        self.assertIsNotNone(result.error)
        self.assertIn("Cycle", result.agent_response)
        failure = self.memory.get_cycle_failure(result.cycle_id)
        self.assertIsNotNone(failure)
        self.assertEqual(failure["error_type"], "RuntimeError")
        self.assertEqual(failure["stage"], "orchestrator")
        self.assertEqual(failure["process"], "orchestrator")

    def test_unsuccessful_execution_logs_failure_snapshot(self):
        """Planner cycles that finish with success=False are logged."""
        failure_result = OrchestratorResult(
            cycle_id="placeholder",
            route=Route.PLANNER.value,
            query="count files",
            agent_response="Could not finish plan",
            execution_result={"success": False, "error": "tool failed"},
            error="Plan execution failed"
        )

        with patch.object(self.orchestrator, "_run_agent_a_cycle", return_value=failure_result):
            result = self.orchestrator.handle_query("count files")

        failure = self.memory.get_cycle_failure(result.cycle_id)
        self.assertIsNotNone(failure)
        self.assertEqual(failure["stage"], "execution")
        self.assertEqual(failure["error_type"], "CycleFailure")
        self.assertIn("tool failed", failure["facts"]["execution_result"]["error"])

    @patch("orchestrator.orchestrator.LLMClient")
    def test_agent_b_loop_returns_structured_outputs(self, mock_llm_client):
        """Agent B loop captures stdout via output_format for fenced rendering."""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="show csv"
        )

        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({
                    "command": "cat all.csv",
                    "output_format": {"rows": "raw"}
                })
            )
        )

        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[tool_call])},
            {"error": None, "message": SimpleNamespace(
                content="```json\n{\"narration_template\":\"Here are the rows:\\n{rows}\"}\n```",
                tool_calls=[]
            )},
            {"error": None, "message": SimpleNamespace(content={
                "segments": [{"kind": "text", "text": "Here are the rows:\n{rows}"}],
                "template_values": {}
            })}
        ]

        with patch.object(self.orchestrator.tool_executor, "execute", return_value={
            "success": True,
            "stdout": "Fruit,Count\nApple,1\nBerry,2\n",
            "stderr": None,
            "raw_stdout": "Fruit,Count\nApple,1\nBerry,2\n",
            "raw_stderr": None,
            "exit_code": 0,
            "output_preview": "Fruit,Count\nApple,1\nBerry,2\n",
            "error": None,
            "result": "Fruit,Count\nApple,1\nBerry,2\n",
            "agent_message": None
        }):
            summary = self.orchestrator._run_agent_b_tool_loop(
                cycle_id=cycle_id,
                query="show csv",
                plan={"intent": "show csv", "success_criteria": ["show file"]}
            )

        self.assertIn("rows", summary["output_values"])
        self.assertEqual(summary["output_value_types"]["rows"], "raw")
        self.assertIn("{rows}", summary["narration_template"])
        self.assertIn("Fruit,Count", summary["output_values"]["rows"])
        self.assertEqual(
            summary["output_value_sources"]["rows"]["tool_name"],
            "run_command"
        )

    @patch("orchestrator.orchestrator.LLMClient")
    def test_run_command_input_data_ref_streams_previous_stdout(self, mock_llm_client):
        """input_data_ref lets Agent B pipe prior tool output into stdin."""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="augment csv"
        )

        read_call = SimpleNamespace(
            id="call-read",
            function=SimpleNamespace(
                name="read_file",
                arguments=json.dumps({"file_path": "data.csv"})
            )
        )
        run_call = SimpleNamespace(
            id="call-run",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({
                    "command": "python3 -c \"print(input())\"",
                    "input_data_ref": {"tool_call_id": "call-read", "channel": "stdout"}
                })
            )
        )

        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[read_call])},
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[run_call])},
            {"error": None, "message": SimpleNamespace(content="done", tool_calls=[])},
            {"error": None, "message": SimpleNamespace(content={
                "segments": [{"kind": "text", "text": "done"}],
                "template_values": {}
            })}
        ]

        file_body = "name,id\nalice,1\n"
        executed_args = []

        def fake_execute(tool_name, tool_args, **kwargs):
            executed_args.append((tool_name, dict(tool_args)))
            if tool_name == "read_file":
                return {
                    "success": True,
                    "stdout": file_body,
                    "stderr": "",
                    "raw_stdout": file_body,
                    "raw_stderr": "",
                    "exit_code": 0,
                    "output_preview": file_body,
                    "error": None,
                    "result": file_body,
                    "agent_message": None
                }
            if tool_name == "run_command":
                assert tool_args.get("input_data") == file_body
                return {
                    "success": True,
                    "stdout": "updated csv",
                    "stderr": "",
                    "raw_stdout": "updated csv",
                    "raw_stderr": "",
                    "exit_code": 0,
                    "output_preview": "updated csv",
                    "error": None,
                    "result": "updated csv",
                    "agent_message": None
                }
            raise AssertionError(f"Unexpected tool {tool_name}")

        with patch.object(self.orchestrator.tool_executor, "execute", side_effect=fake_execute):
            summary = self.orchestrator._run_agent_b_tool_loop(
                cycle_id=cycle_id,
                query="augment csv",
                plan={"intent": "augment csv", "success_criteria": []}
            )

        self.assertEqual(executed_args[0][0], "read_file")
        self.assertEqual(executed_args[1][0], "run_command")
        self.assertEqual(executed_args[1][1]["input_data"], file_body)
        self.assertTrue(summary["success"])

    @patch("orchestrator.orchestrator.LLMClient")
    def test_run_command_warns_when_stdin_missing_after_read_file(self, mock_llm_client):
        """Agent B receives telemetry when it forgets to pipe read_file output into stdin."""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="process log"
        )

        read_call = SimpleNamespace(
            id="call-read",
            function=SimpleNamespace(
                name="read_file",
                arguments=json.dumps({"file_path": "log.txt"})
            )
        )
        run_call = SimpleNamespace(
            id="call-run",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({"command": "python3 process.py"})
            )
        )

        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[read_call])},
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[run_call])},
            {"error": None, "message": SimpleNamespace(content="```json\n{\"segments\": []}\n```", tool_calls=[])},
            {"error": None, "message": SimpleNamespace(content={"segments": [], "template_values": {}})}
        ]

        file_body = "line 1\nline 2\n"

        def fake_execute(tool_name, tool_args, **kwargs):
            if tool_name == "read_file":
                return {
                    "success": True,
                    "stdout": file_body,
                    "stderr": "",
                    "raw_stdout": file_body,
                    "raw_stderr": "",
                    "exit_code": 0,
                    "output_preview": file_body,
                    "result": file_body,
                    "agent_message": None
                }
            if tool_name == "run_command":
                self.assertNotIn("input_data", tool_args)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Traceback (most recent call last): EOF when reading line",
                    "raw_stdout": "",
                    "raw_stderr": "Traceback (most recent call last): EOF when reading line",
                    "exit_code": 1,
                    "output_preview": "",
                    "error": "exit 1",
                    "result": ""
                }
            raise AssertionError(f"Unexpected tool {tool_name}")

        with patch.object(self.orchestrator, "_emit_tool_output") as mock_emit, \
             patch.object(self.orchestrator.tool_executor, "execute", side_effect=fake_execute):
            summary = self.orchestrator._run_agent_b_tool_loop(
                cycle_id=cycle_id,
                query="process log",
                plan={"intent": "process log", "success_criteria": []}
            )

        warning_payloads = [
            call.args[0] for call in mock_emit.call_args_list
            if call.args[0]["tool_name"] == "run_command"
        ]
        self.assertTrue(warning_payloads, "run_command payload missing")
        self.assertIn("input_data_ref", warning_payloads[0]["warnings"][0])

    @patch("orchestrator.orchestrator.LLMClient")
    def test_run_command_strips_null_input_data(self, mock_llm_client):
        """Optional stdin parameters are omitted instead of sending null."""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="list workspace"
        )

        run_call = SimpleNamespace(
            id="call-run",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({"command": "ls", "input_data": None})
            )
        )

        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[run_call])},
            {"error": None, "message": SimpleNamespace(content="done", tool_calls=[])},
            {"error": None, "message": SimpleNamespace(content={
                "segments": [{"kind": "text", "text": "done"}],
                "template_values": {}
            })}
        ]

        captured_args = []

        def fake_execute(tool_name, tool_args, **kwargs):
            captured_args.append((tool_name, dict(tool_args)))
            return {
                "success": True,
                "stdout": "README.md\nsrc\n",
                "stderr": "",
                "raw_stdout": "README.md\nsrc\n",
                "raw_stderr": "",
                "exit_code": 0,
                "output_preview": "README.md\nsrc\n",
                "error": None,
                "result": "README.md\nsrc\n",
                "agent_message": None
            }

        with patch.object(self.orchestrator.tool_executor, "execute", side_effect=fake_execute):
            summary = self.orchestrator._run_agent_b_tool_loop(
                cycle_id=cycle_id,
                query="list workspace",
                plan={"intent": "list workspace", "success_criteria": []}
            )

        self.assertTrue(summary["success"])
        self.assertEqual(len(captured_args), 1)
        self.assertEqual(captured_args[0][0], "run_command")
        self.assertNotIn("input_data", captured_args[0][1])

    @patch("orchestrator.orchestrator.LLMClient")
    def test_schema_validation_error_aborts_cycle(self, mock_llm_client):
        """Schema validation failures immediately abort execution."""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="ls"
        )

        run_call = SimpleNamespace(
            id="call-run",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({"command": "ls"})
            )
        )

        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[run_call])}
        ]

        def fake_execute(tool_name, tool_args, **kwargs):
            self.assertEqual(tool_name, "run_command")
            return {
                "success": False,
                "stdout": None,
                "stderr": "Tool call validation failed: /input_data expected string",
                "raw_stdout": None,
                "raw_stderr": None,
                "exit_code": None,
                "output_preview": "Tool call validation failed: /input_data expected string",
                "error": "Tool call validation failed: /input_data expected string",
                "result": ""
            }

        with patch.object(self.orchestrator.tool_executor, "execute", side_effect=fake_execute):
            with self.assertRaises(OrchestratorProcessError) as ctx:
                self.orchestrator._run_agent_b_tool_loop(
                    cycle_id=cycle_id,
                    query="ls",
                    plan={"intent": "ls", "success_criteria": []}
                )

        self.assertIn("Tool call validation failed", str(ctx.exception))

    @patch("orchestrator.orchestrator.LLMClient")
    def test_pipe_from_streams_file_into_run_command(self, mock_llm_client):
        """pipe_from prepares stdin without echoing content to the agent."""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="count file lines"
        )

        pipe_call = SimpleNamespace(
            id="call-pipe",
            function=SimpleNamespace(
                name="pipe_from",
                arguments=json.dumps({"file_path": "data.txt"})
            )
        )
        run_call = SimpleNamespace(
            id="call-run",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({
                    "command": "wc -l",
                    "input_data_ref": {"tool_call_id": "call-pipe"}
                })
            )
        )

        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[pipe_call])},
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[run_call])},
            {"error": None, "message": SimpleNamespace(content="done", tool_calls=[])},
            {"error": None, "message": SimpleNamespace(content={
                "segments": [{"kind": "text", "text": "done"}],
                "template_values": {}
            })}
        ]

        file_body = "alpha\nbeta\n"
        executed = []

        def fake_execute(tool_name, tool_args, **kwargs):
            executed.append((tool_name, dict(tool_args)))
            if tool_name == "pipe_from":
                return {
                    "success": True,
                    "stdout": file_body,
                    "stderr": "",
                    "raw_stdout": file_body,
                    "raw_stderr": "",
                    "exit_code": 0,
                    "output_preview": "",
                    "agent_message": "stdin ready"
                }
            if tool_name == "run_command":
                self.assertEqual(tool_args.get("input_data"), file_body)
                return {
                    "success": True,
                    "stdout": "2 data.txt",
                    "stderr": "",
                    "raw_stdout": "2 data.txt",
                    "raw_stderr": "",
                    "exit_code": 0,
                    "output_preview": "2 data.txt",
                    "agent_message": None
                }
            raise AssertionError(f"Unexpected tool {tool_name}")

        with patch.object(self.orchestrator.tool_executor, "execute", side_effect=fake_execute):
            summary = self.orchestrator._run_agent_b_tool_loop(
                cycle_id=cycle_id,
                query="count file lines",
                plan={"intent": "count file lines", "success_criteria": []}
            )

        self.assertEqual(executed[0][0], "pipe_from")
        self.assertEqual(executed[1][0], "run_command")
        self.assertTrue(summary["success"])

    @patch("orchestrator.orchestrator.LLMClient")
    def test_tool_history_captures_tool_call_ids(self, mock_llm_client):
        """Agent context exposes recent tool_call_ids for input_data_ref reuse."""
        _SESSION_STATE.reset("history-session")
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="split file"
        )

        pipe_call = SimpleNamespace(
            id="call-pipe",
            function=SimpleNamespace(
                name="pipe_from",
                arguments=json.dumps({"file_path": "data.txt"})
            )
        )
        run_call = SimpleNamespace(
            id="call-run",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({
                    "command": "python3 -c \"print(input())\"",
                    "input_data_ref": {"tool_call_id": "call-pipe"}
                })
            )
        )

        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[pipe_call])},
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[run_call])},
            {"error": None, "message": SimpleNamespace(content="done", tool_calls=[])},
            {"error": None, "message": SimpleNamespace(content={
                "segments": [{"kind": "text", "text": "done"}],
                "template_values": {}
            })}
        ]

        stdin_payload = "alpha\nbeta\n"

        def fake_execute(tool_name, tool_args, **_):
            if tool_name == "pipe_from":
                return {
                    "success": True,
                    "stdout": stdin_payload,
                    "stderr": "",
                    "raw_stdout": stdin_payload,
                    "raw_stderr": "",
                    "exit_code": 0,
                    "output_preview": "",
                    "result": stdin_payload
                }
            if tool_name == "run_command":
                assert tool_args.get("input_data") == stdin_payload
                return {
                    "success": True,
                    "stdout": "processed",
                    "stderr": "",
                    "raw_stdout": "processed",
                    "raw_stderr": "",
                    "exit_code": 0,
                    "output_preview": "processed",
                    "result": "processed"
                }
            raise AssertionError(f"Unexpected tool {tool_name}")

        with patch.object(self.orchestrator.tool_executor, "execute", side_effect=fake_execute):
            self.orchestrator._run_agent_b_tool_loop(
                cycle_id=cycle_id,
                query="split file",
                plan={"intent": "split file", "success_criteria": []}
            )

        context_result = GetContextTool().execute()
        context_payload = json.loads(context_result["stdout"])
        history = context_payload["tool_history"]
        tool_ids = {entry.get("tool_call_id") for entry in history if entry.get("tool_call_id")}
        self.assertIn("call-pipe", tool_ids)
        self.assertIn("call-run", tool_ids)

    @patch("orchestrator.orchestrator.LLMClient")
    def test_tool_snapshot_metadata_persisted_with_step_output(self, mock_llm_client):
        """tool_outputs_by_call_id metadata (hashes/lengths) is persisted for debugging."""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="show env"
        )
        run_call = SimpleNamespace(
            id="call-run",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({"command": "printf 'ok'"})
            )
        )
        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[run_call])},
            {"error": None, "message": SimpleNamespace(content="done", tool_calls=[])},
            {"error": None, "message": SimpleNamespace(content={
                "segments": [{"kind": "text", "text": "done"}],
                "template_values": {}
            })}
        ]

        def fake_execute(tool_name, tool_args, **kwargs):
            return {
                "success": True,
                "stdout": "ok",
                "stderr": "",
                "raw_stdout": "ok",
                "raw_stderr": "",
                "exit_code": 0,
                "output_preview": "ok",
                "agent_message": None
            }

        with patch.object(self.orchestrator.tool_executor, "execute", side_effect=fake_execute):
            summary = self.orchestrator._run_agent_b_tool_loop(
                cycle_id=cycle_id,
                query="show env",
                plan={"intent": "show env", "success_criteria": []}
            )

        self.assertTrue(summary["success"])
        step_outputs = self.memory.get_step_outputs(cycle_id)
        self.assertTrue(step_outputs, "expected step outputs recorded")
        snapshot_meta = step_outputs[0]["parsed_outputs"]["snapshot_meta"]
        self.assertIn("stdout", snapshot_meta)
        self.assertIn("sha256", snapshot_meta["stdout"])
        self.assertEqual(snapshot_meta["stdout"]["len"], 2)

    @patch("orchestrator.orchestrator.LLMClient")
    def test_execution_plan_path_does_not_exit_early(self, mock_llm_client):
        """Ensure execution-plan responses proceed without touching undefined agent_response."""
        # Fake LLM returning a simple execution plan (Agent A format)
        plan_dict = {
            "intent": "List files",
            "success_criteria": ["files listed"]
        }
        mock_llm_client.return_value.call.return_value = {
            "error": None,
            "message": SimpleNamespace(content=json.dumps(plan_dict))
        }

        # Validator should accept our fake plan
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="list files"
        )

        with patch.object(PlanValidator, "validate_with_hints", return_value=(plan_dict, None)), \
             patch.object(Orchestrator, "_execute_plan", return_value={
                 "success": True,
                 "output_values": {"files": "main.py"},
                 "output_value_types": {"files": "list"},
                 "output_value_sources": {},
                 "step_results": [],
                 "narration_template": "Files: {files}",
                 "response_segments": [{"kind": "text", "text": "Files: main.py"}]
             }):
            result = self.orchestrator._run_agent_a_cycle(
                cycle_id=cycle_id,
                query="list files"
            )

        self.assertEqual(result.route, Route.PLANNER.value)
        self.assertEqual(result.agent_response, "Files: main.py")

    @patch("orchestrator.orchestrator.LLMClient")
    def test_planner_success_persists_chat_history(self, mock_llm_client):
        """Successful planner runs store the final narration for future context."""
        plan_dict = {
            "intent": "List files",
            "success_criteria": ["files listed"]
        }
        mock_llm_client.return_value.call.return_value = {
            "error": None,
            "message": SimpleNamespace(content=json.dumps(plan_dict))
        }

        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="list files"
        )

        with patch.object(PlanValidator, "validate_with_hints", return_value=(plan_dict, None)), \
             patch.object(Orchestrator, "_execute_plan", return_value={
                 "success": True,
                 "output_values": {"files": "main.py"},
                 "output_value_types": {"files": "list"},
                 "output_value_sources": {},
                 "step_results": [],
                 "narration_template": "Files: {files}",
                 "response_segments": [{"kind": "text", "text": "Files: main.py"}]
             }), \
             patch.object(self.orchestrator.memory, "save_chat_exchange") as mock_save_chat:
            self.orchestrator._run_agent_a_cycle(
                cycle_id=cycle_id,
                query="list files"
            )

        mock_save_chat.assert_called_once_with(
            session_id=self.orchestrator.session_id,
            cycle_id=cycle_id,
            user_query="list files",
            agent_response="Files: main.py"
        )


class TestAgentBFallbacks(unittest.TestCase):
    """Unit tests for Agent B failure surfacing and narration."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        self.config = Mock(spec=Config)
        self.config.model = "test-model"
        self.config.max_tokens = 512
        self.config.temperature = 0.1
        self.config.agent_a_temperature = 0.2
        self.config.agent_b_temperature = 0.0
        self.config.api_key = "test-key"
        self.config.base_url = "http://example.com"
        self.orchestrator = Orchestrator(self.config, self.memory)

    def tearDown(self):
        self.orchestrator.close()
        os.unlink(self.temp_db.name)

    @patch("orchestrator.orchestrator.LLMClient")
    def test_tool_executor_failure_raises_process_error(self, mock_llm_client):
        """ToolExecutor exceptions bubble as OrchestratorProcessError for logging."""
        tool_call = SimpleNamespace(
            id="call-err",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({"command": "ls", "output_format": {"files": "list"}})
            )
        )
        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[tool_call])},
            {"error": None, "message": SimpleNamespace(content="```json\n{\"segments\":[{\"kind\":\"text\",\"text\":\"should not reach\"}]}\n```", tool_calls=[])}
        ]

        with patch.object(self.orchestrator.tool_executor, "execute", side_effect=RuntimeError("bad args")):
            with self.assertRaises(OrchestratorProcessError) as ctx:
                self.orchestrator._run_agent_b_tool_loop(
                    cycle_id="c-fail",
                    query="list files",
                    plan={"intent": "list files", "success_criteria": []}
                )

        self.assertEqual(ctx.exception.process, "agent_b_tool_executor")
        self.assertIn("bad args", ctx.exception.facts.get("error"))

    @patch("orchestrator.orchestrator.LLMClient")
    def test_informative_exit_codes_not_treated_as_fatal(self, mock_llm_client):
        """Exit codes 1/2/127 with diagnostics are treated as informative, not fatal failures."""
        tool_call = SimpleNamespace(
            id="call-info",
            function=SimpleNamespace(
                name="run_command",
                arguments=json.dumps({"command": "ruby -v 2>&1", "output_format": {"out": "raw"}})
            )
        )
        mock_llm_client.return_value.call.side_effect = [
            {"error": None, "message": SimpleNamespace(content=None, tool_calls=[tool_call])},
            {"error": None, "message": SimpleNamespace(content=json.dumps({
                "segments": [{"kind": "text", "text": "done"}],
                "template_values": {}
            }))},
            {"error": None, "message": SimpleNamespace(content=json.dumps({
                "segments": [{"kind": "text", "text": "done"}],
                "template_values": {}
            }))}
        ]

        exec_result = {
            "success": True,
            "stdout": "bash: ruby: command not found",
            "stderr": "",
            "raw_stdout": "bash: ruby: command not found",
            "raw_stderr": "",
            "exit_code": 127,
            "output_preview": "bash: ruby: command not found",
            "error": None,
            "result": "bash: ruby: command not found",
            "agent_message": None
        }

        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="check ruby"
        )

        with patch.object(self.orchestrator.tool_executor, "execute", return_value=exec_result):
            summary = self.orchestrator._run_agent_b_tool_loop(
                cycle_id=cycle_id,
                query="check ruby",
                plan={"intent": "check ruby", "success_criteria": []}
            )

        step = summary["step_results"][0]
        self.assertTrue(step["success"])
        self.assertTrue(step.get("informative_negative"))
        self.assertEqual(summary["steps_failed"], 0)
        self.assertEqual(summary["steps_completed"], 1)

    @patch("orchestrator.orchestrator.PlanValidator.validate_with_hints")
    @patch("orchestrator.orchestrator.LLMClient")
    def test_agent_a_cycle_uses_agent_b_narration_on_failure(self, mock_llm_client, mock_validate):
        """Failed executions should still surface Agent B narration, not Agent A fallback."""
        plan_dict = {"intent": "List files", "success_criteria": []}
        mock_validate.return_value = (plan_dict, None)
        mock_llm_client.return_value.call.return_value = {
            "error": None,
            "message": SimpleNamespace(content=json.dumps(plan_dict))
        }
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="list files"
        )

        with patch.object(self.orchestrator, "_execute_plan", return_value={
            "success": False,
            "steps_completed": 0,
            "steps_failed": 1,
            "total_steps": 1,
            "step_results": [{"step_id": 0, "description": "run_command", "success": False}],
            "response_segments": [{"kind": "text", "text": "Agent B failed"}],
            "final_response": "Agent B failed",
            "narration_template": None,
            "output_values": {},
            "output_value_types": {},
            "output_value_sources": {},
            "template_values": {}
        }) as mock_execute:
            result = self.orchestrator._run_agent_a_cycle(cycle_id=cycle_id, query="list files")

        mock_execute.assert_called_once()
        self.assertEqual(result.agent_response, "Agent B failed")


if __name__ == "__main__":
    unittest.main()
