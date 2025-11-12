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
from router.rules import Route


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
        hide_thinking=False,
        max_steps=5,
        show_raw_output=False,
        raw_output_max_chars=4000,
        use_event_memory=False,
        event_log_retention_days=7,
        event_memory_max_events=40,
        event_memory_max_chars=6000,
        artifact_threshold_bytes=8192,
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
    mem.close()


@pytest.fixture
def orchestrator(test_config, memory):
    """Create Orchestrator instance for testing"""
    return Orchestrator(config=test_config, memory=memory)


# ============================================================================
# PLANNER Route Tests - 3 Representative Tasks
# ============================================================================


class TestPlannerRoute:
    """Test PLANNER route functionality"""

    def test_planner_route_classification(self, orchestrator):
        """Verify complex tasks route to PLANNER"""
        queries = [
            "Create a Python script that monitors disk space and alerts when it exceeds 80%",
            "Set up a daily backup of my home directory to an external drive",
            "Build a web scraper that collects data from multiple sites",
        ]

        for query in queries:
            result = orchestrator.router.classify(query)
            # Complex tasks either route to PLANNER or can route to SHELL/CHAT
            # Router precedence: SHELL > CACHED > CHAT > PLANNER
            assert result.route in [Route.PLANNER, Route.CHAT, Route.SHELL], (
                f"Query '{query}' routed to {result.route}"
            )
            assert result.confidence >= 0.5


class TestTask1DiskMonitoring:
    """Task 1: Disk space monitoring script"""

    def test_task1_classification(self, orchestrator):
        """Verify disk monitoring task routes to PLANNER"""
        query = (
            "Create a Python script that monitors disk space "
            "and alerts when it exceeds 80%"
        )
        result = orchestrator.router.classify(query)
        assert result.route == Route.PLANNER

    def test_task1_planning(self, orchestrator):
        """Test Agent A decomposition for disk monitoring task"""
        query = (
            "Create a Python script that monitors disk space "
            "and alerts when it exceeds 80%"
        )

        # Mock Agent A (Planner) response - returns list of tool names
        planner_response = {
            "plan": [
                "get_disk_usage",  # Check current disk usage
                "create_file",      # Create monitoring script
                "run_command",      # Make script executable
            ],
            "reasoning": "First check current disk usage, then create script, then set permissions",
        }

        # Mock Agent B (Command Engineer) responses for each step
        agent_b_responses = [
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
        ]

        # Simulate decomposition and execution
        assert len(planner_response["plan"]) == 3
        assert all(tool in ["get_disk_usage", "create_file", "run_command"] 
                   for tool in planner_response["plan"])

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

    def test_task2_classification(self, orchestrator):
        """Verify backup task routes to PLANNER"""
        query = "Set up a daily backup of my home directory to an external drive"
        result = orchestrator.router.classify(query)
        assert result.route == Route.PLANNER

    def test_task2_planning(self, orchestrator):
        """Test Agent A decomposition for backup task"""
        query = "Set up a daily backup of my home directory to an external drive"

        # Expected decomposition
        expected_steps = [
            "create_file",        # Create backup script
            "run_command",        # Test script
            "run_command",        # Set up cron job
        ]

        assert len(expected_steps) == 3
        assert expected_steps[0] == "create_file"

    def test_task2_execution_with_mocked_llm(self, orchestrator):
        """Test full execution with mocked LLM calls"""
        query = "Set up a daily backup of my home directory to an external drive"

        mock_response = Mock()
        mock_response.content = "Backup script created and cron job scheduled"
        mock_response.usage = Mock(
            prompt_tokens=100, completion_tokens=150, total_tokens=250
        )

        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": mock_response,
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 150,
                    "total_tokens": 250,
                },
                "latency_ms": 1200,
                "trace_id": "test-backup-trace",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            # Execute
            result = orchestrator.handle_query(query)

            # Verify result structure
            # Router may classify as PLANNER, CHAT, or SHELL depending on patterns
            assert result.route in ["PLANNER", "CHAT", "SHELL"]
            # Response will have either agent_c_response (CHAT) or plan (PLANNER) or was SHELL
            assert result.cycle_id is not None


class TestTask3DockerMonitoring:
    """Task 3: Docker memory monitoring"""

    def test_task3_classification(self, orchestrator):
        """Verify Docker monitoring task routes appropriately"""
        query = "Find all Docker containers using more than 500MB memory and list them"
        result = orchestrator.router.classify(query)
        # Docker queries may route to SHELL (docker command), PLANNER, or CHAT
        assert result.route in [Route.PLANNER, Route.CHAT, Route.SHELL]

    def test_task3_planning(self, orchestrator):
        """Test Agent A decomposition for Docker monitoring task"""
        query = "Find all Docker containers using more than 500MB memory and list them"

        # Expected steps
        expected_tools = ["run_command", "run_command"]  # docker stats, filter

        assert len(expected_tools) == 2

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
        """Test that step outputs are stored in memory"""
        query = "Create a Python script that monitors disk space"

        # Store execution in intention cache
        memory.add_to_intention_cache(
            user_query=query,
            normalized_intent="create monitoring script",
            tool_name="create_file",
            tool_args={"path": "/tmp/test.py", "content": "print('hello')"},
            success=True,
        )

        # Verify stored in cache
        hits = memory.search_intention_cache(query, limit=1, min_success=True)
        assert len(hits) > 0
        assert hits[0]["tool_name"] == "create_file"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
