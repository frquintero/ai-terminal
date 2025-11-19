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

import pytest

from config import Config
from memory.api import Memory
from orchestrator.orchestrator import Orchestrator, OrchestratorResult
from orchestrator.plan_validator import PlanValidator
from orchestrator.prompts import get_agent_a_system_prompt
from orchestrator.routes import Route


class TestOrchestratorPrompts(unittest.TestCase):
    """Test Agent A unified system prompt."""
    
    def test_get_agent_a_system_prompt_lists_tools(self):
        prompt = get_agent_a_system_prompt(["run_command", "read_file"])
        self.assertIn("run_command", prompt)
        self.assertIn("read_file", prompt)
        self.assertIn("One-Shot Planning", prompt)


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

    def test_execute_plan_parses_and_persists_outputs(self):
        """_execute_plan stores parsed values and narration slots."""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="list files"
        )
        plan = {
            "steps": [
                {
                    "id": 0,
                    "tool_name": "run_command",
                    "description": "List repository files",
                    "output_keys": ["files", "count"]
                }
            ],
            "narration_template": "Found {count} files: {files}"
        }
        self.memory.save_plan(cycle_id, plan, status="in_progress")

        agent_b_payload = {
            "success": True,
            "tool_args": {"command": "ls"},
            "command": "ls",
            "output_format": {"files": "list", "count": "int"}
        }

        tool_result = {
            "success": True,
            "result": "main.py\napp.py\ncount: 2\n",
            "stdout": "main.py\napp.py\ncount: 2\n",
            "stderr": None,
            "raw_stdout": "main.py\napp.py\ncount: 2\n",
            "raw_stderr": None,
            "exit_code": 0,
            "output_preview": "main.py\napp.py\ncount: 2\n",
            "error": None,
            "latency_ms": 15
        }

        with patch.object(self.orchestrator, "_call_agent_b", return_value=agent_b_payload), \
             patch.object(self.orchestrator, "tool_executor") as mock_executor:
            mock_executor.execute.return_value = tool_result

            summary = self.orchestrator._execute_plan(
                cycle_id=cycle_id,
                query="list files",
                plan=plan
            )

        self.assertEqual(summary["steps_completed"], 1)
        self.assertEqual(summary["steps_failed"], 0)
        self.assertEqual(summary["output_values"]["files"], "main.py, app.py, count: 2")
        self.assertEqual(summary["output_values"]["count"], "2")
        self.assertEqual(summary["template_values"]["files"], "main.py, app.py, count: 2")
        self.assertEqual(summary["template_values"]["count"], 2)
        self.assertEqual(summary["output_value_types"]["files"], "list")
        self.assertEqual(summary["output_value_types"]["count"], "int")
        self.assertEqual(
            summary["output_value_sources"]["files"]["command"],
            "ls"
        )
        self.assertEqual(
            summary["output_value_sources"]["count"]["tool_name"],
            "run_command"
        )

        stored_outputs = self.memory.get_step_outputs(cycle_id)
        self.assertEqual(len(stored_outputs), 1)
        self.assertEqual(
            stored_outputs[0]["parsed_outputs"],
            {"files": ["main.py", "app.py", "count: 2"], "count": 2}
        )

        template_values = self.orchestrator._build_template_value_map(summary)
        formatted, _ = self.orchestrator._render_narration_template(
            "Found {count:.1f} files",
            template_values
        )
        self.assertEqual(formatted, "Found 2.0 files")

    def test_execute_plan_injects_no_output_message(self):
        """When stdout is empty, the orchestrator replaces values with a helpful note."""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="any bat files?"
        )
        plan = {
            "steps": [
                {
                    "id": 0,
                    "tool_name": "run_command",
                    "intent": "Search for BAT files",
                    "description": "Find *.bat files",
                    "output_keys": ["bat_files"]
                }
            ],
            "narration_template": "Found these files: {bat_files}"
        }
        self.memory.save_plan(cycle_id, plan, status="in_progress")

        agent_b_payload = {
            "success": True,
            "tool_args": {"command": "find . -name '*.bat'"},
            "command": "find . -name '*.bat'",
            "output_format": {"bat_files": "list"}
        }

        tool_result = {
            "success": True,
            "result": "",
            "stdout": "",
            "stderr": None,
            "raw_stdout": "",
            "raw_stderr": None,
            "exit_code": 0,
            "output_preview": "",
            "error": None,
            "latency_ms": 5
        }

        with patch.object(self.orchestrator, "_call_agent_b", return_value=agent_b_payload), \
             patch.object(self.orchestrator, "tool_executor") as mock_executor:
            mock_executor.execute.return_value = tool_result

            summary = self.orchestrator._execute_plan(
                cycle_id=cycle_id,
                query="any bat files?",
                plan=plan
            )

        fallback = summary["output_values"]["bat_files"]
        self.assertIn("Tool run_command", fallback)
        self.assertIn("find . -name '*.bat'", fallback)
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
        with patch.object(self.orchestrator, "_run_agent_a_cycle", side_effect=RuntimeError("boom")), \
             patch.object(self.orchestrator, "_call_agent_a_direct_response", return_value="fallback"):
            result = self.orchestrator.handle_query("boom")

        self.assertIsNotNone(result.error)
        failure = self.memory.get_cycle_failure(result.cycle_id)
        self.assertIsNotNone(failure)
        self.assertEqual(failure["error_type"], "RuntimeError")
        self.assertEqual(failure["stage"], "orchestrator")

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
        self.assertIn("tool failed", failure["payload"]["execution_result"]["error"])

    @patch("orchestrator.orchestrator.LLMClient")
    def test_execution_plan_path_does_not_exit_early(self, mock_llm_client):
        """Ensure execution-plan responses proceed without touching undefined agent_response."""
        # Fake LLM returning a simple execution plan
        plan_dict = {
            "response_type": "execution_plan",
            "steps": [
                {
                    "id": 0,
                    "tool_name": "run_command",
                    "description": "List files",
                    "output_keys": ["files"],
                    "intent": "List files"
                }
            ],
            "narration_template": "Files: {files}"
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
                 "step_results": []
             }), \
             patch.object(Orchestrator, "_render_narration_template", return_value=("Files: main.py", [{"type": "text", "content": "Files: main.py"}])):
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
            "response_type": "execution_plan",
            "steps": [
                {
                    "id": 0,
                    "tool_name": "run_command",
                    "description": "List files",
                    "output_keys": ["files"],
                    "intent": "List files"
                }
            ],
            "narration_template": "Files: {files}"
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
                 "step_results": []
             }), \
             patch.object(Orchestrator, "_render_narration_template", return_value=("Files: main.py", [{"type": "text", "content": "Files: main.py"}])), \
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


class TestAgentBOutputFormatValidation(unittest.TestCase):
    """Unit tests for Agent B payload normalization."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        self.config = Mock(spec=Config)
        self.config.model = "test-model"
        self.config.max_tokens = 512
        self.config.temperature = 0.1
        self.config.agent_a_temperature = 0.2
        self.config.agent_b_temperature = 0.0
        self.orchestrator = Orchestrator(self.config, self.memory)

    def tearDown(self):
        self.orchestrator.close()
        os.unlink(self.temp_db.name)

    def test_shell_payload_normalization(self):
        step = {"tool_name": "run_command", "output_keys": ["files", "count"]}
        payload = {
            "command": "ls -la",
            "output_format": {"files": "LIST", "count": "int"}
        }
        normalized = self.orchestrator._normalize_agent_b_payload(step, 0, payload)
        self.assertEqual(normalized["tool_args"]["command"], "ls -la")
        self.assertEqual(normalized["output_format"], {"files": "list", "count": "int"})

    def test_missing_output_key_raises_error(self):
        step = {"tool_name": "run_command", "output_keys": ["files", "count"]}
        payload = {
            "command": "ls -la",
            "output_format": {"files": "list"}
        }
        with pytest.raises(ValueError):
            self.orchestrator._normalize_agent_b_payload(step, 0, payload)


if __name__ == "__main__":
    unittest.main()
