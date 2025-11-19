import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
from pathlib import Path
import json

from orchestrator.orchestrator import Orchestrator
from memory.api import Memory
from config import Config

class TestFailFast(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        self.config = Mock(spec=Config)
        self.config.agent_a_temperature = 0.0
        self.config.agent_b_temperature = 0.0
        self.config.model = "test-model"
        self.orchestrator = Orchestrator(self.config, self.memory)

    def tearDown(self):
        self.orchestrator.close()
        os.unlink(self.temp_db.name)

    @patch("orchestrator.orchestrator.LLMClient")
    def test_agent_a_no_retry(self, MockLLMClient):
        """Verify Agent A fails immediately on invalid JSON without retrying"""
        mock_client_instance = MockLLMClient.return_value
        
        # Return invalid JSON (string response instead of JSON)
        response = MagicMock()
        response.content = "I'm not giving you JSON!"
        
        mock_client_instance.call.return_value = {
            "message": response,
            "error": None
        }

        # Execute
        # Note: _run_agent_a_cycle catches the failure and returns a fallback response,
        # but it should do so after ONE call, not multiple.
        # We mock _call_agent_a_direct_response to avoid the fallback LLM call complicating things,
        # or just count the calls.
        
        # We'll let it run. The result should be the fallback explanation.
        with patch.object(self.orchestrator, '_call_agent_a_direct_response', return_value="Fallback explanation") as mock_fallback:
            result = self.orchestrator._run_agent_a_cycle(
                cycle_id="test-cycle",
                query="some query"
            )
        
        # Verify only 1 call to Agent A (plus maybe fallback, but we patched that)
        # Wait, _run_agent_a_cycle creates a NEW LLMClient.
        # Our mock_client_instance mocks the return value of the constructor.
        
        self.assertEqual(mock_client_instance.call.call_count, 1)
        
        # Verify result indicates error/fallback
        self.assertEqual(result.agent_response, "Fallback explanation")

    @patch("orchestrator.orchestrator.LLMClient")
    def test_agent_b_no_retry(self, MockLLMClient):
        """Verify Agent B fails immediately on invalid JSON without retrying"""
        mock_client_instance = MockLLMClient.return_value
        
        # Return invalid JSON
        response = MagicMock()
        response.content = "Invalid JSON"
        
        mock_client_instance.call.return_value = {
            "message": response,
            "error": None
        }
        
        plan = {"intent": "foo", "tools": ["bar"]}

        # Execute
        result = self.orchestrator._get_execution_manifest(
            cycle_id="test-cycle",
            plan=plan
        )
        
        # Verify failure
        self.assertFalse(result["success"])
        # Error message depends on parser logic, but it should be an error
        self.assertTrue(result["error"]) 
        
        # Verify only 1 call
        self.assertEqual(mock_client_instance.call.call_count, 1)

if __name__ == '__main__':
    unittest.main()
