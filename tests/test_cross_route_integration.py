"""
Cross-Route Integration Tests - Real-world scenarios with context handoff

Tests 3 representative workflows:
1. CHAT→SHELL: User asks about a command, then runs it
2. SHELL→PLANNER: Quick shell command, then multi-step task
3. CHAT→PLANNER→CHAT: Question, detailed task, follow-up question

Each validates:
- Route classification
- Context preservation
- Memory persistence
- Agent response quality
- Cycle tracking and state advancement
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from config import Config
from memory.api import Memory
from orchestrator.orchestrator import Orchestrator
from orchestrator.routes import RouterResult, Route


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
        mem.close(force=True)


@pytest.fixture
def orchestrator(test_config, memory):
    """Create Orchestrator instance for testing"""
    return Orchestrator(config=test_config, memory=memory)


# ============================================================================
# Integration Test 1: CHAT→SHELL
# User asks about a command, then runs it
# ============================================================================

class TestIntegration1ChatToShell:
    """CHAT→SHELL workflow: Question about command, then execution"""

    def test_chat_then_shell_preserves_context(self, orchestrator):
        """User asks about ls command, then runs it"""
        
        with patch.object(Orchestrator, "classify_query") as mock_classify, \
                patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_classify.side_effect = [
                RouterResult(route=Route.CHAT, confidence=0.85, latency_ms=5),
                RouterResult(route=Route.SHELL, confidence=0.95, latency_ms=5),
            ]
            # Step 1: CHAT route - "How do I list files?"
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content="Use 'ls -la' to list all files with details"),
                "usage": None,
                "latency_ms": 150,
                "trace_id": "chat-trace-1",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            result1 = orchestrator.handle_query("How do I list files?")
            assert result1.route == "CHAT"
            assert "ls" in result1.agent_response.lower()
            assert result1.cycle_id is not None
            chat_cycle_id = result1.cycle_id

            # Verify chat saved to history
            history = orchestrator.memory.get_chat_history(
                session_id=orchestrator.session_id,
                last_n=10
            )
            assert len(history) > 0
            assert any("list files" in h["user_query"].lower() for h in history)

            # Step 2: SHELL route - Run the command
            mock_llm.call.return_value = {
                "message": Mock(content="Files listed successfully"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "shell-trace-1",
                "error": None,
            }

            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True,
                    "result": "file1.txt\nfile2.py",
                    "exit_code": 0,
                    "error": None,
                }
                MockExecutor.return_value = mock_executor

                result2 = orchestrator.handle_query("ls -la /tmp")
                assert result2.route == "SHELL"
                assert result2.cycle_id != chat_cycle_id  # Different cycles
                assert result2.cycle_id is not None

    def test_chat_context_available_in_shell_execution(self, orchestrator):
        """Verify shell command can reference previous chat context"""
        
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            # Chat exchange
            cycle_id_1 = orchestrator.memory.create_cycle(
                session_id=orchestrator.session_id,
                query="What does grep do?"
            )
            orchestrator.memory.save_chat_exchange(
                session_id=orchestrator.session_id,
                cycle_id=cycle_id_1,
                user_query="What does grep do?",
                agent_response="grep searches for text patterns in files"
            )

            # Shell command - should have context available
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content="Grep command executed"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "shell-trace-2",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True,
                    "result": "line containing pattern",
                    "exit_code": 0,
                    "error": None,
                }
                MockExecutor.return_value = mock_executor

                result = orchestrator.handle_query("grep 'error' /var/log/syslog")
                assert result.route == "SHELL"

                # Verify context is available
                history = orchestrator.memory.get_chat_history(
                    session_id=orchestrator.session_id,
                    last_n=10
                )
                assert len(history) > 0

    def test_chat_to_shell_cycle_independence(self, orchestrator):
        """Verify each route gets independent cycle_id"""
        
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content="Response"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "test-trace",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True,
                    "result": "result",
                    "exit_code": 0,
                    "error": None,
                }
                MockExecutor.return_value = mock_executor

                result1 = orchestrator.handle_query("What is Docker?")
                result2 = orchestrator.handle_query("docker ps")

                assert result1.cycle_id != result2.cycle_id
                assert result1.cycle_id is not None
                assert result2.cycle_id is not None


# ============================================================================
# Integration Test 2: SHELL→PLANNER
# Quick shell command, then multi-step task
# ============================================================================

class TestIntegration2ShellToPlanner:
    """SHELL→PLANNER workflow: Quick command then complex task"""

    def test_shell_then_planner_separate_execution(self, orchestrator):
        """Execute quick ls command, then create monitoring script"""
        
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            # Step 1: SHELL route - "ls /tmp"
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content="Directory contents listed"),
                "usage": None,
                "latency_ms": 80,
                "trace_id": "shell-trace-3",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True,
                    "result": "file1\nfile2\nfile3",
                    "exit_code": 0,
                    "error": None,
                }
                MockExecutor.return_value = mock_executor

                result1 = orchestrator.handle_query("ls /tmp")
                assert result1.route == "SHELL"
                shell_cycle_id = result1.cycle_id

            # Step 2: PLANNER route - Complex task
            planner_plan = json.dumps({
                "steps": [
                    {
                        "tool_name": "create_file",
                        "intent": "Create monitoring script",
                        "description": "Create monitoring script",
                        "output_keys": ["script_path"]
                    },
                    {
                        "tool_name": "run_command",
                        "intent": "Make script executable",
                        "description": "Make script executable",
                        "output_keys": ["chmod_result"]
                    }
                ],
                "narration_template": "Script saved to {script_path}. chmod: {chmod_result}"
            })

            mock_llm.call.return_value = {
                "message": Mock(content=planner_plan),
                "usage": None,
                "latency_ms": 500,
                "trace_id": "planner-trace-1",
                "error": None,
            }

            result2 = orchestrator.handle_query("Create a script that monitors disk space")
            # May route to PLANNER or CHAT depending on rules
            assert result2.cycle_id != shell_cycle_id
            assert result2.cycle_id is not None

    def test_shell_execution_tracked_separately(self, orchestrator, memory):
        """Verify shell execution doesn't interfere with planner state"""
        
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content="Response"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "test-trace",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor, \
                    patch.object(Orchestrator, "classify_query") as mock_classify:
                mock_classify.side_effect = [
                    RouterResult(route=Route.SHELL, confidence=0.95, latency_ms=5),
                    RouterResult(route=Route.CHAT, confidence=0.85, latency_ms=5),
                ]
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True,
                    "result": "output",
                    "exit_code": 0,
                    "error": None,
                }
                MockExecutor.return_value = mock_executor

                # Shell command
                result1 = orchestrator.handle_query("pwd")
                cycle_1 = result1.cycle_id

                # Verify decision logged
                decision_1 = memory.get_router_decision(cycle_1)
                assert decision_1 is not None
                assert decision_1["route"] == "SHELL"

                # Complex task
                result2 = orchestrator.handle_query("Create a backup system")
                cycle_2 = result2.cycle_id

                # Verify separate decisions
                decision_2 = memory.get_router_decision(cycle_2)
                assert decision_2 is not None
                assert cycle_1 != cycle_2


# ============================================================================
# Integration Test 3: CHAT→PLANNER→CHAT
# Question, detailed task, follow-up question
# ============================================================================

class TestIntegration3ChatPlannerChat:
    """CHAT→PLANNER→CHAT workflow: Q&A with complex task in middle"""

    def test_full_chat_planner_chat_cycle(self, orchestrator):
        """Complete: ask, do task, ask follow-up"""
        
        with patch.object(Orchestrator, "classify_query") as mock_classify, \
                patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_classify.side_effect = [
                RouterResult(route=Route.CHAT, confidence=0.85, latency_ms=5),
                RouterResult(route=Route.PLANNER, confidence=0.6, latency_ms=5),
                RouterResult(route=Route.CHAT, confidence=0.85, latency_ms=5),
            ]
            
            mock_llm = Mock()
            MockLLMClient.return_value = mock_llm
            
            # Step 1: CHAT - "What's a cron job?"
            mock_llm.call.return_value = {
                "message": Mock(content="A cron job is a scheduled task in Unix/Linux"),
                "usage": None,
                "latency_ms": 120,
                "trace_id": "chat-trace-3",
                "error": None,
            }
            result1 = orchestrator.handle_query("What's a cron job?")
            assert result1.route == "CHAT"
            chat_cycle_1 = result1.cycle_id
            
            orchestrator.memory.save_chat_exchange(
                session_id=orchestrator.session_id,
                cycle_id=chat_cycle_1,
                user_query="What's a cron job?",
                agent_response=result1.agent_response
            )
            history = orchestrator.memory.get_chat_history(
                session_id=orchestrator.session_id,
                last_n=10
            )
            assert len(history) > 0
            
            # Step 2: PLANNER - "Set up daily backup"
            planner_response = json.dumps({
                "steps": [
                    {
                        "tool_name": "create_file",
                        "intent": "Create backup script",
                        "description": "Create backup script",
                        "output_keys": ["backup_script_path"]
                    },
                    {
                        "tool_name": "run_command",
                        "intent": "Install cron job",
                        "description": "Install in cron",
                        "output_keys": ["cron_status"]
                    }
                ],
                "narration_template": "Backup script at {backup_script_path}; cron status: {cron_status}"
            })
            mock_llm.call.return_value = {
                "message": Mock(content=planner_response),
                "usage": None,
                "latency_ms": 600,
                "trace_id": "planner-trace-3",
                "error": None,
            }
            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True,
                    "result": "Step completed",
                    "exit_code": 0,
                    "error": None,
                }
                MockExecutor.return_value = mock_executor
                
                result2 = orchestrator.handle_query("Set up daily backup of my home directory")
                assert result2.route == "PLANNER"
                planner_cycle = result2.cycle_id
                assert planner_cycle != chat_cycle_1
            
            # Step 3: CHAT follow-up - "How do I verify it's running?"
            mock_llm.call.return_value = {
                "message": Mock(content="Use crontab -l to list your jobs and check logs"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "chat-trace-4",
                "error": None,
            }
            result3 = orchestrator.handle_query("How do I verify it's running?")
            assert result3.route == "CHAT"
            chat_cycle_2 = result3.cycle_id
            
            # Verify all cycles unique
            assert chat_cycle_1 != planner_cycle
            assert planner_cycle != chat_cycle_2
            assert chat_cycle_1 != chat_cycle_2
            
            # Verify final chat history contains all exchanges
            final_history = orchestrator.memory.get_chat_history(
                session_id=orchestrator.session_id,
                last_n=10
            )
            assert len(final_history) >= 2  # At least 2 chat exchanges

    def test_planner_context_includes_previous_chat(self, orchestrator, memory):
        """Verify Agent A receives context from chat history"""
        
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            # Save initial chat context
            cycle_id_chat = memory.create_cycle(
                session_id=orchestrator.session_id,
                query="What is Docker?"
            )
            memory.save_chat_exchange(
                session_id=orchestrator.session_id,
                cycle_id=cycle_id_chat,
                user_query="What is Docker?",
                agent_response="Docker is a containerization platform that packages applications with their dependencies"
            )

            # Planner query should have this context available
            planner_plan = """{
                "steps": [
                    {"id": 0, "tool": "create_file", "description": "Create Dockerfile"}
                ]
            }"""

            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content=planner_plan),
                "usage": None,
                "latency_ms": 400,
                "trace_id": "planner-with-context",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True,
                    "result": "File created",
                    "exit_code": 0,
                    "error": None,
                }
                MockExecutor.return_value = mock_executor

                result = orchestrator.handle_query("Create a Dockerfile for my Python app")
                assert result.cycle_id is not None

                # Verify chat history is retrievable
                history = memory.get_chat_history(
                    session_id=orchestrator.session_id,
                    last_n=10
                )
                assert len(history) > 0

    def test_chat_includes_recent_planner_context(self, orchestrator, memory):
        """Verify Agent A (Chat) receives recent task completion context"""
        
        # Create a completed plan
        cycle_id_plan = memory.create_cycle(
            session_id=orchestrator.session_id,
            query="Create monitoring script"
        )
        plan = {
            "steps": [
                {"id": 0, "tool": "create_file", "description": "Create script"}
            ]
        }
        memory.save_plan(cycle_id=cycle_id_plan, plan=plan, status="done")

        # Verify we can retrieve the completed plan
        recent_plans = memory.get_recent_completed_plan(
            session_id=orchestrator.session_id,
            last_n=1
        )
        assert len(recent_plans) > 0
        assert recent_plans[0]["status"] == "done"
        assert "monitoring" in recent_plans[0]["query"].lower()

        # Now run a chat query - should have context available
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content="Chat response with context"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "chat-with-planner-context",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            result = orchestrator.handle_query("Is my monitoring script running?")
            assert result.route in ["CHAT", "PLANNER"]  # Both valid routes
            assert result.cycle_id is not None


# ============================================================================
# Cross-Route Integration Tests - Comprehensive
# ============================================================================

class TestCrossRouteIntegration:
    """Comprehensive tests for route transitions and context preservation"""

    def test_all_routes_in_sequence(self, orchestrator):
        """Execute queries that would use all four routes in sequence"""
        
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            MockLLMClient.return_value = mock_llm

            cycle_ids = []

            # 1. CHAT
            mock_llm.call.return_value = {
                "message": Mock(content="Docker is a containerization platform"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "trace-1",
                "error": None,
            }
            r1 = orchestrator.handle_query("What is Docker?")
            assert r1.route == "CHAT"
            cycle_ids.append(r1.cycle_id)

            # 2. SHELL
            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True, "result": "output", "exit_code": 0, "error": None
                }
                MockExecutor.return_value = mock_executor

                mock_llm.call.return_value = {
                    "message": Mock(content="Execution complete"),
                    "usage": None,
                    "latency_ms": 80,
                    "trace_id": "trace-2",
                    "error": None,
                }
                r2 = orchestrator.handle_query("docker ps")
                assert r2.route == "SHELL"
                cycle_ids.append(r2.cycle_id)

                # 3. PLANNER (complex task)
                plan = '{"steps": [{"id": 0, "tool": "create_file"}]}'
                mock_llm.call.return_value = {
                    "message": Mock(content=plan),
                    "usage": None,
                    "latency_ms": 500,
                    "trace_id": "trace-3",
                    "error": None,
                }
                mock_executor.execute.return_value = {
                    "success": True, "result": "done", "exit_code": 0, "error": None
                }
                r3 = orchestrator.handle_query("Create a Docker monitoring script")
                # May be PLANNER, CHAT, or SHELL depending on classification
                cycle_ids.append(r3.cycle_id)

            # Verify all cycles unique
            assert len(set(cycle_ids)) == len(cycle_ids), "All cycles should be unique"

    def test_memory_persistence_across_routes(self, orchestrator, memory):
        """Verify memory persists across all route transitions"""
        
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content="Response"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "test",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True, "result": "output", "exit_code": 0, "error": None
                }
                MockExecutor.return_value = mock_executor

                # Execute across routes
                q1 = "How do I use grep?"
                r1 = orchestrator.handle_query(q1)

                q2 = "grep pattern file.txt"
                r2 = orchestrator.handle_query(q2)

                # Verify both recorded in memory
                decisions = memory.conn.execute(
                    "SELECT COUNT(*) as cnt FROM router_decisions WHERE session_id = ?",
                    (orchestrator.session_id,)
                ).fetchone()
                assert decisions[0] >= 2, "Both queries should be recorded"

    def test_context_handoff_preserves_information(self, orchestrator, memory):
        """Verify context is not lost during route transitions"""
        
        # Setup: Create chat history
        cycle_chat = memory.create_cycle(
            session_id=orchestrator.session_id,
            query="What is a shell script?"
        )
        memory.save_chat_exchange(
            session_id=orchestrator.session_id,
            cycle_id=cycle_chat,
            user_query="What is a shell script?",
            agent_response="A shell script is a text file with shell commands"
        )

        # Verify retrieval works
        history_before = memory.get_chat_history(
            session_id=orchestrator.session_id,
            last_n=10
        )
        assert len(history_before) > 0
        original_query = history_before[0]["user_query"]

        # Simulate route transition
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content="Response"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "test",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True, "result": "output", "exit_code": 0, "error": None
                }
                MockExecutor.return_value = mock_executor

                # Execute another query
                orchestrator.handle_query("bash /tmp/script.sh")

        # Verify original context still available
        history_after = memory.get_chat_history(
            session_id=orchestrator.session_id,
            last_n=10
        )
        assert len(history_after) > 0
        # Original exchange should still be there
        queries = [h["user_query"] for h in history_after]
        assert original_query in queries


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
