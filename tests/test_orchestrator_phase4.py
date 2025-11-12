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
        """Test simple plan execution (single step)"""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="list files"
        )
        
        # Create simple plan
        plan = {
            "steps": [
                {
                    "tool_name": "run_command",
                    "tool_args": {"command": "echo 'test execution'"},
                    "description": "Test echo command"
                }
            ]
        }
        
        # Save plan
        self.memory.save_plan(cycle_id=cycle_id, plan=plan, status="in_progress")
        
        # Execute plan
        result = self.orchestrator._execute_plan(cycle_id, "list files", plan)
        
        # Verify results
        self.assertEqual(result["total_steps"], 1)
        self.assertEqual(result["steps_completed"], 1)
        self.assertEqual(result["steps_failed"], 0)
        self.assertTrue(result["success"])
        
        # Check step result
        step_result = result["step_results"][0]
        self.assertEqual(step_result["step_id"], 0)
        self.assertEqual(step_result["tool_name"], "run_command")
        self.assertTrue(step_result["success"])
        self.assertIn("test execution", step_result["output"])
    
    def test_execute_plan_multi_step_with_variables(self):
        """Test multi-step plan with variable substitution"""
        cycle_id = self.memory.create_cycle(
            session_id=self.orchestrator.session_id,
            query="create and read file"
        )
        
        # Create multi-step plan with variable substitution
        plan = {
            "steps": [
                {
                    "tool_name": "run_command",
                    "tool_args": {"command": "echo 'hello world'"},
                    "description": "Generate content"
                },
                {
                    "tool_name": "write_file",
                    "tool_args": {
                        "file_path": "test_output.txt",
                        "content": "$PREVIOUS_OUTPUT"
                    },
                    "description": "Write output to file"
                },
                {
                    "tool_name": "read_file",
                    "tool_args": {"file_path": "ai-terminal-wd/test_output.txt"},
                    "description": "Read back the file"
                }
            ]
        }
        
        # Save and execute plan
        self.memory.save_plan(cycle_id=cycle_id, plan=plan, status="in_progress")
        result = self.orchestrator._execute_plan(cycle_id, "create and read file", plan)
        
        # Verify results
        self.assertEqual(result["total_steps"], 3)
        self.assertEqual(result["steps_completed"], 3)
        self.assertEqual(result["steps_failed"], 0)
        self.assertTrue(result["success"])
        
        # Check that file contains the echo output
        step2_result = result["step_results"][2]
        self.assertIn("hello world", step2_result["output"])


if __name__ == "__main__":
    unittest.main()
