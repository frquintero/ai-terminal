import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
from pathlib import Path
import json

from orchestrator.orchestrator import Orchestrator
from memory.api import Memory
from config import Config

class TestAgentBRetry(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.memory = Memory(db_path=Path(self.temp_db.name))
        self.config = Mock(spec=Config)
        self.config.agent_b_temperature = 0.0
        self.config.model = "test-model"
        self.orchestrator = Orchestrator(self.config, self.memory)

    def tearDown(self):
        self.orchestrator.close()
        os.unlink(self.temp_db.name)

    @patch("orchestrator.orchestrator.LLMClient")
    def test_agent_b_retry_on_missing_keys(self, MockLLMClient):
        # Setup mock LLM client
        mock_client_instance = MockLLMClient.return_value
        
        # First response: Missing output_format
        response1 = MagicMock()
        response1.content = json.dumps({
            "command": "ls -la",
            "output_format": {}  # Missing 'files' key
        })
        
        # Second response: Correct
        response2 = MagicMock()
        response2.content = json.dumps({
            "command": "ls -la",
            "output_format": {"files": "list"}
        })
        
        # Configure side_effect for call()
        mock_client_instance.call.side_effect = [
            {"message": response1, "error": None},
            {"message": response2, "error": None}
        ]
        
        # Plan and step setup
        plan = {
            "steps": [
                {
                    "tool_name": "run_command",
                    "intent": "List files",
                    "output_keys": ["files"]
                }
            ]
        }
        
        # Execute
        result = self.orchestrator._call_agent_b(
            cycle_id="test-cycle",
            plan=plan,
            step_id=0,
            previous_results=[]
        )
        
        # Verify success
        self.assertTrue(result["success"])
        self.assertEqual(result["output_format"], {"files": "list"})
        
        # Verify retry happened (2 calls)
        self.assertEqual(mock_client_instance.call.call_count, 2)
        
        # Verify error message was passed in second call
        # call_args_list contains (args, kwargs) tuples
        # call() is called with keyword arguments in the implementation
        second_call_kwargs = mock_client_instance.call.call_args_list[1].kwargs
        messages = second_call_kwargs['messages']
        self.assertEqual(messages[-1]['role'], 'user')
        self.assertIn("Agent B output_format missing keys", messages[-1]['content'])

if __name__ == '__main__':
    unittest.main()
