"""
Unit tests for Orchestrator module (Phase 2)

Tests CHAT, SHELL, and CACHED route handlers
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from config import Config
from memory.api import Memory
from orchestrator.orchestrator import Orchestrator, OrchestratorResult
from orchestrator.prompts import get_agent_c_prompt
from router.cache import CacheHit
from orchestrator.routes import RouterResult, Route


class TestOrchestratorPrompts(unittest.TestCase):
    """Test Agent C prompt generation"""
    
    def test_get_agent_c_chat_prompt(self):
        """Agent C chat prompt includes system context"""
        prompt = get_agent_c_prompt("chat")
        
        self.assertIn("helpful AI assistant", prompt)
        self.assertIn("Operating System:", prompt)
        self.assertIn("Working Directory:", prompt)
    
    def test_get_agent_c_narrator_prompt(self):
        """Agent C narrator prompt includes tool context guidance"""
        prompt = get_agent_c_prompt("narrator")
        
        self.assertIn("narrator", prompt.lower())
        self.assertIn("conversational", prompt.lower())
        self.assertIn("Tool that was executed", prompt)
    
    def test_get_agent_c_summarizer_prompt(self):
        """Agent C summarizer prompt for multi-step tasks"""
        prompt = get_agent_c_prompt("summarizer")
        
        self.assertIn("summarizer", prompt.lower())
        self.assertIn("plan that was executed", prompt.lower())
    
    def test_invalid_mode_raises_error(self):
        """Invalid mode raises ValueError"""
        with self.assertRaises(ValueError) as ctx:
            get_agent_c_prompt("invalid_mode")
        
        self.assertIn("Invalid Agent C mode", str(ctx.exception))


class TestOrchestratorChatRoute(unittest.TestCase):
    """Test CHAT route handler"""
    
    def setUp(self):
        """Create test orchestrator with mocked Memory"""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        
        self.config = Mock(spec=Config)
        self.config.model = "gpt-4"
        self.config.max_tokens = 500
        self.config.temperature = 0.7
        
        self.orchestrator = Orchestrator(
            config=self.config,
            memory=self.memory
        )
    
    def tearDown(self):
        """Clean up test database"""
        self.orchestrator.close()
        os.unlink(self.temp_db.name)
    
    @patch.object(Orchestrator, "_classify_query")
    @patch("orchestrator.orchestrator.LLMClient")
    def test_chat_route_calls_agent_a(self, mock_llm_client_class, mock_classify):
        """CHAT route calls Agent A with chat history"""
        mock_classify.return_value = RouterResult(
            route=Route.CHAT,
            confidence=0.85,
            latency_ms=10
        )
        
        # Mock LLM response
        mock_llm_client = Mock()
        mock_message = Mock()
        mock_message.content = "The capital of France is Paris."
        mock_llm_client.call.return_value = {
            "message": mock_message,
            "usage": {"total_tokens": 50},
            "latency_ms": 200,
            "trace_id": "test123",
            "error": None
        }
        mock_llm_client_class.return_value = mock_llm_client
        
        # Execute query
        result = self.orchestrator.handle_query("What is the capital of France?")
        
        # Verify
        self.assertEqual(result.route, "CHAT")
        self.assertEqual(result.agent_c_response, "The capital of France is Paris.")
        self.assertIsNone(result.error)
        
        # Verify LLM was called with correct role and messages
        mock_llm_client.call.assert_called_once()
        call_args = mock_llm_client.call.call_args
        messages = call_args[1]["messages"]
        
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("helpful AI assistant", messages[0]["content"])
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], "What is the capital of France?")
    
    @patch.object(Orchestrator, "_classify_query")
    @patch("orchestrator.orchestrator.LLMClient")
    def test_chat_route_preserves_context(self, mock_llm_client_class, mock_classify):
        """CHAT route includes previous chat history in context"""
        mock_classify.return_value = RouterResult(
            route=Route.CHAT,
            confidence=0.85,
            latency_ms=10
        )
        
        mock_llm_client = Mock()
        mock_message = Mock()
        mock_message.content = "Response"
        mock_llm_client.call.return_value = {
            "message": mock_message,
            "usage": {},
            "latency_ms": 100,
            "trace_id": "test",
            "error": None
        }
        mock_llm_client_class.return_value = mock_llm_client
        
        # First query
        self.orchestrator.handle_query("What is Python?")
        
        # Second query - should include first in context
        self.orchestrator.handle_query("What about Ruby?")
        
        # Check second call included first exchange
        second_call_args = mock_llm_client.call.call_args_list[1]
        messages = second_call_args[1]["messages"]
        
        # Should have: system, user1, assistant1, user2
        user_messages = [m for m in messages if m["role"] == "user"]
        self.assertEqual(len(user_messages), 2)
        self.assertEqual(user_messages[0]["content"], "What is Python?")
        self.assertEqual(user_messages[1]["content"], "What about Ruby?")


class TestOrchestratorShellRoute(unittest.TestCase):
    """Test SHELL route handler"""
    
    def setUp(self):
        """Create test orchestrator"""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        
        self.config = Mock(spec=Config)
        self.config.model = "gpt-4"
        self.config.max_tokens = 500
        self.config.temperature = 0.7
        
        self.orchestrator = Orchestrator(self.config, self.memory)
    
    def tearDown(self):
        """Clean up"""
        self.orchestrator.close()
        os.unlink(self.temp_db.name)
    
    @patch.object(Orchestrator, "_classify_query")
    @patch("orchestrator.orchestrator.LLMClient")
    def test_shell_route_executes_command(
        self,
        mock_llm_client_class,
        mock_classify
    ):
        """SHELL route executes command and calls Agent A narrator"""
        mock_classify.return_value = RouterResult(
            route=Route.SHELL,
            confidence=0.95,
            latency_ms=5,
            matched_rule=r"^ls\b"
        )
        
        # Mock tool execution
        mock_tool_executor = Mock()
        mock_tool_executor.execute.return_value = {
            "success": True,
            "result": "file1.txt\nfile2.txt\n",
            "exit_code": 0,
            "error": None
        }
        self.orchestrator.tool_executor = mock_tool_executor
        
        # Mock Agent A narrator
        mock_llm_client = Mock()
        mock_message = Mock()
        mock_message.content = "I found 2 files: file1.txt and file2.txt"
        mock_llm_client.call.return_value = {
            "message": mock_message,
            "usage": {},
            "latency_ms": 150,
            "trace_id": "test",
            "error": None
        }
        mock_llm_client_class.return_value = mock_llm_client
        
        # Execute
        result = self.orchestrator.handle_query("ls")
        
        # Verify execution
        self.assertEqual(result.route, "SHELL")
        self.assertTrue(result.execution_result["success"])
        self.assertEqual(result.execution_result["exit_code"], 0)
        
        # Verify tool was called
        mock_tool_executor.execute.assert_called_once()
        call_args = mock_tool_executor.execute.call_args
        self.assertEqual(call_args[1]["tool_name"], "run_command")
        self.assertEqual(call_args[1]["tool_args"]["command"], "ls")
        
        # Verify Agent C narrator was called
        mock_llm_client.call.assert_called_once()
        narrator_messages = mock_llm_client.call.call_args[1]["messages"]
        self.assertIn("narrator", narrator_messages[0]["content"].lower())
    
    @patch.object(Orchestrator, "_classify_query")
    @patch("orchestrator.orchestrator.LLMClient")
    def test_shell_route_caches_success(
        self,
        mock_llm_client_class,
        mock_classify
    ):
        """SHELL route caches successful executions"""
        mock_classify.return_value = RouterResult(
            route=Route.SHELL,
            confidence=0.95,
            latency_ms=5
        )
        
        mock_tool_executor = Mock()
        mock_tool_executor.execute.return_value = {
            "success": True,
            "result": "output",
            "exit_code": 0,
            "error": None
        }
        self.orchestrator.tool_executor = mock_tool_executor
        
        mock_llm_client = Mock()
        mock_message = Mock()
        mock_message.content = "Success"
        mock_llm_client.call.return_value = {
            "message": mock_message,
            "usage": {},
            "latency_ms": 100,
            "trace_id": "test",
            "error": None
        }
        mock_llm_client_class.return_value = mock_llm_client
        
        # Execute
        self.orchestrator.handle_query("pwd")
        
        # Verify cache entry was created
        cache_results = self.memory.search_intention_cache("pwd", limit=1)
        self.assertEqual(len(cache_results), 1)
        self.assertEqual(cache_results[0]["tool_name"], "run_command")
        self.assertEqual(cache_results[0]["tool_args"]["command"], "pwd")


class TestOrchestratorCachedRoute(unittest.TestCase):
    """Test CACHED route handler"""
    
    def setUp(self):
        """Create test orchestrator"""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        
        self.config = Mock(spec=Config)
        self.config.model = "gpt-4"
        
        self.orchestrator = Orchestrator(self.config, self.memory)
    
    def tearDown(self):
        """Clean up"""
        self.orchestrator.close()
        os.unlink(self.temp_db.name)
    
    @patch.object(Orchestrator, "_classify_query")
    @patch("orchestrator.orchestrator.LLMClient")
    def test_cached_route_reuses_execution(
        self,
        mock_llm_client_class,
        mock_classify
    ):
        """CACHED route retrieves and executes cached tool"""
        # Pre-populate cache
        self.memory.add_to_intention_cache(
            user_query="list files",
            normalized_intent="list files",
            tool_name="run_command",
            tool_args={"command": "ls -la"},
            success=True
        )
        
        # Mock router to return CACHED with cache hit
        cache_hit = CacheHit(
            cache_id=1,
            tool_name="run_command",
            tool_args={"command": "ls -la"},
            user_query="list files",
            score=-1.5,
            usage_count=1
        )
        
        mock_classify.return_value = RouterResult(
            route=Route.CACHED,
            confidence=0.90,
            latency_ms=8,
            cache_hit=cache_hit
        )
        
        # Mock tool execution
        mock_tool_executor = Mock()
        mock_tool_executor.execute.return_value = {
            "success": True,
            "result": "total 8\n-rw-r--r-- 1 user user 100 Nov 11 file.txt\n",
            "exit_code": 0,
            "error": None
        }
        self.orchestrator.tool_executor = mock_tool_executor
        
        # Mock Agent C narrator
        mock_llm_client = Mock()
        mock_message = Mock()
        mock_message.content = "Here are your files..."
        mock_llm_client.call.return_value = {
            "message": mock_message,
            "usage": {},
            "latency_ms": 120,
            "trace_id": "test",
            "error": None
        }
        mock_llm_client_class.return_value = mock_llm_client
        
        # Recreate orchestrator with mocks
        # Execute
        result = self.orchestrator.handle_query("list files")
        
        # Verify route
        self.assertEqual(result.route, "CACHED")
        self.assertIsNotNone(result.execution_result.get("cache_hit"))
        
        # Verify tool was executed with cached args
        mock_tool_executor.execute.assert_called_once()
        call_args = mock_tool_executor.execute.call_args
        self.assertEqual(call_args[1]["tool_name"], "run_command")
        self.assertEqual(call_args[1]["tool_args"]["command"], "ls -la")
        
        # Verify cache usage was incremented
        cache_entries = self.memory.search_intention_cache("list files", limit=1)
        self.assertEqual(cache_entries[0]["usage_count"], 2)


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
    
    def test_cycle_id_generated(self):
        """Each query generates unique cycle_id"""
        with patch.object(Orchestrator, "_classify_query") as mock_classify:
            mock_classify.return_value = RouterResult(
                route=Route.PLANNER,
                confidence=0.5,
                latency_ms=10
            )
            
            result = self.orchestrator.handle_query("test query")
            
            # Verify cycle was created
            self.assertIsNotNone(result.cycle_id)
            
            # Verify router decision was logged
            decision = self.memory.get_router_decision(result.cycle_id)
            self.assertIsNotNone(decision)
            self.assertEqual(decision["query_text"], "test query")
            self.assertEqual(decision["route"], "PLANNER")


if __name__ == "__main__":
    unittest.main()
