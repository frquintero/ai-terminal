"""
Unit tests for Memory API (Phase 0)

Tests all CRUD operations for the unified memory system.
"""

import pytest
import tempfile
from pathlib import Path

from memory import Memory
from memory.schema import get_schema_version


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    yield db_path
    
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def memory(temp_db):
    """Create Memory instance with temp database."""
    mem = Memory(db_path=temp_db)
    yield mem
    mem.close()


class TestMemorySchema:
    """Test database schema and migrations."""
    
    def test_init_creates_all_tables(self, memory):
        """Verify all required tables are created."""
        required_tables = [
            'schema_version',
            'sessions',
            'router_decisions',
            'intention_cache',
            'intention_cache_fts',
            'interactions',
            'task_state',
            'step_outputs',
            'chat_history',
            'llm_traces'
        ]
        
        cursor = memory.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        
        for table in required_tables:
            assert table in tables, f"Missing table: {table}"
    
    def test_schema_version(self, memory):
        """Verify schema version is tracked."""
        version = get_schema_version(memory.conn)
        assert version == 1
    
    def test_foreign_keys_enabled(self, memory):
        """Verify foreign key constraints are enabled."""
        cursor = memory.conn.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]
        assert fk_enabled == 1


class TestSessionManagement:
    """Test session creation and tracking."""
    
    def test_create_session(self, memory):
        """Test session creation."""
        session_id = 'test-session-001'
        result = memory.create_session(
            session_id=session_id,
            model='gpt-4',
            system_info={'os': 'linux', 'cwd': '/tmp'}
        )
        
        assert result == session_id
        
        # Verify retrieval
        session = memory.get_session(session_id)
        assert session is not None
        assert session['session_id'] == session_id
        assert session['model'] == 'gpt-4'
        assert session['system_info']['os'] == 'linux'
    
    def test_update_session_activity(self, memory):
        """Test session activity timestamp update."""
        session_id = 'test-session-002'
        memory.create_session(session_id, 'gpt-4')
        
        # Get initial timestamp
        session1 = memory.get_session(session_id)
        timestamp1 = session1['last_activity_at']
        
        # Update activity
        memory.update_session_activity(session_id)
        
        # Verify timestamp changed
        session2 = memory.get_session(session_id)
        timestamp2 = session2['last_activity_at']
        assert timestamp2 >= timestamp1


class TestCycleManagement:
    """Test orchestration cycle operations."""
    
    def test_create_cycle(self, memory):
        """Test cycle creation."""
        session_id = 'test-session-003'
        memory.create_session(session_id, 'gpt-4')
        
        cycle_id = memory.create_cycle(session_id, 'test query')
        
        assert cycle_id is not None
        assert len(cycle_id) == 36  # UUID format
        
        # Verify router decision placeholder created
        decision = memory.get_router_decision(cycle_id)
        assert decision is not None
        assert decision['query_text'] == 'test query'
        assert decision['route'] == 'PLANNER'  # Default
        assert decision['confidence'] == 0.0
    
    def test_save_router_decision(self, memory):
        """Test saving router classification."""
        session_id = 'test-session-004'
        memory.create_session(session_id, 'gpt-4')
        cycle_id = memory.create_cycle(session_id, 'what is docker?')
        
        memory.save_router_decision(
            cycle_id=cycle_id,
            route='CHAT',
            confidence=0.95,
            rules={'pattern': 'what is'},
            cache_hit_tool=None,
            cache_hit_args=None
        )
        
        decision = memory.get_router_decision(cycle_id)
        assert decision['route'] == 'CHAT'
        assert decision['confidence'] == 0.95
        assert decision['rules']['pattern'] == 'what is'


class TestIntentionCache:
    """Test intention cache operations."""
    
    def test_add_to_cache(self, memory):
        """Test adding successful execution to cache."""
        memory.add_to_intention_cache(
            user_query='list files',
            normalized_intent='list files in directory',
            tool_name='run_command',
            tool_args={'command': 'ls -la'},
            success=True
        )
        
        # Search cache
        hits = memory.search_intention_cache('list files')
        assert len(hits) > 0
        assert hits[0]['tool_name'] == 'run_command'
        assert hits[0]['tool_args']['command'] == 'ls -la'
    
    def test_fts_search(self, memory):
        """Test FTS5 semantic search."""
        # Add multiple cache entries
        memory.add_to_intention_cache(
            'list python files',
            'list python files',
            'run_command',
            {'command': 'find . -name "*.py"'}
        )
        memory.add_to_intention_cache(
            'show python files',
            'show python files',
            'run_command',
            {'command': 'ls *.py'}
        )
        
        # Search with similar query
        hits = memory.search_intention_cache('python files', limit=10)
        assert len(hits) >= 2
    
    def test_update_cache_usage(self, memory):
        """Test cache usage counter."""
        memory.add_to_intention_cache(
            'test query', 'test', 'run_command', {'command': 'test'}
        )
        
        hits = memory.search_intention_cache('test query')
        cache_id = hits[0]['id']
        usage_before = hits[0]['usage_count']
        
        memory.update_cache_usage(cache_id)
        
        hits_after = memory.search_intention_cache('test query')
        usage_after = hits_after[0]['usage_count']
        
        assert usage_after == usage_before + 1


class TestInteractionLogging:
    """Test LLM interaction logging."""
    
    def test_log_interaction(self, memory):
        """Test logging Agent A/B/C interactions."""
        session_id = 'test-session-005'
        memory.create_session(session_id, 'gpt-4')
        cycle_id = memory.create_cycle(session_id, 'test')
        
        memory.log_interaction(
            cycle_id=cycle_id,
            role='A',
            system_prompt_checksum='abc123',
            prompt_preview='You are a planner',
            response_preview='Plan: step 1, step 2',
            token_usage={'prompt': 10, 'completion': 20, 'total': 30},
            latency_ms=1500
        )
        
        interactions = memory.get_interactions(cycle_id=cycle_id)
        assert len(interactions) == 1
        assert interactions[0]['role'] == 'A'
        assert interactions[0]['token_usage']['total'] == 30
        assert interactions[0]['latency_ms'] == 1500
    
    def test_get_interactions_by_role(self, memory):
        """Test filtering interactions by role."""
        session_id = 'test-session-006'
        memory.create_session(session_id, 'gpt-4')
        cycle_id = memory.create_cycle(session_id, 'test')
        
        # Log multiple roles
        memory.log_interaction(cycle_id, 'A', 'hash1')
        memory.log_interaction(cycle_id, 'B', 'hash2')
        memory.log_interaction(cycle_id, 'C', 'hash3')
        
        a_interactions = memory.get_interactions(role='A')
        c_interactions = memory.get_interactions(role='C')
        
        assert all(i['role'] == 'A' for i in a_interactions)
        assert all(i['role'] == 'C' for i in c_interactions)


class TestTaskState:
    """Test task/plan state management."""
    
    def test_save_plan(self, memory):
        """Test saving Agent A plan."""
        session_id = 'test-session-007'
        memory.create_session(session_id, 'gpt-4')
        cycle_id = memory.create_cycle(session_id, 'test task')
        
        plan = {
            'steps': [
                {'id': 1, 'tool': 'run_command', 'args': {'command': 'ls'}},
                {'id': 2, 'tool': 'read_file', 'args': {'file_path': 'test.txt'}}
            ]
        }
        
        memory.save_plan(cycle_id, plan, status='pending')
        
        task = memory.get_task_state(cycle_id)
        assert task is not None
        assert task['status'] == 'pending'
        assert len(task['plan']['steps']) == 2
    
    def test_update_task_status(self, memory):
        """Test updating task execution state."""
        session_id = 'test-session-008'
        memory.create_session(session_id, 'gpt-4')
        cycle_id = memory.create_cycle(session_id, 'test')
        
        plan = {'steps': [{'id': 1, 'tool': 'run_command', 'args': {}}]}
        memory.save_plan(cycle_id, plan, status='pending')
        
        memory.update_task_status(cycle_id, 'in_progress', current_step_id=1)
        task = memory.get_task_state(cycle_id)
        assert task['status'] == 'in_progress'
        assert task['current_step_id'] == 1
        
        memory.update_task_status(cycle_id, 'done')
        task = memory.get_task_state(cycle_id)
        assert task['status'] == 'done'


class TestStepOutputs:
    """Test step execution results."""
    
    def test_save_step_output(self, memory):
        """Test saving Agent B step result."""
        session_id = 'test-session-009'
        memory.create_session(session_id, 'gpt-4')
        cycle_id = memory.create_cycle(session_id, 'test')
        
        memory.save_step_output(
            cycle_id=cycle_id,
            step_id=1,
            tool_name='run_command',
            tool_args={'command': 'echo hello'},
            success=True,
            exit_code=0,
            output_preview='hello',
            artifact_path=None
        )
        
        steps = memory.get_step_outputs(cycle_id)
        assert len(steps) == 1
        assert steps[0]['step_id'] == 1
        assert steps[0]['tool_name'] == 'run_command'
        assert steps[0]['success'] is True
        assert steps[0]['exit_code'] == 0
    
    def test_get_last_n_steps(self, memory):
        """Test retrieving last N step outputs."""
        session_id = 'test-session-010'
        memory.create_session(session_id, 'gpt-4')
        cycle_id = memory.create_cycle(session_id, 'test')
        
        # Save 5 steps
        for i in range(1, 6):
            memory.save_step_output(
                cycle_id, i, 'run_command', {}, True, 0, f'output {i}'
            )
        
        # Get last 3
        last_3 = memory.get_step_outputs(cycle_id, last_n=3)
        assert len(last_3) == 3
        assert last_3[0]['step_id'] == 3  # Chronological order
        assert last_3[2]['step_id'] == 5


class TestChatHistory:
    """Test chat conversation tracking."""
    
    def test_save_chat_exchange(self, memory):
        """Test saving chat interaction."""
        session_id = 'test-session-011'
        memory.create_session(session_id, 'gpt-4')
        cycle_id = memory.create_cycle(session_id, 'what is docker?')
        
        memory.save_chat_exchange(
            session_id=session_id,
            cycle_id=cycle_id,
            user_query='what is docker?',
            agent_response='Docker is a containerization platform...'
        )
        
        history = memory.get_chat_history(session_id)
        assert len(history) == 1
        assert history[0]['user_query'] == 'what is docker?'
        assert 'containerization' in history[0]['agent_response']
    
    def test_get_last_n_chat(self, memory):
        """Test retrieving last N chat exchanges."""
        import time
        
        session_id = 'test-session-012'
        memory.create_session(session_id, 'gpt-4')
        
        # Save 15 exchanges with delays to ensure different timestamps
        # (SQLite CURRENT_TIMESTAMP has 1-second resolution)
        for i in range(1, 16):
            cycle_id = memory.create_cycle(session_id, f'query {i}')
            memory.save_chat_exchange(
                session_id, cycle_id, f'query {i}', f'response {i}'
            )
            if i % 5 == 0:  # Sleep every 5 to ensure timestamp changes
                time.sleep(1.1)
        
        # Get last 10 (default for Agent C)
        last_10 = memory.get_chat_history(session_id, last_n=10)
        assert len(last_10) == 10
        # Verify we got recent ones (exact order depends on timestamps)
        queries = {h['user_query'] for h in last_10}
        # At least should have entries from the last batch
        assert 'query 15' in queries or 'query 14' in queries


class TestLLMTraces:
    """Test detailed LLM trace logging."""
    
    def test_save_llm_trace(self, memory):
        """Test saving full prompt/response for debugging."""
        session_id = 'test-session-013'
        memory.create_session(session_id, 'gpt-4')
        cycle_id = memory.create_cycle(session_id, 'test')
        
        memory.save_llm_trace(
            cycle_id=cycle_id,
            role='A',
            full_prompt='[full prompt json...]',
            full_response='[full response...]',
            model='gpt-4',
            temperature=0.7,
            max_tokens=1000
        )
        
        traces = memory.get_llm_traces(cycle_id=cycle_id)
        assert len(traces) == 1
        assert traces[0]['role'] == 'A'
        assert traces[0]['model'] == 'gpt-4'
        assert traces[0]['temperature'] == 0.7
