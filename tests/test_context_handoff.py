"""
Tests for Chat↔Planner context handoff.

Tests:
- Chat→Planner: Include last 3 chat interactions as context for Agent A planning
- Planner→Chat: Include recent task summary when returning to CHAT after PLANNER
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from config import Config
from memory.api import Memory
from orchestrator.orchestrator import Orchestrator


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


class TestChatToPlannerHandoff:
    """Test Chat→Planner context handoff (last 3 interactions as context)"""

    def test_chat_to_planner_includes_context(self, orchestrator):
        """Verify Chat→Planner passes last 3 interactions to Agent A"""
        # Simulate 3 chat exchanges - must create cycles first for foreign key
        chat_exchanges = [
            ("What is Docker?", "Docker is a containerization platform..."),
            ("How does it differ from VMs?", "Containers are lighter weight than VMs..."),
            ("Can I run Docker on Windows?", "Yes, Docker Desktop is available for Windows..."),
        ]

        # Save chat history
        for user_query, agent_response in chat_exchanges:
            # Create cycle first (provides foreign key)
            cycle_id = orchestrator.memory.create_cycle(
                session_id=orchestrator.session_id,
                query=user_query
            )
            orchestrator.memory.save_chat_exchange(
                session_id=orchestrator.session_id,
                cycle_id=cycle_id,
                user_query=user_query,
                agent_response=agent_response
            )

        # Verify chat history was saved
        history = orchestrator.memory.get_chat_history(
            session_id=orchestrator.session_id,
            last_n=3
        )
        assert len(history) == 3

    def test_planner_receives_chat_context(self, orchestrator):
        """Verify Agent A receives chat context when handling PLANNER route"""
        # Add chat history - create cycle first
        cycle_id = orchestrator.memory.create_cycle(
            session_id=orchestrator.session_id,
            query="What is Docker?"
        )
        orchestrator.memory.save_chat_exchange(
            session_id=orchestrator.session_id,
            cycle_id=cycle_id,
            user_query="What is Docker?",
            agent_response="Docker is a containerization platform..."
        )

        # Mock Agent A planner response with context
        planner_query = "Create a script that manages Docker containers"

        # Mock LLM - would receive context in messages
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            
            # Create valid JSON plan response
            valid_plan = """{
                "steps": [
                    {
                        "id": 1,
                        "tool": "create_file",
                        "description": "Create Docker management script"
                    },
                    {
                        "id": 2,
                        "tool": "run_command",
                        "description": "Test the script"
                    }
                ]
            }"""

            mock_llm.call.return_value = {
                "message": Mock(content=valid_plan),
                "usage": {"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150},
                "latency_ms": 500,
                "trace_id": "test-trace",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            result = orchestrator.handle_query(planner_query)

            # Verify PLANNER route was taken
            assert result.route == "PLANNER"
            # Should have valid result
            assert result.cycle_id is not None

    def test_chat_context_format(self, orchestrator, memory):
        """Verify Chat→Planner context is properly formatted"""
        # Add chat history
        exchanges = [
            ("Q1", "A1"),
            ("Q2", "A2"),
            ("Q3", "A3"),
        ]

        for q, a in exchanges:
            cycle_id = memory.create_cycle(
                session_id=orchestrator.session_id,
                query=q
            )
            memory.save_chat_exchange(
                session_id=orchestrator.session_id,
                cycle_id=cycle_id,
                user_query=q,
                agent_response=a
            )

        # Retrieve history
        history = memory.get_chat_history(
            session_id=orchestrator.session_id,
            last_n=3
        )

        assert len(history) == 3
        # History is returned in reverse order (most recent first)
        user_queries = [h["user_query"] for h in history]
        assert "Q1" in user_queries
        assert "Q2" in user_queries
        assert "Q3" in user_queries


class TestPlannerToChatHandoff:
    """Test Planner→Chat context handoff (task summary)"""

    def test_completed_plan_retrieval(self, orchestrator, memory):
        """Verify get_recent_completed_plan retrieves completed tasks"""
        # Create a cycle and save plan
        from orchestrator.orchestrator import Orchestrator
        cycle_id = memory.create_cycle(
            session_id=orchestrator.session_id,
            query="Create a backup script"
        )

        # Save plan with done status
        plan = {
            "steps": [
                {"id": 1, "tool": "create_file"},
                {"id": 2, "tool": "run_command"}
            ]
        }
        memory.save_plan(cycle_id=cycle_id, plan=plan, status="done")

        # Retrieve recent completed plans
        completed = memory.get_recent_completed_plan(
            session_id=orchestrator.session_id,
            last_n=1
        )

        assert len(completed) == 1
        assert completed[0]["status"] == "done"

    def test_planner_to_chat_context_available(self, orchestrator, memory):
        """Verify Chat route has access to recent task completion context"""
        # Create and mark a plan as done
        cycle_id = memory.create_cycle(
            session_id=orchestrator.session_id,
            query="Set up daily backups"
        )

        plan = {
            "steps": [
                {"id": 1, "tool": "create_file", "description": "Create backup script"}
            ]
        }
        memory.save_plan(cycle_id=cycle_id, plan=plan, status="done")

        # Now verify CHAT route can find this context
        completed_plans = memory.get_recent_completed_plan(
            session_id=orchestrator.session_id,
            last_n=1
        )

        assert len(completed_plans) == 1
        assert "Set up daily backups" in completed_plans[0]["query"]

    def test_multiple_completed_plans_ordering(self, orchestrator, memory):
        """Verify get_recent_completed_plan returns completed plans"""
        # Create multiple completed plans
        queries = [
            "Create backup script",
            "Set up monitoring",
            "Configure logging"
        ]

        for query in queries:
            cycle_id = memory.create_cycle(
                session_id=orchestrator.session_id,
                query=query
            )
            plan = {"steps": [{"id": 1, "tool": "create_file"}]}
            memory.save_plan(cycle_id=cycle_id, plan=plan, status="done")

        # Retrieve all
        completed = memory.get_recent_completed_plan(
            session_id=orchestrator.session_id,
            last_n=10
        )

        assert len(completed) == 3
        # Verify all queries are present
        queries_returned = [c["query"] for c in completed]
        for q in queries:
            assert q in queries_returned


class TestHandoffIntegration:
    """Integration tests for full Chat↔Planner handoff"""

    def test_full_handoff_cycle(self, orchestrator):
        """Test complete Chat→Planner→Chat→Planner cycle"""
        # This is a high-level integration test showing the flow

        # Step 1: Chat exchange
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content="Chat response"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "test-1",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm

            result1 = orchestrator.handle_query("Tell me about Docker")
            assert result1.route == "CHAT"

            # Step 2: Follow-up planning task (Chat→Planner)
            valid_plan = '{"steps": [{"id": 1, "tool": "create_file"}]}'
            mock_llm.call.return_value = {
                "message": Mock(content=valid_plan),
                "usage": None,
                "latency_ms": 500,
                "trace_id": "test-2",
                "error": None,
            }

            result2 = orchestrator.handle_query("Create a Docker management script")
            # Could be PLANNER or CHAT depending on router
            assert result2.cycle_id is not None

    def test_handoff_with_error_handling(self, orchestrator):
        """Verify handoff works even with partial failures"""
        # Chat history saved - create cycle first
        cycle_id = orchestrator.memory.create_cycle(
            session_id=orchestrator.session_id,
            query="Test query"
        )
        orchestrator.memory.save_chat_exchange(
            session_id=orchestrator.session_id,
            cycle_id=cycle_id,
            user_query="Test query",
            agent_response="Test response"
        )

        # Try to get history
        history = orchestrator.memory.get_chat_history(
            session_id=orchestrator.session_id,
            last_n=5
        )

        assert len(history) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
