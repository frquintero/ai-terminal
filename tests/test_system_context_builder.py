"""
Unit tests for SystemContextBuilder
"""

import pytest
import os
from unittest.mock import Mock, patch
from orchestrator.system_context_builder import SystemContextBuilder


@pytest.fixture
def mock_memory():
    """Mock Memory API."""
    memory = Mock()
    memory.get_session.return_value = {
        "session_id": "test-123",
        "system_info": {
            "os_name": "Linux",
            "os_version": "5.15.0",
            "working_directory": "/home/user/ai-terminal",
            "cwd": "/home/user/ai-terminal",
            "interpreters": {
                "python3": "/usr/bin/python3",
                "node": "/usr/bin/node",
                "bash": "/bin/bash"
            },
            "python_version": "3.11.4",
            "node_version": "v18.16.0",
            "sandbox_enabled": False,
            "sandbox_python": None,
            "sandbox_isolation_enabled": False
        }
    }
    return memory


@pytest.fixture
def builder(mock_memory):
    """Create SystemContextBuilder with mock memory."""
    return SystemContextBuilder(mock_memory)


@pytest.fixture
def sample_tools():
    """Sample tool registry with tool objects."""
    tools = {}
    for name, desc in [
        ("run_command", "Execute shell command in persistent bash session"),
        ("read_file", "Read file contents from filesystem"),
        ("search_db", "Query institutional memory database")
    ]:
        tool = Mock()
        tool.name = name
        tool.description = desc
        tool.schema = {
            "description": desc,
            "function": {
                "name": name,
                "description": desc,
                "parameters": {"type": "object"}
            }
        }
        tools[name] = tool
    return tools


def test_detect_system_state(builder):
    """Test system state detection."""
    state = builder.detect_system_state()
    
    assert "os_name" in state
    assert "os_version" in state
    assert "working_directory" in state
    assert "interpreters" in state
    assert isinstance(state["interpreters"], dict)
    assert "sandbox_enabled" in state


def test_build_for_role_agent_a(builder, sample_tools):
    """Test context generation for Agent A (Planner)."""
    context = builder.build_for_role(
        role='A',
        session_id='test-123',
        tool_registry=sample_tools,
        shell_cwd='/home/user/project'
    )
    
    # Should include basic env
    assert "Current Environment" in context
    assert "Date/Time" in context
    assert "/home/user/project" in context
    
    # Should include tool names
    assert "Available Tools" in context
    assert "run_command" in context
    assert "read_file" in context
    assert "search_db" in context
    
    # Should include database schema
    assert "Database Schema" in context
    assert "chat_history" in context
    assert "step_outputs" in context
    
    # Should NOT include interpreters (tactical detail)
    assert "Interpreters:" not in context


def test_build_for_role_agent_b(builder, sample_tools):
    """Test context generation for Agent B (Executor)."""
    context = builder.build_for_role(
        role='B',
        session_id='test-123',
        tool_registry=sample_tools,
        shell_cwd='/home/user/project'
    )
    
    # Should include basic env
    assert "Current Environment" in context
    
    # Should include tool descriptions
    assert "Available Tools" in context
    assert "Execute shell command" in context  # Description snippet
    
    # Should include interpreters
    assert "Interpreters:" in context
    assert "/usr/bin/python3" in context
    assert "3.11.4" in context
    
    # Should NOT include database schema (strategic info)
    assert "Database Schema" not in context


def test_build_for_role_agent_c(builder, sample_tools):
    """Test context generation for Agent C (Chat/Narrator)."""
    context = builder.build_for_role(
        role='C',
        session_id='test-123',
        tool_registry=None,  # Agent C doesn't need tools
        shell_cwd='/home/user/project'
    )
    
    # Should include basic env
    assert "Current Environment" in context
    
    # Should include capabilities summary
    assert "System Capabilities" in context
    assert "Python 3.11.4" in context
    assert "Node.js v18.16.0" in context
    
    # Should NOT include tools or interpreters details
    assert "Available Tools" not in context
    assert "Interpreters:" not in context


def test_token_budget_compliance(builder, sample_tools):
    """Test that generated context stays under 1000 token budget."""
    for role in ['A', 'B', 'C']:
        context = builder.build_for_role(
            role=role,
            session_id='test-123',
            tool_registry=sample_tools if role in ['A', 'B'] else None,
            shell_cwd='/home/user/project'
        )
        
        estimated_tokens = builder.estimate_tokens(context)
        
        # Hard cap: < 1000 tokens (strict)
        assert estimated_tokens < 1000, \
            f"Agent {role} context exceeds 1000 tokens: {estimated_tokens}"
        
        # Agent C context can be very short, others should have reasonable content
        min_tokens = 30 if role == 'C' else 50
        assert estimated_tokens >= min_tokens, \
            f"Agent {role} context too short: {estimated_tokens} tokens"


def test_session_not_found(builder):
    """Test error handling when session not found."""
    builder.memory.get_session.return_value = None
    
    with pytest.raises(ValueError, match="Session .* not found"):
        builder.build_for_role(
            role='A',
            session_id='nonexistent',
            tool_registry={}
        )


def test_shell_cwd_overrides_system_cwd(builder, sample_tools):
    """Test that shell_cwd overrides system working_directory."""
    # Test with shell_cwd provided
    context_with_shell = builder.build_for_role(
        role='A',
        session_id='test-123',
        tool_registry=sample_tools,
        shell_cwd='/different/path'
    )
    assert "/different/path" in context_with_shell
    assert "/home/user/ai-terminal" not in context_with_shell
    
    # Test without shell_cwd (uses system cwd)
    context_without_shell = builder.build_for_role(
        role='A',
        session_id='test-123',
        tool_registry=sample_tools,
        shell_cwd=None
    )
    assert "/home/user/ai-terminal" in context_without_shell


def test_sandbox_configuration(builder, sample_tools):
    """Test sandbox configuration formatting."""
    # Enable sandbox in mock
    builder.memory.get_session.return_value['system_info']['sandbox_enabled'] = True
    builder.memory.get_session.return_value['system_info']['sandbox_isolation_enabled'] = True
    
    context = builder.build_for_role(
        role='B',
        session_id='test-123',
        tool_registry=sample_tools
    )
    
    assert "Sandbox: Enabled" in context
    assert "isolation=on" in context


def test_minimal_interpreters(builder, sample_tools):
    """Test context with minimal interpreter setup."""
    # Only bash available
    builder.memory.get_session.return_value['system_info']['interpreters'] = {
        "bash": "/bin/bash"
    }
    builder.memory.get_session.return_value['system_info']['python_version'] = None
    builder.memory.get_session.return_value['system_info']['node_version'] = None
    
    context = builder.build_for_role(
        role='B',
        session_id='test-123',
        tool_registry=sample_tools
    )
    
    assert "bash" in context
    assert "python" not in context.lower() or "Python" not in context


def test_db_schema_summary_content(builder, sample_tools):
    """Test that database schema summary is informative."""
    context = builder.build_for_role(
        role='A',
        session_id='test-123',
        tool_registry=sample_tools
    )
    
    # Check key tables mentioned
    assert "chat_history" in context
    assert "step_outputs" in context
    assert "task_state" in context
    
    # Check FTS5 mentioned
    assert "FTS5" in context
    
    # Check key columns mentioned
    assert "session_id" in context
    assert "cycle_id" in context
