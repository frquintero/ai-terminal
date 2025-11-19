"""
SystemContextBuilder: Dynamic system context generation for agent system prompts.

Composes environmental context from:
1. Session system info (cached at startup)
2. Tool registry (dynamic)
3. Database schema (static)
4. Current timestamp
5. Shell state (if available)

Goal: Provide agents with complete environmental awareness without prompt bloat.
Hard cap: < 1000 tokens per context generation.
"""

import os
import platform
import shutil
from datetime import datetime
from typing import Dict, Optional, List, Any
from pathlib import Path

from memory.api import Memory


class SystemContextBuilder:
    """
    Builds role-specific system context for LLM prompts.
    
    Context includes:
    - Cached system info (OS, interpreters, sandbox config)
    - Tool registry (available tools)
    - Database schema summary (for search_db)
    - Current timestamp
    - Shell current directory (dynamic)
    """
    
    def __init__(self, memory: Memory):
        """
        Initialize builder with memory access.
        
        Args:
            memory: Memory API instance for session lookups
        """
        self.memory = memory
    
    def detect_system_state(self) -> Dict[str, Any]:
        """
        Detect current system state (interpreters, OS, sandbox).
        Should be called ONCE per session at orchestrator startup.
        
        Returns:
            Dict with system state snapshot
        """
        # Detect interpreters
        interpreters = {}
        for interpreter in ['python3', 'python', 'node', 'ruby', 'bash', 'perl']:
            path = shutil.which(interpreter)
            if path:
                interpreters[interpreter] = path
        
        # Get Python version if available
        python_version = None
        if 'python3' in interpreters or 'python' in interpreters:
            try:
                import sys
                python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            except:
                python_version = "unknown"
        
        # Get Node version if available
        node_version = None
        if 'node' in interpreters:
            try:
                import subprocess
                result = subprocess.run(
                    ['node', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if result.returncode == 0:
                    node_version = result.stdout.strip()
            except:
                node_version = "unknown"
        
        # Sandbox configuration
        sandbox_enabled = os.getenv('SANDBOX_ENABLE', 'false').lower() == 'true'
        sandbox_python = os.getenv('SANDBOX_PYTHON')
        sandbox_isolation = os.getenv('SANDBOX_ENABLE_ISOLATION', 'false').lower() == 'true'
        
        return {
            "os_name": platform.system(),
            "os_version": platform.version(),
            "working_directory": os.getcwd(),
            "interpreters": interpreters,
            "python_version": python_version,
            "node_version": node_version,
            "sandbox_enabled": sandbox_enabled,
            "sandbox_python": sandbox_python,
            "sandbox_isolation_enabled": sandbox_isolation,
        }
    
    def build_for_role(
        self,
        role: str,
        session_id: str,
        tool_registry: Optional[Dict[str, Any]] = None,
        shell_cwd: Optional[str] = None
    ) -> str:
        """
        Generate role-specific system context.
        
        Args:
            role: Agent role ('A' or 'B')
            session_id: Current session ID
            tool_registry: Available tools (name -> schema)
            shell_cwd: Current shell working directory (can differ from OS cwd)
        
        Returns:
            Formatted system context string (< 1000 tokens)
        """
        # Retrieve cached session system info
        session = self.memory.get_session(session_id)
        if not session or not session.get('system_info'):
            raise ValueError(f"Session {session_id} not found or missing system_info")
        
        system_info = session['system_info']
        
        # Build context sections
        sections = []
        
        # 1. Basic environment (always included)
        sections.append(self._build_basic_env(system_info, shell_cwd))

        # 2. Architecture snapshot (role-aware guardrails)
        sections.append(self._build_architecture_section(role))
        
        # 3. Tools (role-specific)
        if role in ['A', 'B'] and tool_registry:
            sections.append(self._build_tools_section(role, tool_registry))

        # 4. Interpreters (Agent B only - tactical execution)
        if role == 'B':
            sections.append(self._build_interpreters_section(system_info))

        # 5. Capabilities summary (Agent A only - for answering "can I...?" questions)
        if role == 'A':
            sections.append(self._build_capabilities_section(system_info))
        
        return "\n\n".join(sections)
    
    def _build_basic_env(self, system_info: Dict, shell_cwd: Optional[str]) -> str:
        """Build basic environment section."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cwd = shell_cwd if shell_cwd else system_info.get('cwd', system_info.get('working_directory', 'unknown'))
        python_version = system_info.get('python_version')
        if python_version and python_version not in ("unknown", ""):
            python_line = f"- Python: Python {python_version}"
        elif python_version == "unknown":
            python_line = "- Python: detected but version unavailable"
        else:
            python_line = "- Python is not installed in this system"
        
        return f"""**Current Environment:**
- Date/Time: {timestamp}
- OS: {system_info.get('os_name', 'unknown')} {system_info.get('os_version', '')}
- Working Directory: {cwd}
{python_line}"""
    
    def _build_tools_section(self, role: str, tool_registry: Dict[str, Any]) -> str:
        """Build tools section (different for A vs B)."""
        tool_names = list(tool_registry.keys())
        
        if role == 'A':
            # Agent A: Just list tool names (for planning)
            tools_list = ", ".join(tool_names)
            return f"""**Available Tools ({len(tool_names)}):** {tools_list}

Each tool has a specific purpose - use the right tool for each step."""
        
        elif role == 'B':
            # Agent B: Include brief descriptions (for execution)
            tools_desc = []
            for name, tool_obj in tool_registry.items():
                # Get description directly from tool object
                desc = tool_obj.description[:60]  # Truncate
                tools_desc.append(f"- {name}: {desc}")
            
            return f"""**Available Tools ({len(tool_names)}):**
""" + "\n".join(tools_desc)
        
        return ""
    
    def _build_interpreters_section(self, system_info: Dict) -> str:
        """Build interpreters section (Agent B only)."""
        interpreters = system_info.get('interpreters', {})
        if not interpreters:
            return "**Interpreters:** None detected"
        
        interp_lines = []
        for name, path in interpreters.items():
            version = ""
            if name in ['python3', 'python'] and system_info.get('python_version'):
                version = f" (v{system_info['python_version']})"
            elif name == 'node' and system_info.get('node_version'):
                version = f" ({system_info['node_version']})"
            
            interp_lines.append(f"- {name}: {path}{version}")
        
        sandbox_note = ""
        if system_info.get('sandbox_enabled'):
            sandbox_note = f"\n- Sandbox: Enabled (isolation={'on' if system_info.get('sandbox_isolation_enabled') else 'off'})"
        
        return f"""**Interpreters:**
""" + "\n".join(interp_lines) + sandbox_note
    
    def _build_capabilities_section(self, system_info: Dict) -> str:
        """Build capabilities summary (Agent A only)."""
        interpreters = system_info.get('interpreters', {})
        
        python = "python3" in interpreters or "python" in interpreters
        node = "node" in interpreters
        ruby = "ruby" in interpreters
        
        caps = []
        if python:
            caps.append(f"Python {system_info.get('python_version', '')}")
        if node:
            caps.append(f"Node.js {system_info.get('node_version', '')}")
        if ruby:
            caps.append("Ruby")
        
        if not caps:
            caps.append("Bash shell")
        
        return f"""**System Capabilities:** {", ".join(caps)}"""

    def _build_architecture_section(self, role: str) -> str:
        """
        Describe how the dual-agent architecture is wired so each role knows its neighbors.
        """
        shared_lines = [
            "- The Orchestrator receives each query, owns Memory, and decides which role to invoke.",
            "- Agent B (command engineer) turns each Agent A step into concrete ToolExecutor commands.",
            "- ToolExecutor runs `run_command`/`run_interactive` in the sandbox and streams outputs back.",
            "- Memory (logs/orchestrator.db) records cycles, plans, Agent B calls, and parsed step outputs."
        ]

        if role == "A":
            role_intro = "- You are Agent A: focus on planning + narration, never emit commands, and expect Agent B to fulfill every tool call."
        elif role == "B":
            role_intro = "- You are Agent B: execute the intent using available tools. You can call multiple tools if needed."
        else:
            role_intro = "- You are an orchestration helper role."

        lines = "\n".join([role_intro] + shared_lines)
        return f"""**Architecture Snapshot:**
{lines}"""
    
    def estimate_tokens(self, context: str) -> int:
        """
        Rough token estimate (4 chars ≈ 1 token).
        
        Args:
            context: Generated context string
        
        Returns:
            Estimated token count
        """
        return len(context) // 4
