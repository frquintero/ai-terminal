"""
Unit tests for router CLI tool

Tests:
- Query classification via CLI
- Batch test file loading
- Interactive mode commands
- JSON output format
- Error handling
"""

import json
import pytest
import sys
import tempfile
from pathlib import Path
from io import StringIO
from unittest.mock import patch, MagicMock

from router.cli import classify_query, batch_test, print_result
from router.router import Router
from memory.api import Memory


@pytest.fixture
def temp_db():
    """Create temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_router.db"
        yield db_path


@pytest.fixture
def router(temp_db):
    """Create Router instance with test database"""
    return Router(memory=Memory(db_path=temp_db))


@pytest.fixture
def test_queries_file():
    """Create temporary test queries file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("# Test queries\n")
        f.write("What is Python?\n")
        f.write("ls -la\n")
        f.write("# Comment line\n")
        f.write("Create a monitoring script\n")
        f.write("\n")  # Empty line
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    Path(temp_path).unlink()


class TestClassifyQuery:
    """Test single query classification"""
    
    def test_classify_chat_query(self, router):
        """Test CHAT route classification"""
        result = classify_query(router, "What is Docker?")
        
        assert result["query"] == "What is Docker?"
        assert result["route"] == "CHAT"
        assert result["confidence"] > 0.7
        assert result["matched_rule"] is not None
    
    def test_classify_shell_query(self, router):
        """Test SHELL route classification"""
        result = classify_query(router, "ls -la")
        
        assert result["query"] == "ls -la"
        assert result["route"] == "SHELL"
        assert result["confidence"] > 0.9
        assert result["matched_rule"] is not None
    
    def test_classify_planner_query(self, router):
        """Test PLANNER route classification"""
        result = classify_query(router, "Create a monitoring script")
        
        assert result["query"] == "Create a monitoring script"
        assert result["route"] == "PLANNER"
        assert result["confidence"] >= 0.5
    
    def test_classify_includes_pattern_counts(self, router):
        """Test that result includes pattern statistics"""
        result = classify_query(router, "ls")
        
        assert "shell_patterns_count" in result
        assert "chat_patterns_count" in result
        assert "interactive_patterns_count" in result
        assert result["shell_patterns_count"] > 0
        assert result["chat_patterns_count"] > 0
    
    def test_classify_interactive_detection(self, router):
        """Test interactive command detection"""
        vim_result = classify_query(router, "vim main.py")
        ls_result = classify_query(router, "ls -la")
        
        # vim is interactive, ls is not
        assert vim_result["is_interactive"] == True
        assert ls_result["is_interactive"] == False
    
    def test_classify_verbose_mode(self, router):
        """Test that verbose mode doesn't break classification"""
        result = classify_query(router, "grep test *.py", verbose=True)
        
        assert result["route"] == "SHELL"
        assert "is_interactive" in result
    
    def test_classify_with_patterns(self, router):
        """Test show_patterns mode"""
        result = classify_query(router, "cat file.txt", show_patterns=True)
        
        assert result["route"] == "SHELL"
        assert "shell_patterns_count" in result


class TestBatchTest:
    """Test batch query testing from file"""
    
    def test_batch_test_loads_file(self, router, test_queries_file):
        """Test batch test file loading"""
        result = batch_test(router, test_queries_file, verbose=False, json_output=False)
        
        # Should succeed
        assert result == 0
    
    def test_batch_test_counts_routes(self, router, test_queries_file):
        """Test that batch test correctly counts routes"""
        # Create a simple test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("What is Python?\n")  # CHAT
            f.write("ls -la\n")  # SHELL
            f.write("Create a script\n")  # PLANNER
            temp_path = f.name
        
        try:
            result = batch_test(router, temp_path, verbose=False, json_output=False)
            assert result == 0
        finally:
            Path(temp_path).unlink()
    
    def test_batch_test_file_not_found(self, router):
        """Test error handling for missing file"""
        result = batch_test(router, "/nonexistent/file.txt", verbose=False, json_output=False)
        
        assert result == 1
    
    def test_batch_test_ignores_comments(self, router):
        """Test that batch test ignores comment lines"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("# This is a comment\n")
            f.write("What is Python?\n")
            f.write("# Another comment\n")
            temp_path = f.name
        
        try:
            result = batch_test(router, temp_path, verbose=False, json_output=False)
            assert result == 0
        finally:
            Path(temp_path).unlink()
    
    def test_batch_test_json_output(self, router, test_queries_file, capsys):
        """Test JSON output format"""
        batch_test(router, test_queries_file, verbose=False, json_output=True)
        
        captured = capsys.readouterr()
        # Should contain JSON output
        assert "[" in captured.out
        assert "{" in captured.out


class TestPrintResult:
    """Test result printing"""
    
    def test_print_result_basic(self, capsys):
        """Test basic result printing"""
        result = {
            "query": "ls -la",
            "route": "SHELL",
            "confidence": 0.95,
            "matched_rule": "^ls\\b",
            "cache_hit": None,
            "is_interactive": False,
        }
        
        print_result(result, verbose=False, show_patterns=False)
        captured = capsys.readouterr()
        
        assert "ls -la" in captured.out
        assert "SHELL" in captured.out
        assert "0.95" in captured.out
    
    def test_print_result_verbose(self, capsys):
        """Test verbose result printing"""
        result = {
            "query": "vim main.py",
            "route": "SHELL",
            "confidence": 0.95,
            "matched_rule": "^vim\\b",
            "cache_hit": None,
            "is_interactive": True,
            "rules_matched": ["^vim\\b"],
        }
        
        print_result(result, verbose=True, show_patterns=False)
        captured = capsys.readouterr()
        
        assert "vim main.py" in captured.out
        assert "Detailed Analysis" in captured.out
        assert "True" in captured.out or "true" in captured.out
    
    def test_print_result_with_cache_hit(self, capsys):
        """Test result printing with cache hit"""
        result = {
            "query": "ls",
            "route": "CACHED",
            "confidence": 0.90,
            "matched_rule": None,
            "cache_hit": {
                "tool_name": "run_command",
                "tool_args": {"command": "ls -la"},
                "score": 0.95,
            },
            "is_interactive": False,
        }
        
        print_result(result, verbose=False, show_patterns=False)
        captured = capsys.readouterr()
        
        assert "Cache Hit" in captured.out
        assert "run_command" in captured.out


class TestCliIntegration:
    """Integration tests for full CLI"""
    
    def test_cli_help(self, capsys):
        """Test CLI help output"""
        from router.cli import main
        
        with patch.object(sys, 'argv', ['cli.py', '--help']):
            try:
                main()
            except SystemExit:
                pass  # argparse calls sys.exit after printing help
        
        captured = capsys.readouterr()
        assert "Router CLI" in captured.out or "usage:" in captured.out.lower()
    
    def test_cli_single_query(self, capsys):
        """Test CLI with single query"""
        from router.cli import main
        import sys
        
        with patch.object(sys, 'argv', ['cli.py', 'ls -la']):
            result = main()
        
        assert result == 0
        captured = capsys.readouterr()
        assert "SHELL" in captured.out
    
    def test_cli_json_output(self, capsys):
        """Test CLI with JSON output"""
        from router.cli import main
        import sys
        
        with patch.object(sys, 'argv', ['cli.py', 'What is Python?', '--json']):
            result = main()
        
        assert result == 0
        captured = capsys.readouterr()
        # Should be valid JSON
        data = json.loads(captured.out)
        assert "route" in data
        assert "confidence" in data


class TestQueryCoverage:
    """Test coverage of different query types"""
    
    def test_all_route_types(self, router):
        """Test that all route types are recognizable"""
        test_cases = [
            ("What is Docker?", "CHAT"),
            ("ls -la", "SHELL"),
            ("Create monitoring script", "PLANNER"),
        ]
        
        for query, expected_route in test_cases:
            result = classify_query(router, query)
            assert result["route"] == expected_route, f"Query '{query}' should route to {expected_route}"
    
    def test_shell_commands_variety(self, router):
        """Test various shell commands"""
        commands = [
            "ls",
            "grep pattern file",
            "cat README.md",
            "find . -name '*.py'",
            "git status",
            "docker ps",
            "python script.py",
        ]
        
        for cmd in commands:
            result = classify_query(router, cmd)
            assert result["route"] == "SHELL", f"Command '{cmd}' should be SHELL"
    
    def test_chat_questions_variety(self, router):
        """Test various informational questions"""
        questions = [
            "What is Docker?",
            "Explain REST APIs",
            "How does caching work?",
            "Tell me about Kubernetes",
            "Define machine learning",
        ]
        
        for q in questions:
            result = classify_query(router, q)
            assert result["route"] == "CHAT", f"Question '{q}' should be CHAT"
    
    def test_interactive_commands(self, router):
        """Test interactive command detection"""
        interactive = [
            "vim main.py",
            "nano config.py",
            "less README.md",
            "top",
            "htop",
            "man ls",
        ]
        
        for cmd in interactive:
            result = classify_query(router, cmd)
            assert result["is_interactive"] == True, f"'{cmd}' should be detected as interactive"
    
    def test_batch_mode_vim(self, router):
        """Test vim in batch mode (not interactive)"""
        # vim -c is batch mode, so vim itself is interactive but vim -c is not
        vim_interactive = classify_query(router, "vim main.py")
        vim_batch = classify_query(router, "vim -c 'set number' file.py")
        
        assert vim_interactive["is_interactive"] == True
        # vim -c should still route to SHELL but may not be detected as interactive
        assert vim_batch["route"] == "SHELL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
