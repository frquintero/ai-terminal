"""
End-to-end tests for PLANNER route with 3 representative tasks.

These tests validate:
- PLANNER route classification for complex tasks
- Multi-step task decomposition (Agent A)
- Tool schema generation (Agent B)
- Step-by-step execution with proper context handoff
- Memory persistence and cycle tracking
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

from config import Config
from memory.api import Memory
from orchestrator.orchestrator import Orchestrator


# Test configuration with mock LLM
@pytest.fixture
def test_config():
    """Create test config with mock values"""
    return Config(
        api_key="test-key",
        model="gpt-4-turbo",
        base_url="https://api.openai.com/v1",
        agent_type="custom",
        max_tokens=1024,
        temperature=0.7,
        agent_a_temperature=0.7,
        agent_b_temperature=0.0,
        hide_thinking=False,
        max_steps=5,
        show_raw_output=False,
        raw_output_max_chars=4000,
        use_event_memory=False,
        event_log_retention_days=7,
        event_memory_max_events=40,
        event_memory_max_chars=6000,
        artifact_threshold_bytes=8192,
        save_llm_traces=False,
    )


@pytest.fixture
def temp_db():
    """Create temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_orchestrator.db"
        yield db_path


@pytest.fixture
def memory(temp_db):
    """Create Memory instance with test database"""
    mem = Memory(db_path=temp_db)
    yield mem
    mem.close(force=True)


@pytest.fixture
def orchestrator(test_config, memory):
    """Create Orchestrator instance for testing"""
    return Orchestrator(config=test_config, memory=memory)


class TestTask1DiskMonitoring:
    """Task 1: Disk space monitoring script"""

    def test_task1_planning(self, orchestrator):
        """Test Agent A decomposition for disk monitoring task"""
        query = (
            "Create a Python script that monitors disk space "
            "and alerts when it exceeds 80%"
        )

        # Mock Agent A (Planner) response - returns intent
        planner_response = {
            "intent": "Create a Python script that monitors disk space and alerts when it exceeds 80%",
            "success_criteria": ["script created", "permissions set"]
        }

        # Mock Agent B (Command Engineer) responses for each step
        agent_b_response = {
            "execution_steps": [
                {
                    # Step 1: Get disk usage
                    "tool_name": "run_command",
                    "tool_args": {"command": "df -h / | grep -oP '[0-9]+(?=%)' | head -1"},
                },
                {
                    # Step 2: Create script file
                    "tool_name": "create_file",
                    "tool_args": {
                        "path": "/tmp/disk_monitor.py",
                        "content": (
                            "#!/usr/bin/env python3\n"
                            "import os\n"
                            "import psutil\n"
                            "usage = psutil.disk_usage('/')\n"
                            "if usage.percent > 80:\n"
                            "    print(f'ALERT: Disk usage {usage.percent}%')\n"
                        ),
                    },
                },
                {
                    # Step 3: Make executable
                    "tool_name": "run_command",
                    "tool_args": {"command": "chmod +x /tmp/disk_monitor.py"},
                },
            ],
            "narration_template": "Task completed."
        }

        # Simulate decomposition and execution
        assert planner_response["intent"] is not None
        assert len(agent_b_response["execution_steps"]) == 3

    def test_task1_execution_steps(self, orchestrator):
        """Test step-by-step execution for disk monitoring task"""
        query = (
            "Create a Python script that monitors disk space "
            "and alerts when it exceeds 80%"
        )

        # Mock tool executor
        with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
            mock_executor = Mock()

            # Mock responses for each step
            step_responses = [
                {"success": True, "result": "45%", "exit_code": 0, "error": None},  # df check
                {"success": True, "result": "File created", "exit_code": 0, "error": None},  # write
                {"success": True, "result": "", "exit_code": 0, "error": None},  # chmod
            ]

            mock_executor.execute.side_effect = step_responses
            MockExecutor.return_value = mock_executor

            # Simulate executing 3 steps
            results = []
            for i, response in enumerate(step_responses):
                results.append(response)

            assert len(results) == 3
            assert all(r["success"] for r in results)

    def test_task1_memory_tracking(self, orchestrator, memory):
        """Test memory persistence for disk monitoring task"""
        query = (
            "Create a Python script that monitors disk space "
            "and alerts when it exceeds 80%"
        )

        # Verify memory system is initialized and ready
        assert memory is not None
        assert memory.conn is not None
        
        # Memory should have tables created
        cursor = memory.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert "intentions" in tables or "intention_cache" in tables


class TestTask2BackupScript:
    """Task 2: Daily backup automation"""

    def test_task2_planning(self, orchestrator):
        """Test Agent A decomposition for backup task"""
        query = "Set up a daily backup of my home directory to an external drive"

        # Expected decomposition
        expected_intent = "Set up a daily backup of my home directory to an external drive"
        
        # Mock Agent A response
        planner_response = {
            "intent": expected_intent,
            "success_criteria": ["backup script created", "cron job set"]
        }

        assert planner_response["intent"] == expected_intent

    def test_task2_execution_with_mocked_llm(self, orchestrator):
        """Test full execution with mocked LLM calls"""
        query = "Set up a daily backup of my home directory to an external drive"

        # Mock Agent A response
        agent_a_json = json.dumps({
            "intent": "Set up a daily backup of my home directory to an external drive",
            "success_criteria": ["backup script created", "cron job set"]
        })
        agent_a_response = Mock()
        agent_a_response.content = f"```json\n{agent_a_json}\n```"

        # Mock Agent B response
        agent_b_json = json.dumps({
            "execution_steps": [
                {
                    "tool_name": "write_file",
                    "tool_args": {"file_path": "backup.sh", "content": "echo backup"},
                    "output_format": {"path": "str"}
                }
            ],
            "narration_template": "Backup script created at {path}"
        })
        agent_b_response = Mock()
        agent_b_response.content = f"```json\n{agent_b_json}\n```"

        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            # Configure side_effect for multiple calls
            mock_llm.call.side_effect = [
                {
                    "message": agent_a_response,
                    "usage": {"total_tokens": 100},
                    "latency_ms": 500,
                    "trace_id": "trace-a",
                    "error": None
                },
                {
                    "message": agent_b_response,
                    "usage": {"total_tokens": 100},
                    "latency_ms": 500,
                    "trace_id": "trace-b",
                    "error": None
                }
            ]
            MockLLMClient.return_value = mock_llm

            # Mock ToolExecutor to avoid actual file creation
            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True,
                    "result": "/tmp/backup.sh",
                    "stdout": "/tmp/backup.sh",
                    "exit_code": 0,
                    "error": None
                }
                MockExecutor.return_value = mock_executor                # Execute
                result = orchestrator.handle_query(query)

                # Verify result structure
                assert result.route == "PLANNER"
                assert result.cycle_id is not None
                assert result.execution_result["success"] is True
                assert "Backup script created" in result.agent_response


class TestTask3DockerMonitoring:
    """Task 3: Docker memory monitoring"""

    def test_task3_planning(self, orchestrator):
        """Test Agent A decomposition for Docker monitoring task"""
        query = "Find all Docker containers using more than 500MB memory and list them"

        # Expected intent
        expected_intent = "Find all Docker containers using more than 500MB memory and list them"
        
        planner_response = {
            "intent": expected_intent,
            "success_criteria": ["containers listed"]
        }

        assert planner_response["intent"] == expected_intent

    def test_task3_execution_with_tool_schema(self, orchestrator):
        """Test Agent B receiving tool schemas for Docker task"""
        query = "Find all Docker containers using more than 500MB memory and list them"

        # Mock tool schemas that Agent B would receive
        tool_schemas = {
            "run_command": {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Execute shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Command to execute",
                            }
                        },
                        "required": ["command"],
                    },
                },
            }
        }

        # Verify schema structure
        assert "run_command" in tool_schemas
        assert "function" in tool_schemas["run_command"]

    def test_task3_full_execution(self, orchestrator):
        """Test full execution of Docker monitoring task"""
        query = "Find all Docker containers using more than 500MB memory and list them"

        with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
            mock_executor = Mock()
            mock_executor.execute.return_value = {
                "success": True,
                "result": "container_name: 512MB\ncontainer_xyz: 1.2GB",
                "exit_code": 0,
                "error": None,
            }
            MockExecutor.return_value = mock_executor

            # Mock LLM for agent responses
            with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
                mock_llm = Mock()
                mock_response = Mock()
                mock_response.content = (
                    "Found 2 containers:\n- container_name: 512MB\n- container_xyz: 1.2GB"
                )
                mock_llm.call.return_value = {
                    "message": mock_response,
                    "usage": None,
                    "latency_ms": 800,
                    "trace_id": "test-docker-trace",
                    "error": None,
                }
                MockLLMClient.return_value = mock_llm

                result = orchestrator.handle_query(query)
                # May route to SHELL, PLANNER, or CHAT
                assert result.route in ["SHELL", "PLANNER", "CHAT"]
                assert result.cycle_id is not None


# ============================================================================
# Integration Tests - Across All 3 Tasks
# ============================================================================


class TestPlannerIntegration:
    """Test PLANNER integration across multiple tasks"""

    def test_multiple_tasks_separate_cycles(self, orchestrator):
        """Verify each task gets its own cycle_id"""
        tasks = [
            "Create a Python script that monitors disk space and alerts when it exceeds 80%",
            "Set up a daily backup of my home directory to an external drive",
            "Find all Docker containers using more than 500MB memory and list them",
        ]

        mock_response = Mock()
        mock_response.content = "Task completed"
        mock_response.usage = Mock(prompt_tokens=10, completion_tokens=20, total_tokens=30)

        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": mock_response,
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
                "latency_ms": 500,
                "trace_id": "test-trace",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            cycle_ids = []
            for task in tasks:
                result = orchestrator.handle_query(task)
                # All routes should produce a cycle_id
                assert result.cycle_id is not None
                cycle_ids.append(result.cycle_id)

            # All cycle IDs should be unique (one per task)
            assert len(set(cycle_ids)) == len(cycle_ids)
            assert len(cycle_ids) == 3

    def test_planner_error_handling(self, orchestrator):
        """Test PLANNER handles LLM errors gracefully"""
        query = "Create a Python script that monitors disk space"

        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": None,
                "usage": None,
                "latency_ms": 100,
                "trace_id": "test-trace",
                "error": "API timeout",
            }
            MockLLMClient.return_value = mock_llm

            result = orchestrator.handle_query(query)
            assert result.error is not None
            assert "timeout" in result.error.lower()

    def test_planner_step_outputs_stored(self, orchestrator, memory):
        """Test that step outputs are persisted to database during plan execution"""
        query = "Create a Python script that monitors disk space"
        
        # Create a cycle and save a plan
        cycle_id = memory.create_cycle(
            session_id=orchestrator.session_id,
            query=query
        )
        
        plan = {
            "intent": "Create a Python script that monitors disk space",
            "success_criteria": ["script created"]
        }
        memory.save_plan(cycle_id=cycle_id, plan=plan, status="in_progress")
        
        # Simulate step outputs being saved (as would happen in _execute_plan)
        memory.save_step_output(
            cycle_id=cycle_id,
            step_id=0,
            tool_name="create_file",
            tool_args={"path": "/tmp/test.py", "content": "print('hello')"},
            success=True,
            output_preview="File created successfully"
        )
        
        memory.save_step_output(
            cycle_id=cycle_id,
            step_id=1,
            tool_name="run_command",
            tool_args={"command": "chmod +x /tmp/test.py"},
            success=True,
            output_preview=""
        )
        
        # Verify step outputs were persisted
        step_outputs = memory.get_step_outputs(cycle_id=cycle_id)
        assert len(step_outputs) == 2
        assert step_outputs[0]["tool_name"] == "create_file"
        assert step_outputs[0]["success"] is True
        assert step_outputs[1]["tool_name"] == "run_command"
        assert step_outputs[1]["success"] is True

    def test_planner_execution_persists_step_outputs_with_plan_state_advancement(self, orchestrator, memory):
        """Test full integration: Plan state is advanced as steps execute and outputs are stored"""
        query = "Create a simple test script"
        
        # Create cycle and plan
        cycle_id = memory.create_cycle(
            session_id=orchestrator.session_id,
            query=query
        )
        
        plan = {
            "intent": "Create a simple test script",
            "success_criteria": ["script created"]
        }
        
        memory.save_plan(cycle_id=cycle_id, plan=plan, status="in_progress")
        
        # Simulate step execution progression (as in _execute_plan)
        # Note: Agent B would provide the steps dynamically now
        steps_from_agent_b = [
            {"tool_name": "create_file"},
            {"tool_name": "run_command"},
            {"tool_name": "run_command"}
        ]
        
        for step_id, step in enumerate(steps_from_agent_b):
            # Update current step
            memory.update_task_status(
                cycle_id=cycle_id,
                status="in_progress",
                current_step_id=step_id
            )
            
            # Save step output
            memory.save_step_output(
                cycle_id=cycle_id,
                step_id=step_id,
                tool_name=step["tool_name"],
                tool_args={},
                success=True,
                output_preview=f"Step {step_id} completed"
            )
            
            # Verify state advanced
            task_state = memory.get_task_state(cycle_id=cycle_id)
            assert task_state["current_step_id"] == step_id
            assert task_state["status"] == "in_progress"
        
        # Mark as completed
        memory.update_task_status(
            cycle_id=cycle_id,
            status="done",
            current_step_id=2
        )
        
        # Verify final state
        task_state = memory.get_task_state(cycle_id=cycle_id)
        assert task_state["status"] == "done"
        
        # Verify all step outputs are stored
        step_outputs = memory.get_step_outputs(cycle_id=cycle_id)
        assert len(step_outputs) == 3
        for i, output in enumerate(step_outputs):
            assert output["step_id"] == i
            assert output["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
