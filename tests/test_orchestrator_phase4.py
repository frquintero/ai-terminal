"""
Tests for Phase 4: Agent B executor and plan execution
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from memory.api import Memory
from orchestrator.orchestrator import Orchestrator


class TestPhase4Executor(unittest.TestCase):
    """Test Agent B executor and plan execution"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create temp database for testing
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_orchestrator.db"
        
        # Create test config
        self.config = Config(
            api_key="test-key",
            model="test-model",
            base_url="https://api.test.com",
            agent_type="custom",
            max_tokens=1024,
            temperature=0.7,
            agent_a_temperature=0.2,
            agent_b_temperature=0.0,
            save_llm_traces=False,
            hide_thinking=True,
            max_steps=15,
            show_raw_output=False,
            raw_output_max_chars=4000,
            use_event_memory=False,
            event_log_retention_days=7,
            event_memory_max_events=40,
            event_memory_max_chars=6000,
            artifact_threshold_bytes=8192
        )
        
        # Create memory and orchestrator
        self.memory = Memory(db_path=self.db_path)
        self.orchestrator = Orchestrator(config=self.config, memory=self.memory)
    
    def tearDown(self):
        """Clean up test fixtures"""
        self.orchestrator.close()
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_variable_substitution(self):
        """Test $PREVIOUS_OUTPUT and $STEP_N_OUTPUT substitution"""
        tool_args = {
            "command": "echo $PREVIOUS_OUTPUT",
            "file_path": "output_$STEP_0_OUTPUT.txt"
        }
        
        previous_results = [
            {"output": "hello world"},
            {"output": "test123"}
        ]
        
        result = self.orchestrator._substitute_step_variables(tool_args, previous_results)
        
        self.assertEqual(result["command"], "echo test123")
        self.assertEqual(result["file_path"], "output_hello world.txt")
    
    def test_execute_plan_simple(self):
        """Test simple plan execution (single step) - NOTE: Requires LLM for Agent B"""
        # Skip this test - it requires actual LLM calls for Agent B
        # This is an integration test that should be run separately
        self.skipTest("Requires LLM for Agent B - run as integration test")
    
    def test_execute_plan_multi_step_with_variables(self):
        """Test multi-step plan with variable substitution - NOTE: Requires LLM for Agent B"""
        # Skip this test - it requires actual LLM calls for Agent B
        # This is an integration test that should be run separately
        self.skipTest("Requires LLM for Agent B - run as integration test")


if __name__ == "__main__":
    unittest.main()
