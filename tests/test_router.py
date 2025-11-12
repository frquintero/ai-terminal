"""
Unit tests for Router module (Phase 1)

Tests rule engine, intention cache, and router classification.
"""

import pytest
import tempfile
from pathlib import Path

from router import Router, Route, RouterResult
from router.rules import RuleEngine
from router.cache import IntentionCache, CacheHit
from memory import Memory


@pytest.fixture
def temp_db():
    """Create temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    yield db_path
    
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def memory(temp_db):
    """Create Memory instance with temp database"""
    mem = Memory(db_path=temp_db)
    yield mem
    mem.close()


@pytest.fixture
def router(memory):
    """Create Router instance"""
    return Router(memory)


class TestRuleEngine:
    """Test rule-based classification"""
    
    def test_shell_command_detection(self):
        """Test shell command regex patterns"""
        engine = RuleEngine()
        
        # File operations
        route, pattern = engine.classify("ls -la")
        assert route == Route.SHELL
        assert pattern is not None
        
        route, pattern = engine.classify("cat /etc/passwd")
        assert route == Route.SHELL
        
        route, pattern = engine.classify("grep -r TODO .")
        assert route == Route.SHELL
        
        # Git commands
        route, pattern = engine.classify("git status")
        assert route == Route.SHELL
        
        route, pattern = engine.classify("git log --oneline")
        assert route == Route.SHELL
        
        # Docker commands
        route, pattern = engine.classify("docker ps")
        assert route == Route.SHELL
        
        route, pattern = engine.classify("docker-compose up -d")
        assert route == Route.SHELL
        
        # System info
        route, pattern = engine.classify("ps aux | grep python")
        assert route == Route.SHELL
        
        route, pattern = engine.classify("df -h")
        assert route == Route.SHELL
    
    def test_chat_query_detection(self):
        """Test chat query patterns"""
        engine = RuleEngine()
        
        # What is queries
        route, pattern = engine.classify("what is Docker?")
        assert route == Route.CHAT
        assert pattern is not None
        
        route, pattern = engine.classify("What are microservices?")
        assert route == Route.CHAT
        
        # Explain queries
        route, pattern = engine.classify("explain recursion")
        assert route == Route.CHAT
        
        route, pattern = engine.classify("can you explain how HTTPS works?")
        assert route == Route.CHAT
        
        # Define queries
        route, pattern = engine.classify("define REST API")
        assert route == Route.CHAT
    
    def test_no_match_returns_none(self):
        """Test unmatched queries return None (fallback to PLANNER)"""
        engine = RuleEngine()
        
        # Complex queries that need planning
        route, pattern = engine.classify("analyze the logs and fix any errors")
        assert route is None
        assert pattern is None
        
        route, pattern = engine.classify("refactor this module to use async/await")
        assert route is None
        
        route, pattern = engine.classify("create a script that processes CSV files")
        assert route is None
    
    def test_shell_priority_over_chat(self):
        """Test SHELL patterns have higher priority than CHAT"""
        engine = RuleEngine()
        
        # Shell command takes precedence even if it starts with chat-like words
        route, pattern = engine.classify("ls what files are here")
        assert route == Route.SHELL  # Matches ls pattern first
    
    def test_case_insensitive_matching(self):
        """Test patterns are case-insensitive"""
        engine = RuleEngine()
        
        route, _ = engine.classify("LS -la")
        assert route == Route.SHELL
        
        route, _ = engine.classify("GIT status")
        assert route == Route.SHELL
        
        route, _ = engine.classify("WHAT IS DOCKER?")
        assert route == Route.CHAT
    
    def test_get_stats(self):
        """Test rule engine statistics"""
        engine = RuleEngine()
        stats = engine.get_stats()
        
        assert "shell_patterns" in stats
        assert "chat_patterns" in stats
        assert stats["shell_patterns"] > 100  # We have 130+ patterns
        assert stats["chat_patterns"] > 5


class TestIntentionCache:
    """Test FTS5 cache lookup"""
    
    def test_cache_miss_on_empty_db(self, memory):
        """Test cache returns None when empty"""
        cache = IntentionCache(memory)
        
        hit = cache.lookup("list files")
        assert hit is None
    
    def test_cache_hit_after_add(self, memory):
        """Test cache returns hit after adding entry"""
        cache = IntentionCache(memory)
        
        # Add successful execution
        cache.add_execution(
            user_query="list files",
            normalized_intent="list files in directory",
            tool_name="run_command",
            tool_args={"command": "ls -la"},
            success=True
        )
        
        # Search should find it
        hit = cache.lookup("list files")
        assert hit is not None
        assert hit.tool_name == "run_command"
        assert hit.tool_args["command"] == "ls -la"
    
    def test_cache_semantic_search(self, memory):
        """Test FTS5 semantic matching"""
        cache = IntentionCache(memory)
        
        # Add entry with specific query
        cache.add_execution(
            "show python files",
            "list python files",
            "run_command",
            {"command": "ls *.py"},
            True
        )
        
        # Similar query should match via FTS5
        hit = cache.lookup("list python files")
        assert hit is not None
        assert hit.tool_name == "run_command"
    
    def test_cache_filters_failed_executions(self, memory):
        """Test cache only returns successful executions"""
        cache = IntentionCache(memory)
        
        # Add failed execution
        cache.add_execution(
            "test query",
            "test",
            "run_command",
            {"command": "false"},
            success=False
        )
        
        # Should not return failed execution
        hit = cache.lookup("test query")
        assert hit is None
    
    def test_update_usage_increments_counter(self, memory):
        """Test usage counter increments"""
        cache = IntentionCache(memory)
        
        # Add entry
        cache.add_execution(
            "test", "test", "run_command", {"command": "true"}, True
        )
        
        # Get initial hit
        hit = cache.lookup("test")
        assert hit is not None
        initial_usage = hit.usage_count
        cache_id = hit.cache_id
        
        # Update usage
        cache.update_usage(cache_id)
        
        # Usage should increment
        hit2 = cache.lookup("test")
        assert hit2.usage_count == initial_usage + 1
    
    def test_get_stats(self, memory):
        """Test cache statistics"""
        cache = IntentionCache(memory)
        stats = cache.get_stats()
        
        assert "min_score_threshold" in stats
        assert "min_usage_threshold" in stats
        assert "search_limit" in stats


class TestRouter:
    """Test integrated router classification"""
    
    def test_shell_route_priority(self, router):
        """Test SHELL route has highest priority"""
        result = router.classify("ls -la")
        
        assert result.route == Route.SHELL
        assert result.confidence == Router.SHELL_CONFIDENCE
        assert result.matched_rule is not None
        assert result.latency_ms >= 0
    
    def test_cached_route_after_execution(self, router, memory):
        """Test CACHED route for previously executed query"""
        # Add to cache
        router.intention_cache.add_execution(
            "show files",
            "list files",
            "run_command",
            {"command": "ls"},
            True
        )
        
        # Should route to CACHED
        result = router.classify("show files")
        
        assert result.route == Route.CACHED
        assert result.confidence == Router.CACHED_CONFIDENCE
        assert result.cache_hit is not None
        assert result.cache_hit.tool_name == "run_command"
    
    def test_chat_route_for_questions(self, router):
        """Test CHAT route for informational queries"""
        result = router.classify("what is Docker?")
        
        assert result.route == Route.CHAT
        assert result.confidence == Router.CHAT_CONFIDENCE
        assert result.matched_rule is not None
    
    def test_planner_fallback(self, router):
        """Test PLANNER fallback for complex queries"""
        result = router.classify("analyze logs and fix errors")
        
        assert result.route == Route.PLANNER
        assert result.confidence == Router.PLANNER_CONFIDENCE
        assert result.matched_rule is None
        assert result.cache_hit is None
    
    def test_shell_priority_over_cache(self, router, memory):
        """Test SHELL patterns take precedence over cache"""
        # Add cache entry for ls command
        router.intention_cache.add_execution(
            "ls -la",
            "list files",
            "run_command",
            {"command": "ls -la"},
            True
        )
        
        # Should still route to SHELL (higher priority)
        result = router.classify("ls -la")
        assert result.route == Route.SHELL
    
    def test_log_decision(self, router, memory):
        """Test logging router decision to Memory"""
        # Create session and cycle
        session_id = "test-router-session"
        memory.create_session(session_id, "gpt-4")
        cycle_id = memory.create_cycle(session_id, "ls -la")
        
        # Classify
        result = router.classify("ls -la")
        
        # Log decision
        router.log_decision(cycle_id, "ls -la", result)
        
        # Verify logged
        decision = memory.get_router_decision(cycle_id)
        assert decision is not None
        assert decision["route"] == "SHELL"
        assert decision["confidence"] == Router.SHELL_CONFIDENCE
        assert decision["rules"]["pattern"] is not None
    
    def test_log_cached_decision(self, router, memory):
        """Test logging CACHED route with cache hit metadata"""
        # Setup
        session_id = "test-cache-session"
        memory.create_session(session_id, "gpt-4")
        
        # Add cache entry
        router.intention_cache.add_execution(
            "test cmd", "test", "run_command", {"command": "echo test"}, True
        )
        
        # Create cycle and classify
        cycle_id = memory.create_cycle(session_id, "test cmd")
        result = router.classify("test cmd")
        
        # Log
        router.log_decision(cycle_id, "test cmd", result)
        
        # Verify cache metadata logged
        decision = memory.get_router_decision(cycle_id)
        assert decision["route"] == "CACHED"
        assert decision["cache_hit_tool"] == "run_command"
        assert decision["cache_hit_args"]["command"] == "echo test"
        assert decision["rules"]["cache_id"] is not None
    
    def test_get_stats(self, router):
        """Test router statistics"""
        stats = router.get_stats()
        
        assert "rule_engine" in stats
        assert "intention_cache" in stats
        assert "confidence_thresholds" in stats
        
        assert stats["confidence_thresholds"]["shell"] == Router.SHELL_CONFIDENCE
        assert stats["confidence_thresholds"]["chat"] == Router.CHAT_CONFIDENCE
    
    def test_latency_tracking(self, router):
        """Test router tracks classification latency"""
        result = router.classify("ls -la")
        
        # Latency should be measured
        assert result.latency_ms >= 0
        assert result.latency_ms < 100  # Should be fast (<100ms target)
    
    def test_result_to_dict(self, router):
        """Test RouterResult serialization"""
        result = router.classify("git status")
        
        data = result.to_dict()
        
        assert data["route"] == "SHELL"
        assert data["confidence"] == Router.SHELL_CONFIDENCE
        assert data["latency_ms"] >= 0
        assert "matched_rule" in data


class TestRouterEdgeCases:
    """Test edge cases and error handling"""
    
    def test_empty_query(self, router):
        """Test empty query falls back to PLANNER"""
        result = router.classify("")
        assert result.route == Route.PLANNER
    
    def test_whitespace_only_query(self, router):
        """Test whitespace-only query"""
        result = router.classify("   ")
        assert result.route == Route.PLANNER
    
    def test_very_long_query(self, router):
        """Test router handles long queries"""
        long_query = "ls " + (" -la" * 1000)
        result = router.classify(long_query)
        
        # Should still match shell pattern
        assert result.route == Route.SHELL
    
    def test_multiline_query(self, router):
        """Test multiline queries"""
        query = "ls -la\ncd /tmp\npwd"
        result = router.classify(query)
        
        # Should match first line's shell command
        assert result.route == Route.SHELL
    
    def test_unicode_in_query(self, router):
        """Test router handles unicode"""
        result = router.classify("ls файл.txt")
        assert result.route == Route.SHELL
        
        result = router.classify("что такое Docker?")  # Russian "what is"
        # Won't match English patterns, falls back to PLANNER
        assert result.route == Route.PLANNER
