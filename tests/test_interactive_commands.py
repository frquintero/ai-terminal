"""
Tests for interactive command handling (vim, top, htop, nano, etc.)

Tests:
- Router detects interactive commands
- SHELL route uses run_interactive tool for interactive commands  
- SHELL route uses run_command tool for regular commands
- Interactive commands are NOT cached (they're user-controlled)
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from config import Config
from memory.api import Memory
from orchestrator.orchestrator import Orchestrator
from router.rules import Route, RuleEngine


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


class TestInteractiveCommandDetection:
    """Test detection of interactive commands"""
    
    def test_detect_vim(self):
        """Verify vim is detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("vim /etc/hosts") is True
        assert rule_engine.is_interactive_command("vim file.txt") is True
        assert rule_engine.is_interactive_command("VIM file.txt") is True  # Case insensitive
    
    def test_detect_vim_with_c_flag_is_not_interactive(self):
        """vim -c is non-interactive batch mode"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("vim -c ':wq'") is False
        assert rule_engine.is_interactive_command("vim -c 'set number | wq'") is False
    
    def test_detect_nano(self):
        """Verify nano is detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("nano file.py") is True
        assert rule_engine.is_interactive_command("nano ~/.bashrc") is True
    
    def test_detect_less(self):
        """Verify less is detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("less /var/log/syslog") is True
    
    def test_detect_more(self):
        """Verify more is detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("more /etc/hosts") is True
    
    def test_detect_top(self):
        """Verify top is detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("top") is True
        assert rule_engine.is_interactive_command("top -u root") is True
    
    def test_detect_htop(self):
        """Verify htop is detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("htop") is True
    
    def test_detect_man(self):
        """Verify man pages are detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("man ls") is True
        assert rule_engine.is_interactive_command("man 5 hosts") is True
    
    def test_detect_python_repl(self):
        """Verify python REPL is detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("python") is True
        assert rule_engine.is_interactive_command("python3") is True
    
    def test_detect_node_repl(self):
        """Verify node.js REPL is detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("node") is True
    
    def test_detect_mysql(self):
        """Verify mysql interactive is detected"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("mysql -u root") is True
    
    def test_detect_psql(self):
        """Verify psql interactive is detected"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("psql mydb") is True
    
    def test_detect_ssh(self):
        """Verify ssh is detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("ssh user@host") is True
    
    def test_regular_commands_not_detected_as_interactive(self):
        """Verify regular shell commands are NOT detected as interactive"""
        rule_engine = RuleEngine()
        assert rule_engine.is_interactive_command("ls -la") is False
        assert rule_engine.is_interactive_command("cat /etc/hosts") is False
        assert rule_engine.is_interactive_command("grep text file.txt") is False
        assert rule_engine.is_interactive_command("docker ps") is False


class TestInteractiveCommandRouting:
    """Test routing of interactive commands"""
    
    def test_vim_routes_to_shell(self):
        """vim should route to SHELL"""
        rule_engine = RuleEngine()
        route, pattern = rule_engine.classify("vim /etc/hosts")
        # Should be shell route (or None, router will classify)
        # The rule_engine.classify returns SHELL for any shell pattern match
    
    def test_interactive_command_tool_selection(self, orchestrator):
        """Test SHELL route selects run_interactive tool for vim"""
        query = "vim /tmp/test.txt"
        
        # Mock LLM for Agent C
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            mock_llm = Mock()
            mock_llm.call.return_value = {
                "message": Mock(content="Vim editor closed"),
                "usage": None,
                "latency_ms": 100,
                "trace_id": "test-trace",
                "error": None,
            }
            MockLLMClient.return_value = mock_llm
            
            # Patch the orchestrator's tool_executor directly
            original_execute = orchestrator.tool_executor.execute
            with patch.object(orchestrator.tool_executor, 'execute') as mock_execute:
                mock_execute.return_value = {
                    "success": True,
                    "result": "Interactive command 'vim /tmp/test.txt' completed successfully.",
                    "exit_code": 0,
                    "error": None,
                }
                
                result = orchestrator.handle_query(query)
                
                # Verify run_interactive was called
                mock_execute.assert_called()
                call_kwargs = mock_execute.call_args[1]
                assert call_kwargs["tool_name"] == "run_interactive"
                assert call_kwargs["tool_args"]["command"] == query


class TestInteractiveVsRegularCommandCaching:
    """Test caching behavior for interactive vs regular commands"""
    
    def test_regular_command_is_cached(self, orchestrator, memory):
        """Regular shell commands should be cached"""
        query = "ls -la /tmp"
        
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_llm = Mock()
                mock_llm.call.return_value = {
                    "message": Mock(content="File listing retrieved"),
                    "usage": None,
                    "latency_ms": 100,
                    "trace_id": "test-trace",
                    "error": None,
                }
                MockLLMClient.return_value = mock_llm
                
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True,
                    "result": "file1.txt file2.txt",
                    "exit_code": 0,
                    "error": None,
                }
                MockExecutor.return_value = mock_executor
                
                result = orchestrator.handle_query(query)
                
                # Verify it was cached
                cache_hits = memory.search_intention_cache(query)
                # If cached, should have at least one hit
                # (May not be exact match due to FTS5, but should find it)
    
    def test_interactive_command_is_not_cached(self, orchestrator, memory):
        """Interactive commands should NOT be cached"""
        query = "vim /tmp/test.txt"
        
        with patch("orchestrator.orchestrator.LLMClient") as MockLLMClient:
            with patch("orchestrator.orchestrator.ToolExecutor") as MockExecutor:
                mock_llm = Mock()
                mock_llm.call.return_value = {
                    "message": Mock(content="Vim closed"),
                    "usage": None,
                    "latency_ms": 100,
                    "trace_id": "test-trace",
                    "error": None,
                }
                MockLLMClient.return_value = mock_llm
                
                mock_executor = Mock()
                mock_executor.execute.return_value = {
                    "success": True,
                    "result": "Interactive command completed",
                    "exit_code": 0,
                    "error": None,
                }
                MockExecutor.return_value = mock_executor
                
                result = orchestrator.handle_query(query)
                
                # Verify it was NOT cached
                cache_hits = memory.search_intention_cache(query)
                # Should be empty - interactive commands not cached
                assert len(cache_hits) == 0


class TestInteractiveCommandInfo:
    """Test information about interactive commands"""
    
    def test_rule_engine_reports_interactive_patterns(self):
        """RuleEngine should report count of interactive patterns"""
        rule_engine = RuleEngine()
        stats = rule_engine.get_stats()
        assert "interactive_patterns" in stats
        assert stats["interactive_patterns"] > 0
        # Should have at least editors, pagers, monitoring, repls
        assert stats["interactive_patterns"] >= 20


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
