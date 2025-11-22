import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
from pathlib import Path
import json

from orchestrator.orchestrator import Orchestrator
from orchestrator.plan_validator import PlanValidationError
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
        response.tool_calls = []
        
        mock_client_instance.call.return_value = {
            "message": response,
            "error": None
        }

        # Expect a single Agent A call and a validation error raised
        with self.assertRaises(PlanValidationError):
            self.orchestrator._run_agent_a_cycle(
                cycle_id="test-cycle",
                query="some query"
            )
        
        self.assertEqual(mock_client_instance.call.call_count, 1)

if __name__ == '__main__':
    unittest.main()
