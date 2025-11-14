"""
Phase 0 Acceptance Test

Verifies Phase 0 completion criteria:
- Single orchestrator.db file exists
- All 8 tables + FTS created
- Full CRUD API working
- LLMClient + ToolExecutor integration
- Zero imports from v1.3 legacy stores

Based on ORACLE_VERIFICATION_REPORT.md Phase 0 acceptance criteria.
"""

import os
import pytest
from pathlib import Path

from memory import Memory
from memory.schema import get_schema_version
from memory.migrations import verify_schema, get_migration_status
from llm_client import LLMClient
from tool_executor import ToolExecutor
from config import load_config


class TestPhase0Acceptance:
    """Phase 0 completion acceptance tests."""
    
    def test_single_orchestrator_db(self):
        """Verify single logs/orchestrator.db file exists."""
        db_path = Path("logs/orchestrator.db")
        
        # Should exist after any Memory() instantiation
        mem = Memory()
        mem.close(force=True)
        
        assert db_path.exists(), "orchestrator.db should exist"
        assert db_path.is_file(), "orchestrator.db should be a file"
        
        # Check it's a valid SQLite database
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT sqlite_version()")
        version = cursor.fetchone()
        conn.close()
        
        assert version is not None, "Should be valid SQLite database"
    
    def test_all_tables_created(self):
        """Verify all 8 required tables + FTS exist."""
        mem = Memory()
        
        required_tables = [
            'schema_version',
            'sessions',
            'router_decisions',
            'intention_cache',
            'intention_cache_fts',  # FTS5 virtual table
            'interactions',
            'task_state',
            'step_outputs',
            'chat_history',
            'llm_traces'
        ]
        
        cursor = mem.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        
        for table in required_tables:
            assert table in tables, f"Missing required table: {table}"
        
        # Note: FTS5 creates internal tables (_config, _data, _docsize, _idx)
        # So total count will be higher than required_tables
        assert len(tables) >= len(required_tables), \
            f"Expected at least {len(required_tables)} tables, got {len(tables)}"
        
        mem.close(force=True)
    
    def test_full_crud_api(self):
        """Test Memory API CRUD operations work end-to-end."""
        mem = Memory()
        
        # Create session (use unique ID to avoid conflicts)
        import uuid
        session_id = f'acceptance-test-{uuid.uuid4().hex[:8]}'
        mem.create_session(session_id, 'gpt-4', {'os': 'linux'})
        
        # Create cycle
        cycle_id = mem.create_cycle(session_id, 'test query')
        assert cycle_id is not None
        
        # Router decision
        mem.save_router_decision(cycle_id, 'PLANNER', confidence=0.9)
        decision = mem.get_router_decision(cycle_id)
        assert decision['route'] == 'PLANNER'
        
        # Intention cache
        mem.add_to_intention_cache(
            'test', 'test intent', 'run_command', {'command': 'test'}
        )
        cache_hits = mem.search_intention_cache('test')
        assert len(cache_hits) > 0
        
        # Interaction logging
        mem.log_interaction(
            cycle_id, 'A', 'checksum', 'prompt', 'response',
            {'total': 100}, 1000
        )
        interactions = mem.get_interactions(cycle_id=cycle_id)
        assert len(interactions) == 1
        
        # Task state
        plan = {'steps': [{'id': 1, 'tool': 'run_command', 'args': {}}]}
        mem.save_plan(cycle_id, plan, 'pending')
        task = mem.get_task_state(cycle_id)
        assert task['status'] == 'pending'
        
        # Step outputs
        mem.save_step_output(
            cycle_id, 1, 'run_command', {}, True, 0, 'output'
        )
        steps = mem.get_step_outputs(cycle_id)
        assert len(steps) == 1
        
        # Chat history
        mem.save_chat_exchange(session_id, cycle_id, 'query', 'response')
        history = mem.get_chat_history(session_id)
        assert len(history) == 1
        
        # LLM traces
        mem.save_llm_trace(cycle_id, 'A', 'prompt', 'response', 'gpt-4')
        traces = mem.get_llm_traces(cycle_id=cycle_id)
        assert len(traces) == 1
        
        mem.close(force=True)
        
        print("✓ All CRUD operations working")
    
    def test_llm_client_integration(self):
        """Test LLMClient logs to orchestrator.db."""
        import uuid
        config = load_config()
        mem = Memory()
        
        session_id = f'llm-test-{uuid.uuid4().hex[:8]}'
        mem.create_session(session_id, config.model)
        cycle_id = mem.create_cycle(session_id, 'test')
        
        # Create client and make call
        client = LLMClient(config, role='C', memory=mem)
        messages = [
            {'role': 'system', 'content': 'Test'},
            {'role': 'user', 'content': 'Say hi in one word'}
        ]
        
        result = client.call(messages, cycle_id=cycle_id)
        
        # Verify logging
        interactions = mem.get_interactions(cycle_id=cycle_id)
        assert len(interactions) > 0, "LLMClient should log to interactions"
        assert interactions[0]['role'] == 'C'
        
        mem.close(force=True)
        
        print("✓ LLMClient integration working")
    
    def test_tool_executor_integration(self):
        """Test ToolExecutor logs to orchestrator.db."""
        import uuid
        mem = Memory()
        
        session_id = f'tool-test-{uuid.uuid4().hex[:8]}'
        mem.create_session(session_id, 'gpt-4')
        cycle_id = mem.create_cycle(session_id, 'test')
        
        # Execute tool
        executor = ToolExecutor(memory=mem)
        result = executor.execute(
            'run_command',
            {'command': 'echo acceptance'},
            cycle_id=cycle_id,
            step_id=1
        )
        
        # Verify logging
        steps = mem.get_step_outputs(cycle_id)
        assert len(steps) > 0, "ToolExecutor should log to step_outputs"
        assert steps[0]['tool_name'] == 'run_command'
        
        mem.close(force=True)
        
        print("✓ ToolExecutor integration working")
    
    def test_no_legacy_imports(self):
        """Verify memory module has zero imports from v1.3 legacy stores."""
        import memory
        import memory.api
        import memory.schema
        import memory.migrations
        
        legacy_modules = [
            'db_logger',
            'filesystem_context',
            'history_store',
            'event_memory'
        ]
        
        for module in [memory, memory.api, memory.schema, memory.migrations]:
            module_globals = dir(module)
            for legacy in legacy_modules:
                assert legacy not in module_globals, \
                    f"Memory module should not import legacy {legacy}"
        
        print("✓ No legacy v1.3 imports in memory/")
    
    def test_schema_verification(self):
        """Verify schema is valid and up-to-date."""
        mem = Memory()
        
        # Schema version should be current (v2)
        version = get_schema_version(mem.conn)
        assert version == 2, f"Expected schema version 2, got {version}"
        
        # Schema should pass verification
        is_valid = verify_schema(mem.conn)
        assert is_valid, "Schema verification should pass"
        
        # Migration status should be up-to-date
        status = get_migration_status(mem.conn)
        assert status['up_to_date'], "Schema should be up-to-date"
        assert status['pending_migrations'] == 0, "No pending migrations"
        
        mem.close(force=True)
        
        print("✓ Schema verification passed")
    
    def test_foreign_key_integrity(self):
        """Verify foreign key constraints are enforced."""
        mem = Memory()
        
        # Should fail: cycle_id references non-existent session
        with pytest.raises(Exception):
            mem.conn.execute(
                """
                INSERT INTO router_decisions (session_id, cycle_id, query_text, route)
                VALUES ('nonexistent-session', 'test-cycle', 'test', 'CHAT')
                """
            )
            mem.conn.commit()
        
        mem.conn.rollback()
        mem.close(force=True)
        
        print("✓ Foreign key constraints enforced")
    
    def test_concurrent_cycles(self):
        """Test multiple concurrent cycles can coexist."""
        import uuid
        mem = Memory()
        
        session_id = f'concurrent-test-{uuid.uuid4().hex[:8]}'
        mem.create_session(session_id, 'gpt-4')
        
        # Create 3 concurrent cycles
        cycles = []
        for i in range(3):
            cycle_id = mem.create_cycle(session_id, f'query {i}')
            mem.save_router_decision(cycle_id, 'PLANNER', confidence=0.8)
            cycles.append(cycle_id)
        
        # Verify all exist independently
        for cycle_id in cycles:
            decision = mem.get_router_decision(cycle_id)
            assert decision is not None
            assert decision['cycle_id'] == cycle_id
        
        mem.close(force=True)
        
        print("✓ Concurrent cycles working")


def test_phase0_complete():
    """
    Meta-test: Run all acceptance criteria and report.
    
    This test runs all Phase 0 acceptance checks and provides
    a final summary for handoff to Phase 1.
    """
    print("\n" + "="*60)
    print("PHASE 0 ACCEPTANCE TEST")
    print("="*60)
    
    acceptance = TestPhase0Acceptance()
    
    tests = [
        ("Single orchestrator.db file", acceptance.test_single_orchestrator_db),
        ("All tables created", acceptance.test_all_tables_created),
        ("Full CRUD API", acceptance.test_full_crud_api),
        ("LLMClient integration", acceptance.test_llm_client_integration),
        ("ToolExecutor integration", acceptance.test_tool_executor_integration),
        ("No legacy imports", acceptance.test_no_legacy_imports),
        ("Schema verification", acceptance.test_schema_verification),
        ("Foreign key integrity", acceptance.test_foreign_key_integrity),
        ("Concurrent cycles", acceptance.test_concurrent_cycles),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            print(f"\nTesting: {name}...")
            test_fn()
            passed += 1
            print(f"  ✓ PASS")
        except Exception as e:
            failed += 1
            print(f"  ✗ FAIL: {e}")
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed}/{len(tests)} tests passed")
    
    if failed == 0:
        print("\n✅ PHASE 0 COMPLETE - Ready for Phase 1")
        print("\nDeliverables:")
        print("  - memory/ module (schema, api, migrations)")
        print("  - llm_client.py (LLM wrapper)")
        print("  - tool_executor.py (tool execution)")
        print("  - Single logs/orchestrator.db")
        print("  - 19 unit tests + acceptance test")
    else:
        print(f"\n❌ PHASE 0 INCOMPLETE - {failed} failures")
    
    print("="*60 + "\n")
    
    assert failed == 0, f"{failed} acceptance tests failed"
