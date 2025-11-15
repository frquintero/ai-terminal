"""
Unit tests for the routerless Orchestrator (Agent A-first flow).

Focuses on Agent A prompts, Agent B normalization, plan execution, and
handle_query bookkeeping without legacy CHAT/SHELL/CACHED branches.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from config import Config
from memory.api import Memory
from orchestrator.orchestrator import Orchestrator, OrchestratorResult
from orchestrator.prompts import (
    get_agent_a_narrator_prompt,
    get_agent_a_summarizer_prompt,
)
from orchestrator.routes import Route


class TestOrchestratorPrompts(unittest.TestCase):
    """Test Agent A prompt generation modes."""
    
    def test_get_agent_a_narrator_prompt(self):
        prompt = get_agent_a_narrator_prompt()
        self.assertIn("narrator", prompt.lower())
        self.assertIn("conversational", prompt.lower())
        self.assertIn("Tool Executed", prompt)
    
    def test_get_agent_a_summarizer_prompt(self):
        prompt = get_agent_a_summarizer_prompt()
        self.assertIn("summarizer", prompt.lower())
        self.assertIn("multi-step plan", prompt.lower())


class TestHandleQueryRouterless(unittest.TestCase):
    """Ensure handle_query always flows through Agent A."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        self.config = Mock(spec=Config)
        self.config.model = "gpt-4"
        self.config.max_tokens = 1024
        self.config.temperature = 0.2
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
        self.assertIn("1. User query: What is 5 — Cycle", context)
        self.assertNotIn("```", context)


class TestAgentBOutputFormatValidation(unittest.TestCase):
    """Unit tests for Agent B payload normalization."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        self.config = Mock(spec=Config)
        self.config.model = "test-model"
        self.config.max_tokens = 512
        self.config.temperature = 0.1
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
