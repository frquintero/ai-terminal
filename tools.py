"""
AI Terminal Tool Registry

Provides shell-first tools for the AI agent to interact with the system.
Philosophy: Prefer shell commands (run_command) over Python for most tasks.
Use Python sandbox only for visualization, ML, or explicit Python requirements.
"""

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import inspect
import ipaddress
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import textwrap
import time
from uuid import uuid4
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse, quote_plus

from shell_integration import ShellIntegration
from command_parser import parse_command

# v1.3 legacy imports (deprecated in v2.0, gated behind USE_EVENT_MEMORY flag)
# These modules are kept for historical reference only
# v2.0 uses unified Memory API (orchestrator.db) instead
_USE_EVENT_MEMORY = os.getenv('USE_EVENT_MEMORY', '0').lower() in ('1', 'true', 'yes')

if _USE_EVENT_MEMORY:
    # Only import if explicitly enabled
    from event_memory import summarize_event_log
    from history_store import get_history_store, HistoryStoreError
    from history_sql import get_history_sql_executor, HistorySQLExecutionError
    from filesystem_context import get_fs_context_store
else:
    # Stub implementations to prevent import errors
    def summarize_event_log(*args, **kwargs):
        return "Event memory disabled (set USE_EVENT_MEMORY=1 to enable legacy v1.3 tools)"
    
    def get_history_store():
        raise RuntimeError("History store disabled (v1.3 legacy - use Memory API)")
    
    def get_history_sql_executor():
        raise RuntimeError("History SQL disabled (v1.3 legacy - use Memory API)")
    
    def get_fs_context_store():
        raise RuntimeError("Filesystem context disabled (v1.3 legacy - use get_context tool)")
    
    class HistoryStoreError(Exception):
        pass
    
    class HistorySQLExecutionError(Exception):
        pass


# ============================================================================
# Working Directory Isolation
# ============================================================================

WORKING_DIR_PREFIX = "ai-terminal-wd"

def _get_working_dir_path() -> str:
    """Get absolute path to working directory (relative to this script's location)"""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(tools_dir, WORKING_DIR_PREFIX)


# ============================================================================
# Context Tracking
# ============================================================================

# Track recently written files for context awareness
_RECENT_WRITES: deque = deque(maxlen=100)
_RECENT_FILE_EVENTS: deque = deque(maxlen=200)

def _get_fs_store():
    try:
        return get_fs_context_store()
    except Exception:
        return None

_WORKING_DIR_PATH = Path(_get_working_dir_path())
HTTP_SESSION_ROOT = _WORKING_DIR_PATH / ".http_sessions"
HTTP_BODY_DIR = _WORKING_DIR_PATH / "http_bodies"
HTTP_TRACE_DIR = _WORKING_DIR_PATH / "http_traces"

for http_dir in (HTTP_SESSION_ROOT, HTTP_BODY_DIR, HTTP_TRACE_DIR):
    http_dir.mkdir(parents=True, exist_ok=True)

SESSION_CONFIG_FILENAME = "session.json"

TIME_KEYS = {
    "time_namelookup": "dns_lookup",
    "time_connect": "tcp_connect",
    "time_appconnect": "tls_handshake",
    "time_starttransfer": "ttfb",
    "time_total": "total",
    "time_pretransfer": "pretransfer",
    "time_redirect": "redirect",
    "time_posttransfer": "posttransfer",
}

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)((?:(?:[:|])[a-zA-Z0-9_.-]+)*)\s*\}\}")

DEFAULT_SESSION_CONFIG = {
    "default_headers": {},
    "auth_bearer": None,
    "api_key": {
        "header": None,
        "value": None
    },
    "variables": {}
}


# Curl exit code classification derived from Everything Curl
CURL_EXIT_CODE_MAP: Dict[int, Tuple[str, str]] = {
    1: ("protocol_error", "Unsupported protocol or invalid URL."),
    2: ("init_error", "Curl failed to initialize."),
    3: ("url_malformed", "Malformed URL."),
    5: ("proxy_error", "Proxy resolution failed."),
    6: ("dns_error", "Could not resolve host."),
    7: ("connect_error", "Failed to connect to host."),
    18: ("transfer_error", "Partial file transfer."),
    19: ("transfer_error", "Reference file already exists (resume conflict)."),
    22: ("http_error", "HTTP response >= 400 (use status for details)."),
    23: ("write_error", "Failed writing received data to disk/socket."),
    26: ("read_error", "Read error."),
    27: ("out_of_memory", "Out of memory."),
    28: ("timeout", "Operation timeout."),
    35: ("tls_error", "SSL/TLS handshake failed."),
    42: ("aborted", "Aborted by callback."),
    47: ("too_many_redirects", "Too many redirects."),
    48: ("dns_error", "Unknown option specified to DNS resolver."),
    49: ("dns_error", "Malformed DNS interface/option."),
    51: ("tls_cert_error", "Peer certificate could not be authenticated."),
    52: ("server_empty", "Server returned nothing."),
    53: ("ssl_engine_error", "SSL crypto engine not found."),
    54: ("ssl_engine_set_error", "Failed setting SSL crypto engine as default."),
    55: ("send_error", "Failed sending network data."),
    56: ("recv_error", "Failure when receiving network data."),
    58: ("no_local_cert", "Problem with local client certificate."),
    59: ("ssl_cipher_error", "Couldn't use specified SSL cipher."),
    60: ("tls_cert_error", "Peer certificate cannot be authenticated."),
    61: ("ssl_key_error", "Unrecognized client certificate format."),
    67: ("auth_error", "Authentication failure."),
    77: ("ssl_ca_error", "Problem with reading CA cert (path?)."),
    78: ("resource_not_found", "Resource not found (HTTP 404)."),
    79: ("file_error", "Remote file error."),
    80: ("ssl_shutdown_failed", "Failed to shut down SSL connection."),
    82: ("http2_error", "Stream error in HTTP/2 framing layer."),
    83: ("http2_error", "Inadequate transport security for HTTP/2."),
    84: ("http2_error", "HTTP/2 stream refused."),
    85: ("http2_error", "HTTP/2 internal error."),
    90: ("peer_error", "Peer failed verification."),
    91: ("bad_content_encoding", "Unrecognized transfer encoding."),
    92: ("http2_error", "HTTP/2 server refused settings."),
}


HTTP_STATUS_ERROR_MAP: Dict[int, Tuple[str, str]] = {
    401: ("auth_error", "Authentication required or failed."),
    403: ("auth_error", "Access forbidden."),
    404: ("resource_not_found", "Resource not found."),
    409: ("conflict_error", "Conflict when processing request."),
    422: ("validation_error", "Validation failed (HTTP 422)."),
    429: ("rate_limit", "Too many requests / rate limited."),
    500: ("server_error", "Internal server error."),
    502: ("server_error", "Bad gateway."),
    503: ("server_error", "Service unavailable."),
    504: ("server_error", "Gateway timeout."),
}


@dataclass(frozen=True)
class HttpProfile:
    name: str
    timeout_sec: int
    max_bytes: int
    follow_redirects: bool
    retries: int = 0
    retry_delay: int = 1
    retry_max_time: Optional[int] = None
    min_interval_sec: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "timeout_sec": self.timeout_sec,
            "max_bytes": self.max_bytes,
            "follow_redirects": self.follow_redirects,
            "retries": self.retries,
            "retry_delay": self.retry_delay,
            "retry_max_time": self.retry_max_time,
            "min_interval_sec": self.min_interval_sec,
        }


@dataclass
class HttpSessionContext:
    session_id: str
    safe_id: str
    base_dir: Path
    cookie_file: Path
    curlrc_path: Path
    config_path: Path
    config: Dict[str, Any]


# ============================================================================
# Session State Tracking
# ============================================================================

from datetime import datetime, timezone

class SessionState:
    """
    Module-level session state for tracking agent activity.
    Owned and reset by MiniAgent at session start.
    
    Provides bounded, in-memory tracking of:
    - Session metadata (id, start time, interaction counts)
    - Tool execution history (last N calls; default 10)
    - Recent errors (last 3)
    - Last command exit code
    """
    
    TOOL_HISTORY_LIMIT = max(1, int(os.getenv("SESSION_TOOL_HISTORY_LIMIT", "10")))

    def __init__(self):
        self.session_id: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.total_interactions: int = 0
        self.total_tool_calls: int = 0
        self.tool_history: deque = deque(maxlen=self.TOOL_HISTORY_LIMIT)
        self.recent_errors: deque = deque(maxlen=3)  # Bounded to last 3 errors
        self.last_exit_code: Optional[int] = None
    
    def reset(self, session_id: str):
        """Reset state for new session. Called by MiniAgent.__init__"""
        self.session_id = session_id
        self.start_time = datetime.now(timezone.utc)
        self.total_interactions = 0
        self.total_tool_calls = 0
        self.tool_history.clear()
        self.recent_errors.clear()
        self.last_exit_code = None
    
    def increment_interactions(self):
        """Increment user interaction count. Called per user turn."""
        self.total_interactions += 1
    
    def record_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        success: bool,
        exit_code: Optional[int] = None,
        error: Optional[str] = None
    ):
        """
        Record a tool execution.
        
        Args:
            tool_name: Name of the tool executed
            args: Tool arguments (will be truncated if >200 chars)
            success: Whether execution succeeded
            exit_code: Exit code for commands (run_command, run_python_sandbox)
            error: Error message if failed
        """
        self.total_tool_calls += 1
        
        # Truncate args to prevent bloat
        args_str = json.dumps(args, ensure_ascii=False)
        if len(args_str) > 200:
            args_str = args_str[:197] + "..."
        
        entry = {
            "tool": tool_name,
            "args": args_str,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": success,
        }
        
        if exit_code is not None:
            entry["exit_code"] = exit_code
        
        if error:
            entry["error"] = error
        
        self.tool_history.append(entry)
    
    def record_error(self, tool_name: str, error: str, context: Optional[Dict[str, Any]] = None):
        """
        Record an error for debugging.
        
        Args:
            tool_name: Name of the tool that failed
            error: Error message
            context: Optional context (e.g., command, file path)
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "error": error
        }
        
        if context:
            # Truncate context to prevent bloat
            context_str = json.dumps(context, ensure_ascii=False)
            if len(context_str) > 200:
                context_str = context_str[:197] + "..."
            entry["context"] = context_str
        
        self.recent_errors.append(entry)
    
    def set_last_exit_code(self, code: Optional[int]):
        """Set the last command exit code. Called by run_command."""
        self.last_exit_code = code
    
    def get_session_info(self) -> Dict[str, Any]:
        """Get session metadata for get_context"""
        if not self.session_id:
            return {}
        
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        return {
            "id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "duration_seconds": int(duration),
            "total_interactions": self.total_interactions,
            "total_tool_calls": self.total_tool_calls
        }
    
    def get_tool_history(self) -> List[Dict[str, Any]]:
        """Get recent tool execution history for get_context"""
        return list(self.tool_history)
    
    def get_recent_errors(self) -> List[Dict[str, Any]]:
        """Get recent errors for get_context"""
        return list(self.recent_errors)


# Global session state instance (owned by MiniAgent)
_SESSION_STATE = SessionState()


def _abs_working_dir() -> str:
    """Return the absolute working directory path."""
    return os.path.abspath(_get_working_dir_path())


def _relativize_to_working_dir(path: str) -> str:
    """Return a path relative to the working directory when possible."""
    working_dir = _abs_working_dir()
    try:
        return os.path.relpath(path, working_dir)
    except ValueError:
        return path


def _classify_path_location(path: str) -> str:
    """Classify a path as belonging to the workspace, project root, or elsewhere."""
    working_dir = _abs_working_dir()
    project_root = os.path.dirname(os.path.abspath(__file__))
    normalized = os.path.abspath(path)
    if normalized == working_dir or normalized.startswith(f"{working_dir}{os.sep}"):
        return "workspace"
    if normalized == project_root or normalized.startswith(f"{project_root}{os.sep}"):
        return "project"
    return "external"


def _record_file_event(
    operation: str,
    requested_path: str,
    source: str,
    absolute_path: Optional[str] = None
) -> None:
    """Track recent file reads/writes with absolute and relative context."""
    abs_path = os.path.abspath(absolute_path or requested_path)
    entry = {
        "operation": operation,
        "requested_path": requested_path,
        "relative_path": _relativize_to_working_dir(abs_path),
        "absolute_path": abs_path,
        "location": _classify_path_location(abs_path),
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "interactive_hint": abs_path
    }
    _RECENT_FILE_EVENTS.append(entry)
    store = _get_fs_store()
    if store and _SESSION_STATE.session_id:
        try:
            store.record_file_event(_SESSION_STATE.session_id, entry)
        except Exception:
            pass


def _extract_path_candidates(command: str, base_dir: str) -> List[Dict[str, Any]]:
    """Heuristically extract path-like tokens from the command string."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    candidates: List[Dict[str, Any]] = []
    skip_tokens = {"|", "||", "&&", ";", ">", ">>", "<"}

    def _looks_like_path(token: str) -> bool:
        if not token or token in skip_tokens:
            return False
        if token.startswith("-") or token.startswith("$"):
            return False
        if token in {"sudo", "env"}:
            return False
        if "/" in token or token.startswith(".") or token.startswith("~"):
            return True
        if "." in token and len(token) <= 128:
            return True
        return False

    for token in tokens:
        if not _looks_like_path(token):
            continue
        expanded = token
        if token.startswith("~"):
            expanded = os.path.expanduser(token)
        if os.path.isabs(expanded):
            abs_path = expanded
        else:
            abs_path = os.path.abspath(os.path.join(base_dir, expanded))
        candidates.append({
            "token": token,
            "absolute_path": abs_path,
            "relative_path": _relativize_to_working_dir(abs_path),
            "exists": os.path.exists(abs_path)
        })
    return candidates


def _record_shell_snapshot(command: str, exit_code: Optional[int], shell_cwd: Optional[str], working_dir: str):
    """Persist snapshot of the shell state after a command executes."""
    store = _get_fs_store()
    if not store or not _SESSION_STATE.session_id:
        return
    cwd = shell_cwd or working_dir
    metadata = {
        "relative_cwd": _relativize_to_working_dir(cwd),
        "recent_activity": list(_RECENT_FILE_EVENTS)[-20:],
        "path_candidates": _extract_path_candidates(command, cwd or working_dir),
    }
    payload = {
        "shell_cwd": cwd,
        "working_dir": working_dir,
        "workspace_hint": os.path.join(working_dir, "workspace"),
        "sandbox_root": WORKING_DIR_PREFIX,
        "command": command,
        "command_preview": command[:240],
        "exit_code": exit_code,
        "metadata": metadata,
    }
    try:
        store.record_snapshot(_SESSION_STATE.session_id, payload)
    except Exception:
        pass


# ============================================================================
# Base Tool Interface
# ============================================================================

class BaseTool(ABC):
    """
    Abstract base class for all tools available to the AI agent.
    
    Each tool must implement:
    - name: Unique identifier for the tool
    - description: Brief description of what the tool does
    - schema: JSON schema for tool parameters
    - execute: Method that performs the tool's action
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of tool purpose"""
        pass

    @property
    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        """JSON schema defining tool parameters for LLM"""
        pass

    @property
    def usage_examples(self) -> Optional[List[str]]:
        """
        Optional usage examples for this tool.
        Override in subclasses to provide common patterns.
        """
        return None

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """
        Execute the tool's action.
        
        Returns:
            String result to be passed back to the LLM
        """
        pass


# ============================================================================
# File Operations Tools
# ============================================================================

class ReadFileTool(BaseTool):
    """
    Read file contents into memory.
    
    Searches in: 1) Working directory (ai-terminal-wd/), 2) App directory (project root)
    Use for: Small to medium text files (< 5MB)
    Don't use for: Large files, binary files, or when you only need portions
    Alternative: Use run_command with head/tail/grep for large files
    """
    
    # Maximum file size to read (5MB default, configurable via env)
    MAX_BYTES = int(os.getenv("READ_FILE_MAX_BYTES", str(5 * 1024 * 1024)))
    
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return f"Read the contents of a file (searches in {WORKING_DIR_PREFIX}/ first, then app directory)"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": f"Read file contents. Searches {WORKING_DIR_PREFIX}/ first, then app directory. Use relative paths only (e.g., 'script.sh' not '{WORKING_DIR_PREFIX}/script.sh')",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": f"Path relative to working directory (WITHOUT '{WORKING_DIR_PREFIX}/' prefix). Examples: 'file.txt', 'subdir/data.csv', 'config/settings.json'"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        }

    def execute(self, file_path: str) -> str:
        """
        Read and return file contents.
        
        Search order:
        1. Working directory (ai-terminal-wd/)
        2. Application directory (project root)
        
        Guards:
        - File size limit to avoid memory exhaustion
        - UTF-8 encoding required (text files only)
        """
        # Try working directory first
        working_dir_path = os.path.join(_get_working_dir_path(), file_path)
        
        # If not in working dir, try app directory (project root)
        app_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir_path = os.path.join(app_dir, file_path)
        
        # Determine which path to use
        if os.path.exists(working_dir_path):
            target_path = working_dir_path
        elif os.path.exists(app_dir_path):
            target_path = app_dir_path
        else:
            return f"Error: File not found in working directory or app directory: {file_path}"
        
        try:
            # Check file size before reading
            size = os.path.getsize(target_path)
            if size > self.MAX_BYTES:
                return (
                    f"File is {size} bytes; exceeds READ_FILE_MAX_BYTES={self.MAX_BYTES}. "
                    f"Use run_command with head/tail/less for large files."
                )
            
            with open(target_path, 'r', encoding='utf-8') as f:
                content = f.read()
            _record_file_event("read", file_path, "read_file", absolute_path=target_path)
            return content
        except UnicodeDecodeError:
            return f"Error: File is not valid UTF-8 text. Use run_command with cat/hexdump for binary files."
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(BaseTool):
    """
    Create or overwrite files with text content in the isolated working directory.
    
    Use for: Config files, scripts, data files
    Note: For executable scripts, use run_command to chmod +x after writing
    """
    
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return f"Create or overwrite a file with content in the isolated working directory ({WORKING_DIR_PREFIX})"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": f"Create or overwrite a file with content. IMPORTANT: Do NOT include '{WORKING_DIR_PREFIX}/' prefix in file_path - it is automatically prepended. Example: use 'output.txt' not '{WORKING_DIR_PREFIX}/output.txt'",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": f"Path relative to working directory (WITHOUT '{WORKING_DIR_PREFIX}/' prefix). Examples: 'script.sh', 'logs/output.log', 'data/results.json'"
                        },
                        "content": {
                            "type": "string",
                            "description": "The content to write to the file"
                        }
                    },
                    "required": ["file_path", "content"]
                }
            }
        }
    
    @property
    def usage_examples(self) -> List[str]:
        return [
            "write_file('script.sh', '#!/bin/bash\\necho Hello')",
            "write_file('config/settings.json', '{\"debug\": true}')",
            "write_file('output/results.txt', 'Analysis complete\\nTotal: 100')"
        ]

    def execute(self, file_path: str, content: str) -> str:
        """
        Write content to file in isolated working directory, creating parent directories if needed.
        
        Security: No path traversal checks - agent should validate paths
        """
        # Get absolute working directory path
        working_dir = _get_working_dir_path()
        isolated_path = os.path.join(working_dir, file_path)
        
        try:
            # Ensure base working directory exists
            os.makedirs(working_dir, exist_ok=True)
            
            # Create parent directories if needed
            dirpath = os.path.dirname(isolated_path)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            
            with open(isolated_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Track this write for context awareness
            _RECENT_WRITES.append(file_path)
            _record_file_event("write", file_path, "write_file", absolute_path=isolated_path)
            
            return f"File written successfully: {isolated_path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


class HttpRequestTool(BaseTool):
    """
    Structured HTTP(S) requests via curl with session-aware profiles and telemetry.
    """

    SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

    def __init__(self):
        self.working_dir = _WORKING_DIR_PATH
        self.session_root = HTTP_SESSION_ROOT
        self.body_dir = HTTP_BODY_DIR
        self.trace_dir = HTTP_TRACE_DIR
        self.body_preview_limit = int(os.getenv("HTTP_MAX_BODY_PREVIEW", "4096"))
        self._curl_path = shutil.which("curl")
        if not self._curl_path:
            raise RuntimeError("curl binary not found in PATH")
        self._curl_version = self._detect_curl_version()
        self._supports_certs_write_out = self._curl_version >= (7, 88, 0)
        self._jq_path = shutil.which("jq")
        self._jo_path = shutil.which("jo")

        self.user_agent = "ai-terminal-http/1.0"
        self.default_profile_name = "quick_fetch"
        self.profiles: Dict[str, HttpProfile] = {
            "quick_fetch": HttpProfile("quick_fetch", timeout_sec=10, max_bytes=2 * 1024 * 1024, follow_redirects=True, retries=0, min_interval_sec=0.0),
            "gentle_crawl": HttpProfile("gentle_crawl", timeout_sec=30, max_bytes=5 * 1024 * 1024, follow_redirects=True, retries=2, retry_delay=2, retry_max_time=45, min_interval_sec=2.0),
            "deep_audit": HttpProfile("deep_audit", timeout_sec=60, max_bytes=10 * 1024 * 1024, follow_redirects=False, retries=1, retry_delay=1, retry_max_time=60, min_interval_sec=0.5),
        }
        self._session_cache: Dict[str, HttpSessionContext] = {}
        self._host_last_request: Dict[str, float] = {}
        self._dns_cache: Dict[str, Tuple[float, List[str]]] = {}
        self._dns_cache_ttl_sec = int(os.getenv("HTTP_DNS_CACHE_TTL", "300"))
        self._helper_capabilities = {
            "jq_available": bool(self._jq_path),
            "jo_available": bool(self._jo_path),
            "curl_supports_certs": self._supports_certs_write_out,
        }

    @property
    def name(self) -> str:
        return "http_request"

    def _detect_curl_version(self) -> Tuple[int, int, int]:
        if not self._curl_path:
            return (0, 0, 0)
        try:
            result = subprocess.run(
                [self._curl_path, "--version"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            output = result.stdout or ""
            match = re.search(r"curl\s+(\d+)\.(\d+)\.(\d+)", output)
            if match:
                return tuple(int(part) for part in match.groups())
        except Exception:
            pass
        return (0, 0, 0)

    @property
    def description(self) -> str:
        return (
            "Structured HTTP client backed by curl with profile presets, persistent sessions, "
            "and write-out metrics. Prefer this over run_command for web/API work."
        )

    @property
    def schema(self) -> Dict[str, Any]:
        profile_names = sorted(self.profiles.keys())
        return {
            "type": "function",
            "function": {
                "name": "http_request",
                "description": (
                    "Execute HTTP/HTTPS requests with structured output, retries, and metrics. "
                    "Pick a profile (quick_fetch, gentle_crawl, deep_audit) and optionally bind "
                    "to a named session for cookie/auth reuse."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "enum": list(self.SUPPORTED_METHODS),
                            "default": "GET",
                            "description": "HTTP method to use"
                        },
                        "url": {
                            "type": "string",
                            "description": "Target URL (http or https only)"
                        },
                        "params": {
                            "type": "object",
                            "description": "Optional query parameters to append"
                        },
                        "headers": {
                            "type": "object",
                            "description": "Additional headers (e.g., {'Accept': 'application/json'})"
                        },
                        "body_form": {
                            "type": "object",
                            "description": "Form fields encoded as application/x-www-form-urlencoded (do not mix with body_json/body_raw)"
                        },
                        "body_json": {
                            "type": "object",
                            "description": "JSON payload (serialized automatically, sets Content-Type)"
                        },
                        "body_raw": {
                            "type": "string",
                            "description": "Raw string payload. Supply Content-Type header yourself."
                        },
                        "profile": {
                            "type": "string",
                            "enum": profile_names,
                            "default": self.default_profile_name,
                            "description": "Execution profile controlling timeout/retries"
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Named session for cookie/auth reuse (defaults to 'default')"
                        },
                        "session_update": {
                            "type": "object",
                            "description": "Update session defaults (headers/auth). Fields: default_headers, remove_headers, auth_bearer, clear_auth_bearer, api_key_header, api_key_value, clear_api_key.",
                            "additionalProperties": False,
                            "properties": {
                                "default_headers": {
                                    "type": "object",
                                    "description": "Headers to persist for this session (added when missing)"
                                },
                                "remove_headers": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Headers to remove from persisted defaults"
                                },
                                "variables": {
                                    "type": "object",
                                    "description": "Session-scoped template variables (referenced via {{var}})."
                                },
                                "remove_variables": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Template variables to remove from the session store."
                                },
                                "auth_bearer": {
                                    "type": "string",
                                    "description": "Bearer token stored securely for Authorization header"
                                },
                                "clear_auth_bearer": {
                                    "type": "boolean",
                                    "description": "Set true to remove stored bearer token"
                                },
                                "api_key_header": {
                                    "type": "string",
                                    "description": "Header name for API key"
                                },
                                "api_key_value": {
                                    "type": "string",
                                    "description": "API key value"
                                },
                                "clear_api_key": {
                                    "type": "boolean",
                                    "description": "Set true to remove stored API key"
                                }
                            }
                        },
                        "variables": {
                            "type": "object",
                            "description": "Per-request template variables available via {{var}} placeholders in URL, params, headers, and bodies."
                        },
                        "follow_redirects": {
                            "type": "boolean",
                            "description": "Override profile redirect behavior"
                        },
                        "timeout_sec": {
                            "type": "integer",
                            "description": "Override profile timeout (seconds)"
                        },
                        "max_bytes": {
                            "type": "integer",
                            "description": "Override profile max response bytes"
                        },
                        "max_redirects": {
                            "type": "integer",
                            "description": "Limit number of redirects when follow_redirects=true"
                        },
                        "min_interval_sec": {
                            "type": "number",
                            "description": "Throttle requests per host by enforcing a minimum interval (seconds)"
                        },
                        "allow_local_networks": {
                            "type": "boolean",
                            "description": "Set true to allow loopback/private IPs (defaults to blocked for SSRF safety)"
                        },
                        "allow_insecure_tls": {
                            "type": "boolean",
                            "description": "Allow self-signed certificates (adds --insecure)"
                        },
                        "proxy": {
                            "type": "string",
                            "description": "Forward requests through the given proxy URL (e.g., http://user:pass@proxy:8080)"
                        },
                        "dns_servers": {
                            "type": "string",
                            "description": "Override DNS resolution order (comma-separated IP list passed to curl --dns-servers)"
                        },
                        "bind_interface": {
                            "type": "string",
                            "description": "Bind outgoing connection to a local interface or IP"
                        },
                        "http_version": {
                            "type": "string",
                            "enum": ["auto", "1.0", "1.1", "2", "3"],
                            "description": "Force an HTTP version (default auto-negotiates)"
                        },
                        "accept_compression": {
                            "type": "boolean",
                            "description": "If true, request compressed responses with curl --compressed"
                        },
                        "parse_mode": {
                            "type": "string",
                            "enum": ["auto", "json", "none"],
                            "default": "auto",
                            "description": "Control response parsing strategy"
                        },
                        "json_pointer": {
                            "type": "string",
                            "description": "Extract a specific field via RFC 6901 pointer (e.g., '/data/items/0/title')"
                        },
                        "json_selector": {
                            "type": "string",
                            "description": "Optional jq expression applied to parsed JSON responses (requires jq binary)."
                        },
                        "verbose_headers": {
                            "type": "boolean",
                            "description": "Capture verbose header trace (default true)"
                        },
                        "save_body": {
                            "type": "boolean",
                            "description": "Persist body to http_bodies even if within preview limit"
                        }
                    },
                    "required": ["url"],
                    "additionalProperties": False
                }
            }
        }

    @property
    def usage_examples(self) -> List[str]:
        return [
            "http_request(method='GET', url='https://api.github.com/repos/octocat/Hello-World')",
            "http_request(method='POST', url='https://api.example.com/chat', body_json={'prompt': 'hi'})",
            "http_request(url='https://news.ycombinator.com', profile='gentle_crawl', accept_compression=True, min_interval_sec=2)",
            "http_request(method='POST', url='https://httpbin.org/forms/post', body_form={'q': 'curl'}, parse_mode='json', json_pointer='/form/q')"
        ]

    def execute(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        body_form: Optional[Dict[str, Any]] = None,
        body_json: Optional[Dict[str, Any]] = None,
        body_raw: Optional[str] = None,
        profile: Optional[str] = None,
        session_id: Optional[str] = None,
        session_update: Optional[Dict[str, Any]] = None,
        variables: Optional[Dict[str, Any]] = None,
        follow_redirects: Optional[bool] = None,
        timeout_sec: Optional[int] = None,
        max_bytes: Optional[int] = None,
        max_redirects: Optional[int] = None,
        min_interval_sec: Optional[float] = None,
        allow_local_networks: Optional[bool] = None,
        allow_insecure_tls: Optional[bool] = None,
        proxy: Optional[str] = None,
        dns_servers: Optional[str] = None,
        bind_interface: Optional[str] = None,
        http_version: str = "auto",
        accept_compression: Optional[bool] = None,
        parse_mode: str = "auto",
        json_pointer: Optional[str] = None,
        json_selector: Optional[str] = None,
        verbose_headers: Optional[bool] = None,
        save_body: Optional[bool] = None
    ) -> str:
        try:
            request = self._prepare_request(
                url=url,
                method=method,
                params=params or {},
                headers=headers or {},
                body_form=body_form,
                body_json=body_json,
                body_raw=body_raw,
                profile_name=profile,
                session_id=session_id,
                session_update=session_update or {},
                variables=variables or {},
                follow_redirects=follow_redirects,
                timeout_override=timeout_sec,
                max_bytes_override=max_bytes,
                max_redirects=max_redirects,
                min_interval_override=min_interval_sec,
                allow_local_networks=allow_local_networks,
                allow_insecure_tls=allow_insecure_tls,
                proxy=proxy,
                dns_servers=dns_servers,
                bind_interface=bind_interface,
                http_version=http_version,
                accept_compression=accept_compression,
                parse_mode=parse_mode,
                json_pointer=json_pointer,
                json_selector=json_selector,
                verbose_headers=verbose_headers,
                save_body=save_body,
            )
            envelope = self._perform_request(request)
            _SESSION_STATE.record_tool_call(
                self.name,
                {
                    "url": request["url"],
                    "method": request["method"],
                    "profile": request["profile"].name,
                    "session_id": request.get("session_id")
                },
                success=envelope["ok"],
                exit_code=envelope.get("curl_exit_code"),
                error=envelope.get("error")
            )
            return json.dumps(envelope, indent=2)
        except Exception as exc:
            _SESSION_STATE.record_tool_call(
                self.name,
                {"url": url, "method": method},
                success=False,
                error=str(exc)
            )
            _SESSION_STATE.record_error(self.name, str(exc))
            return f"Error: {exc}"

    # ------------------------------------------------------------------
    # Request preparation
    # ------------------------------------------------------------------
    def _prepare_request(
        self,
        url: str,
        method: str,
        params: Dict[str, Any],
        headers: Dict[str, Any],
        body_form: Optional[Dict[str, Any]],
        body_json: Optional[Dict[str, Any]],
        body_raw: Optional[str],
        profile_name: Optional[str],
        session_id: Optional[str],
        session_update: Dict[str, Any],
        variables: Dict[str, Any],
        follow_redirects: Optional[bool],
        timeout_override: Optional[int],
        max_bytes_override: Optional[int],
        max_redirects: Optional[int],
        min_interval_override: Optional[float],
        allow_local_networks: Optional[bool],
        allow_insecure_tls: Optional[bool],
        proxy: Optional[str],
        dns_servers: Optional[str],
        bind_interface: Optional[str],
        http_version: str,
        accept_compression: Optional[bool],
        parse_mode: str,
        json_pointer: Optional[str],
        json_selector: Optional[str],
        verbose_headers: Optional[bool],
        save_body: Optional[bool],
    ) -> Dict[str, Any]:
        method_upper = method.upper()
        if method_upper not in self.SUPPORTED_METHODS:
            raise ValueError(f"Unsupported HTTP method: {method}")

        request_vars = {str(k): "" if v is None else str(v) for k, v in (variables or {}).items()}
        profile = self.profiles.get(profile_name or self.default_profile_name)
        if not profile:
            raise ValueError(f"Unknown profile: {profile_name}")

        session_identifier = session_id
        if session_identifier is None:
            session_identifier = "default"
        else:
            session_identifier = str(session_identifier)
            if not session_identifier.strip():
                session_identifier = None
        session_ctx = self._ensure_session(session_identifier) if session_identifier else None
        if session_ctx and session_update:
            self._apply_session_update(session_ctx, session_update)

        scope = self._build_variable_scope(session_ctx, request_vars)
        templated_params = self._render_template_mapping(params, scope)
        templated_url = self._render_template_string(url, scope)
        normalized_url = self._merge_query_params(templated_url, templated_params)
        parsed = urlparse(normalized_url)
        host = parsed.hostname
        if not host:
            raise ValueError("URL missing host information.")
        allow_local = bool(allow_local_networks)
        self._validate_target_host(host, allow_local)
        min_interval_value = (
            max(0.0, float(min_interval_override))
            if min_interval_override is not None
            else profile.min_interval_sec
        )
        throttle_delay = 0.0
        if min_interval_value > 0:
            throttle_delay = self._throttle_host(host, min_interval_value)

        scope = self._build_variable_scope(
            session_ctx,
            request_vars,
            extra={
                "target_host": host or "",
                "profile": profile.name,
                "session_id": session_ctx.session_id if session_ctx else "",
                "method": method_upper,
            },
        )
        templated_headers = self._render_template_mapping(headers, scope)
        normalized_headers = self._normalize_headers(templated_headers)
        if session_ctx:
            normalized_headers = self._apply_session_headers(normalized_headers, session_ctx.config)
        body_payload = None
        body_mode = None
        body_is_json = False
        templated_body_form = self._render_template_mapping(body_form, scope) if body_form is not None else None
        templated_body_json = self._render_template_value(body_json, scope) if body_json is not None else None
        templated_body_raw = self._render_template_string(body_raw, scope)

        provided_bodies = sum(
            1
            for candidate in (templated_body_form, templated_body_json, templated_body_raw)
            if candidate is not None
        )
        if provided_bodies > 1:
            raise ValueError("Provide at most one of body_form, body_json, or body_raw.")
        if templated_body_json is not None:
            body_payload = json.dumps(templated_body_json, separators=(",", ":"))
            body_is_json = True
            body_mode = "json"
            if not any(k.lower() == "content-type" for k in normalized_headers):
                normalized_headers["Content-Type"] = "application/json"
        elif templated_body_form is not None:
            form_items: List[Tuple[str, str]] = []
            for key, value in templated_body_form.items():
                if value is None:
                    continue
                if isinstance(value, list):
                    for item in value:
                        form_items.append((str(key), str(item)))
                else:
                    form_items.append((str(key), str(value)))
            body_payload = urlencode(form_items, doseq=True)
            body_mode = "form"
            if not any(k.lower() == "content-type" for k in normalized_headers):
                normalized_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif templated_body_raw is not None:
            body_payload = templated_body_raw
            body_mode = "raw"

        timeout_value = timeout_override or profile.timeout_sec
        max_bytes_value = max_bytes_override or profile.max_bytes
        follow = follow_redirects if follow_redirects is not None else profile.follow_redirects
        max_redirects_value = max_redirects
        if max_redirects_value is not None and max_redirects_value < 0:
            raise ValueError("max_redirects must be >= 0.")
        min_interval_chosen = min_interval_value if min_interval_override is not None else profile.min_interval_sec

        parse_mode_normalized = (parse_mode or "auto").lower()
        if parse_mode_normalized not in {"auto", "json", "none"}:
            raise ValueError("parse_mode must be one of 'auto', 'json', or 'none'.")
        http_version_normalized = (http_version or "auto").lower()
        if http_version_normalized not in {"auto", "1.0", "1.1", "2", "3"}:
            raise ValueError("http_version must be one of auto, 1.0, 1.1, 2, 3.")
        verbose_choice = True if verbose_headers is None else bool(verbose_headers)

        return {
            "url": normalized_url,
            "method": method_upper,
            "headers": normalized_headers,
            "body": body_payload,
            "body_is_json": body_is_json,
            "body_mode": body_mode,
            "profile": profile,
            "session": session_ctx,
            "session_id": session_ctx.session_id if session_ctx else None,
            "target_host": host,
            "follow_redirects": follow,
            "timeout_sec": timeout_value,
            "max_bytes": max_bytes_value,
            "max_redirects": max_redirects_value,
            "min_interval_sec": min_interval_chosen,
            "allow_local_networks": allow_local,
            "allow_insecure_tls": bool(allow_insecure_tls),
            "proxy": proxy,
            "dns_servers": dns_servers,
            "bind_interface": bind_interface,
            "http_version": http_version_normalized,
            "accept_compression": bool(accept_compression) if accept_compression is not None else False,
            "parse_mode": parse_mode_normalized,
            "json_pointer": json_pointer,
            "json_selector": json_selector,
            "verbose_headers": verbose_choice,
            "save_body": bool(save_body) if save_body is not None else False,
            "throttle_delay": throttle_delay,
        }

    def _normalize_headers(self, headers: Dict[str, Any]) -> Dict[str, str]:
        normalized = {}
        for key, value in headers.items():
            if key is None:
                continue
            normalized[str(key).strip()] = str(value)
        return normalized

    def _merge_query_params(self, url: str, params: Dict[str, Any]) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only http and https schemes are supported.")
        existing_params = list(parse_qsl(parsed.query, keep_blank_values=True))
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, list):
                for item in value:
                    existing_params.append((str(key), str(item)))
            else:
                existing_params.append((str(key), str(value)))
        new_query = urlencode(existing_params, doseq=True)
        updated = parsed._replace(query=new_query)
        return urlunparse(updated)

    def _build_variable_scope(
        self,
        session_ctx: Optional[HttpSessionContext],
        request_vars: Dict[str, str],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        scope: Dict[str, str] = {}
        if session_ctx:
            for key, value in (session_ctx.config.get("variables") or {}).items():
                scope[str(key)] = "" if value is None else str(value)
        for key, value in (request_vars or {}).items():
            scope[str(key)] = "" if value is None else str(value)
        if extra:
            for key, value in extra.items():
                if value is None:
                    continue
                scope[str(key)] = str(value)
        return scope

    def _render_template_mapping(self, data: Dict[str, Any], scope: Dict[str, str]) -> Dict[str, Any]:
        return {key: self._render_template_value(value, scope) for key, value in data.items()}

    def _render_template_value(self, value: Any, scope: Dict[str, str]) -> Any:
        if isinstance(value, str):
            return self._render_template_string(value, scope)
        if isinstance(value, list):
            return [self._render_template_value(item, scope) for item in value]
        if isinstance(value, dict):
            return {k: self._render_template_value(v, scope) for k, v in value.items()}
        return value

    def _render_template_string(self, value: Optional[str], scope: Dict[str, str]) -> Optional[str]:
        if value is None or not isinstance(value, str) or not scope:
            return value

        def _apply_filters(raw_value: str, suffix: Optional[str]) -> str:
            if suffix:
                filters = [token for token in suffix.replace("|", ":").split(":") if token]
            else:
                filters = []
            result = raw_value
            for filter_name in filters:
                name = filter_name.lower()
                if name == "trim":
                    result = result.strip()
                elif name == "lower":
                    result = result.lower()
                elif name == "upper":
                    result = result.upper()
                elif name == "url":
                    result = quote_plus(result)
                elif name == "json":
                    result = json.dumps(result, separators=(",", ":"))
                else:
                    # Unknown filter -> leave value unchanged
                    continue
            return result

        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            filters = match.group(2)
            raw_value = scope.get(var_name, "")
            return _apply_filters(raw_value, filters)

        return TEMPLATE_PATTERN.sub(replacer, value)

    # ------------------------------------------------------------------
    # Network safety helpers
    # ------------------------------------------------------------------
    def _validate_target_host(self, host: str, allow_local: bool) -> None:
        if allow_local:
            return
        if self._host_is_ip(host):
            if self._ip_is_disallowed(host):
                raise ValueError(f"SSRF protection: host {host} is not reachable from this tool.")
            return
        resolved_ips = self._resolve_host_ips(host)
        if any(self._ip_is_disallowed(ip) for ip in resolved_ips):
            raise ValueError(f"SSRF protection: {host} resolves to a private or loopback network.")

    def _resolve_host_ips(self, host: str) -> List[str]:
        cached = self._dns_cache.get(host)
        now = time.time()
        if cached and now - cached[0] < self._dns_cache_ttl_sec:
            return cached[1]
        ips: List[str] = []
        try:
            results = socket.getaddrinfo(host, None)
            for _family, _type, _proto, _canon, sockaddr in results:
                if sockaddr and sockaddr[0]:
                    ips.append(sockaddr[0])
        except socket.gaierror:
            return []
        self._dns_cache[host] = (now, ips)
        return ips

    def _host_is_ip(self, host: str) -> bool:
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False

    def _ip_is_disallowed(self, ip_value: str) -> bool:
        try:
            ip_obj = ipaddress.ip_address(ip_value)
        except ValueError:
            return True
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
        )

    def _throttle_host(self, host: str, min_interval: float) -> float:
        last = self._host_last_request.get(host)
        now = time.monotonic()
        delay = 0.0
        if last is not None:
            elapsed = now - last
            if elapsed < min_interval:
                delay = max(0.0, min_interval - elapsed)
                time.sleep(delay)
                now = time.monotonic()
        self._host_last_request[host] = now
        return delay

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------
    def _perform_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        trace_id = uuid4().hex[:8]
        markers = self._build_markers(trace_id)
        command = self._build_command(request, markers)
        result = self._run_curl(command, request["timeout_sec"])
        stdout = result.stdout or b""
        stderr = result.stderr or b""
        body_bytes, metrics, certs_raw = self._parse_curl_output(stdout, markers)
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        status = metrics.get("response_code") or metrics.get("http_code")
        ok = result.returncode == 0 and status is not None and 200 <= int(status) < 400

        preview, body_path, truncated = self._handle_body_artifacts(
            trace_id, body_bytes, force_persist=request.get("save_body")
        )
        body_format = self._detect_body_format(metrics, body_bytes)
        parsed_json = None
        json_pointer_value = None
        json_pointer_error = None
        parse_mode = request.get("parse_mode", "auto")
        if self._should_parse_body(parse_mode, body_format) and body_bytes:
            parsed_json = self._parse_json_body(body_bytes)
            pointer = request.get("json_pointer")
            if parsed_json is not None and pointer:
                try:
                    json_pointer_value = self._extract_json_pointer(parsed_json, pointer)
                except ValueError as exc:
                    json_pointer_error = str(exc)
        json_selector_value = None
        json_selector_error = None
        json_selector = request.get("json_selector")
        if json_selector:
            if parsed_json is None:
                json_selector_error = "Response body is not JSON."
            elif not self._jq_path:
                json_selector_error = "jq binary not available on host."
            else:
                try:
                    json_selector_value = self._run_jq_selector(json_selector, parsed_json)
                except Exception as exc:
                    json_selector_error = str(exc)
        latency = self._extract_latency(metrics)
        cert_chain = self._normalize_certificates(certs_raw)
        diagnostics = self._build_diagnostics(metrics, cert_chain)

        header_trace = None
        if request.get("verbose_headers", True):
            header_trace = self._parse_verbose_headers(stderr_text)

        error_type, error_message = (None, None)
        if not ok:
            error_type, error_message = self._classify_error(
                exit_code=result.returncode,
                status=status,
                metrics=metrics,
                stderr=stderr_text,
            )
        ssrf_block = self._detect_ssrf_violation(metrics, request.get("allow_local_networks"))
        if ssrf_block:
            ok = False
            error_type = error_type or "ssrf_blocked"
            error_message = error_message or f"SSRF protection blocked remote IP {ssrf_block}."
        if not error_message:
            error_message = metrics.get("errormsg") or stderr_text or (None if ok else "Request failed")

        envelope = {
            "ok": ok,
            "status": int(status) if status is not None else None,
            "status_text": metrics.get("errormsg"),
            "url": request["url"],
            "request_method": request["method"],
            "session_id": request.get("session_id"),
            "target_host": request.get("target_host"),
            "profile": request["profile"].name,
            "headers": self._redact_headers(request["headers"]),
            "content_type": metrics.get("content_type"),
            "body_format": body_format,
            "body_preview": preview,
            "body_path": body_path,
            "body_truncated": truncated,
            "parsed_json": parsed_json,
            "parse_mode": parse_mode,
            "json_pointer": request.get("json_pointer"),
            "json_pointer_value": json_pointer_value,
            "json_pointer_error": json_pointer_error,
            "json_selector": json_selector,
            "json_selector_value": json_selector_value,
            "json_selector_error": json_selector_error,
            "metrics": metrics,
            "diagnostics": diagnostics or None,
            "latency": latency or None,
            "curl_exit_code": result.returncode,
            "stderr": stderr_text or None,
            "trace_id": trace_id,
            "error": error_message,
            "error_type": error_type,
            "http_headers": header_trace,
            "throttle_delay_sec": request.get("throttle_delay"),
            "allow_local_networks": request.get("allow_local_networks"),
            "min_interval_sec": request.get("min_interval_sec"),
            "certificate_chain": cert_chain,
            "helper_capabilities": self._helper_capabilities,
            "ssrf_remote_ip": ssrf_block,
        }

        self._persist_trace(trace_id, request, envelope, command)
        return envelope

    def _build_markers(self, trace_id: str) -> Dict[str, Optional[str]]:
        base = f"__AI_HTTP_JSON__{trace_id}__"
        markers = {"json": f"{base}JSON__"}
        markers["cert"] = f"{base}CERT__" if self._supports_certs_write_out else None
        return markers

    def _build_command(self, request: Dict[str, Any], markers: Dict[str, Optional[str]]) -> List[str]:
        cmd = [
            self._curl_path,
            "--silent",
            "--show-error",
            "--no-progress-meter",
            "--proto",
            "=http,https",
            "--user-agent",
            self.user_agent,
            "--max-time",
            str(request["timeout_sec"]),
            "--max-filesize",
            str(request["max_bytes"])
        ]

        session_ctx = request.get("session")
        if session_ctx:
            cmd.extend(["--config", str(session_ctx.curlrc_path)])

        profile = request["profile"]
        if profile.retries > 0:
            cmd.extend(["--retry", str(profile.retries), "--retry-delay", str(profile.retry_delay)])
            if profile.retry_max_time:
                cmd.extend(["--retry-max-time", str(profile.retry_max_time)])
            cmd.append("--retry-connrefused")

        if request.get("allow_insecure_tls"):
            cmd.append("--insecure")

        if proxy := request.get("proxy"):
            cmd.extend(["--proxy", proxy])
        if dns_servers := request.get("dns_servers"):
            cmd.extend(["--dns-servers", dns_servers])
        if bind_interface := request.get("bind_interface"):
            cmd.extend(["--interface", bind_interface])

        if request["follow_redirects"]:
            cmd.append("--location")
            if request.get("max_redirects") is not None:
                cmd.extend(["--max-redirs", str(request["max_redirects"])])
        else:
            cmd.extend(["--max-redirs", "0"])

        http_version = request.get("http_version", "auto")
        if http_version == "1.0":
            cmd.append("--http1.0")
        elif http_version == "1.1":
            cmd.append("--http1.1")
        elif http_version == "2":
            cmd.append("--http2")
        elif http_version == "3":
            cmd.append("--http3")

        cmd.extend(["--request", request["method"], "--url", request["url"]])

        for key, value in request["headers"].items():
            cmd.extend(["--header", f"{key}: {value}"])

        if request["body"] is not None:
            body_mode = request.get("body_mode")
            if body_mode == "form":
                cmd.extend(["--data", request["body"]])
            else:
                cmd.extend(["--data-raw", request["body"]])

        if request.get("accept_compression"):
            cmd.append("--compressed")

        if request.get("verbose_headers", True):
            cmd.append("--verbose")

        write_out = f"{markers['json']}%{{json}}"
        cert_marker = markers.get("cert")
        if cert_marker:
            write_out += f"{cert_marker}%{{certs}}"
        cmd.extend(["-w", write_out])
        return cmd

    def _run_curl(self, command: List[str], timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.working_dir,
            timeout=timeout + 2
        )

    def _parse_curl_output(self, stdout: bytes, markers: Dict[str, Optional[str]]) -> Tuple[bytes, Dict[str, Any], Optional[Any]]:
        json_marker_bytes = (markers["json"] or "").encode("utf-8")
        idx = stdout.rfind(json_marker_bytes)
        if idx == -1:
            raise ValueError("Failed to parse curl output (missing metrics marker).")
        body = stdout[:idx]
        trailing = stdout[idx + len(json_marker_bytes):]
        cert_marker = markers.get("cert")
        cert_bytes = None
        if cert_marker:
            cert_marker_bytes = cert_marker.encode("utf-8")
            cert_idx = trailing.rfind(cert_marker_bytes)
            if cert_idx != -1:
                cert_bytes = trailing[cert_idx + len(cert_marker_bytes):].strip()
                metrics_bytes = trailing[:cert_idx].strip()
            else:
                metrics_bytes = trailing.strip()
        else:
            metrics_bytes = trailing.strip()
        if not metrics_bytes:
            raise ValueError("Curl metrics missing or empty.")
        try:
            metrics = json.loads(metrics_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse curl metrics: {exc}") from exc
        cert_data = None
        if cert_bytes:
            try:
                cert_data = json.loads(cert_bytes.decode("utf-8"))
            except json.JSONDecodeError:
                cert_data = None
        return body, metrics, cert_data

    def _handle_body_artifacts(self, trace_id: str, body_bytes: bytes, force_persist: bool = False) -> Tuple[str, Optional[str], bool]:
        if body_bytes is None:
            return "", None, False
        truncated = len(body_bytes) > self.body_preview_limit
        preview_bytes = body_bytes[: self.body_preview_limit]
        preview = preview_bytes.decode("utf-8", errors="replace")
        body_path = None
        if truncated or force_persist:
            body_path = self._write_body_file(trace_id, body_bytes)
        return preview, body_path, truncated

    def _write_body_file(self, trace_id: str, body_bytes: bytes) -> str:
        path = self.body_dir / f"{trace_id}.body"
        path.write_bytes(body_bytes)
        path_str = str(path)
        _RECENT_WRITES.append(path_str)
        _record_file_event("write", _relativize_to_working_dir(path_str), "http_request", absolute_path=path_str)
        return path_str

    def _persist_trace(self, trace_id: str, request: Dict[str, Any], envelope: Dict[str, Any], command: List[str]) -> None:
        trace_payload = {
            "trace_id": trace_id,
            "request": {
                "method": request["method"],
                "url": request["url"],
                "session_id": request.get("session_id"),
                "profile": request["profile"].name,
                "headers": self._redact_headers(request["headers"]),
            },
            "response": {
                "ok": envelope["ok"],
                "status": envelope["status"],
                "content_type": envelope["content_type"],
                "body_path": envelope["body_path"],
                "body_truncated": envelope["body_truncated"]
            },
            "http_headers": envelope.get("http_headers"),
            "metrics": envelope["metrics"],
            "curl_exit_code": envelope.get("curl_exit_code"),
            "command": self._redact_command(command)
        }
        trace_path = self.trace_dir / f"trace-{trace_id}.json"
        trace_path.write_text(json.dumps(trace_payload, indent=2))
        trace_path_str = str(trace_path)
        _RECENT_WRITES.append(trace_path_str)
        _record_file_event("write", _relativize_to_working_dir(trace_path_str), "http_request", absolute_path=trace_path_str)

    def _redact_headers(self, headers: Dict[str, str]) -> Dict[str, Any]:
        redacted = {}
        for key, value in headers.items():
            redacted[key] = self._redact_header_value(key, value)
        return redacted

    def _redact_header_value(self, key: str, value: str) -> str:
        if key.lower() in {"authorization", "cookie", "set-cookie"}:
            return "<redacted>"
        return value

    def _redact_command(self, command: List[str]) -> str:
        safe_parts = []
        skip_next = False
        sensitive_flags = {"--header", "--data-raw", "--proxy"}
        for part in command:
            if skip_next:
                safe_parts.append("<redacted>")
                skip_next = False
                continue
            lowered = part.lower()
            safe_parts.append(part)
            if lowered in sensitive_flags:
                skip_next = True
        return " ".join(shlex.quote(p) for p in safe_parts)

    def _extract_latency(self, metrics: Dict[str, Any]) -> Dict[str, float]:
        latency = {}
        for metric_key, label in TIME_KEYS.items():
            value = metrics.get(metric_key)
            if value in (None, ""):
                continue
            try:
                latency[label] = float(value)
            except (TypeError, ValueError):
                continue
        return latency

    def _build_diagnostics(self, metrics: Dict[str, Any], cert_chain: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        diag = {}
        mapping = {
            "http_version": "http_version",
            "num_redirects": "redirect_count",
            "redirect_url": "redirect_url",
            "remote_ip": "remote_ip",
            "remote_port": "remote_port",
            "local_ip": "local_ip",
            "local_port": "local_port",
            "ssl_verify_result": "ssl_verify_result",
            "proxy_ssl_verify_result": "proxy_ssl_verify_result",
            "num_certs": "certificate_count",
            "certs": "certificate_chain",
            "size_download": "bytes_download",
            "size_upload": "bytes_upload",
            "size_header": "header_bytes",
            "size_request": "request_bytes",
            "speed_download": "speed_download",
            "speed_upload": "speed_upload",
            "url": "requested_url",
            "url_effective": "final_url",
        }
        for source, target in mapping.items():
            value = metrics.get(source)
            if value in (None, ""):
                continue
            diag[target] = value
        if cert_chain:
            diag["certificate_chain"] = cert_chain
        return diag

    def _normalize_certificates(self, certs_raw: Optional[Any]) -> Optional[List[Dict[str, Any]]]:
        if not certs_raw:
            return None
        cert_entries: Any = certs_raw
        if isinstance(certs_raw, dict) and "certs" in certs_raw:
            cert_entries = certs_raw.get("certs")
        if not isinstance(cert_entries, list):
            return None
        normalized: List[Dict[str, Any]] = []
        for cert in cert_entries:
            if not isinstance(cert, dict):
                continue
            normalized.append(
                {
                    "subject": cert.get("Subject"),
                    "issuer": cert.get("Issuer"),
                    "valid_from": cert.get("Start date") or cert.get("Start Date"),
                    "valid_to": cert.get("Expire date") or cert.get("Expire Date"),
                    "serial": cert.get("Serial Number"),
                    "sha256": cert.get("SHA256") or cert.get("SHA256 Fingerprint"),
                    "sha1": cert.get("SHA1") or cert.get("SHA1 Fingerprint"),
                    "public_key_algorithm": cert.get("Public Key type") or cert.get("Public Algorithm"),
                }
            )
        return normalized or None

    def _detect_body_format(self, metrics: Dict[str, Any], body_bytes: Optional[bytes]) -> Optional[str]:
        content_type = (metrics.get("content_type") or "").lower()
        if "json" in content_type:
            return "json"
        if "html" in content_type:
            return "html"
        if "xml" in content_type:
            return "xml"
        if not body_bytes:
            return None
        sample = body_bytes[:512].lstrip()
        if not sample:
            return None
        prefix = sample[:16].lower()
        if prefix.startswith(b"{") or prefix.startswith(b"["):
            return "json"
        if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
            return "html"
        if prefix.startswith(b"<?xml") or sample.startswith(b"<rss"):
            return "xml"
        return None

    def _parse_json_body(self, body_bytes: bytes) -> Optional[Any]:
        try:
            return json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return None

    def _run_jq_selector(self, selector: str, payload: Any) -> Any:
        if not self._jq_path:
            raise RuntimeError("jq binary not available.")
        try:
            proc = subprocess.run(
                [self._jq_path, "--compact-output", selector],
                input=json.dumps(payload, separators=(",", ":")),
                text=True,
                capture_output=True,
                timeout=3,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to launch jq: {exc}") from exc
        if proc.returncode != 0:
            error = proc.stderr.strip() or f"jq exited with {proc.returncode}"
            raise RuntimeError(error)
        output = proc.stdout.strip()
        if not output:
            return None
        lines = [line for line in output.splitlines() if line.strip()]
        if not lines:
            return None
        if len(lines) == 1:
            line = lines[0]
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                return line
        results = []
        for line in lines:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                results.append(line)
        return results

    def _should_parse_body(self, parse_mode: str, body_format: Optional[str]) -> bool:
        if parse_mode == "none":
            return False
        if parse_mode == "json":
            return True
        return body_format == "json"

    def _extract_json_pointer(self, data: Any, pointer: str) -> Any:
        if pointer in (None, "", "/"):
            return data
        if not pointer.startswith("/"):
            raise ValueError("JSON pointer must start with '/'.")
        current = data
        parts = pointer.lstrip("/").split("/")
        for raw_token in parts:
            token = raw_token.replace("~1", "/").replace("~0", "~")
            if isinstance(current, list):
                if not token.isdigit():
                    raise ValueError(f"Pointer token '{token}' is not a list index.")
                idx = int(token)
                if idx >= len(current):
                    raise ValueError(f"Pointer token '{token}' out of range.")
                current = current[idx]
            elif isinstance(current, dict):
                if token not in current:
                    raise ValueError(f"Pointer token '{token}' missing in object.")
                current = current[token]
            else:
                raise ValueError(f"Cannot descend into type {type(current).__name__} at token '{token}'.")
        return current

    def _detect_ssrf_violation(self, metrics: Dict[str, Any], allow_local: bool) -> Optional[str]:
        if allow_local:
            return None
        remote_ip = metrics.get("remote_ip")
        if remote_ip and self._ip_is_disallowed(remote_ip):
            return remote_ip
        return None

    def _parse_verbose_headers(self, stderr_text: Optional[str]) -> Optional[Dict[str, Any]]:
        if not stderr_text:
            return None
        request_headers: List[Dict[str, str]] = []
        response_headers: List[Dict[str, str]] = []
        for raw_line in stderr_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("> "):
                content = line[2:].strip()
                if not content or content in {"{", "}"}:
                    continue
                entry = self._parse_verbose_line(content, is_request=True)
                if entry:
                    request_headers.append(entry)
            elif line.startswith("< "):
                content = line[2:].strip()
                if not content or content in {"{", "}"}:
                    continue
                entry = self._parse_verbose_line(content, is_request=False)
                if entry:
                    response_headers.append(entry)
        if not request_headers and not response_headers:
            return None
        return {"request": request_headers, "response": response_headers}

    def _parse_verbose_line(self, content: str, is_request: bool) -> Optional[Dict[str, str]]:
        if ":" in content:
            name, value = content.split(":", 1)
            return {
                "name": name.strip(),
                "value": self._redact_header_value(name.strip(), value.strip())
            }
        return {"line": content}

    def _classify_error(
        self,
        exit_code: int,
        status: Optional[int],
        metrics: Dict[str, Any],
        stderr: Optional[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        if exit_code:
            mapped = CURL_EXIT_CODE_MAP.get(exit_code)
            if mapped:
                return mapped
            return (
                "curl_error",
                f"Curl exited with code {exit_code}: {stderr or 'Unknown error'}",
            )

        if status:
            if status in HTTP_STATUS_ERROR_MAP:
                return HTTP_STATUS_ERROR_MAP[status]
            if 500 <= status < 600:
                return ("server_error", f"Server error (HTTP {status}).")
            if status == 429:
                return ("rate_limit", "Too many requests / rate limited.")
            if status in (401, 403):
                return ("auth_error", f"Authentication/authorization failed (HTTP {status}).")
            if 400 <= status < 500:
                return ("http_error", f"Client error (HTTP {status}).")

        return (None, None)

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------
    def _ensure_session(self, session_id: str) -> HttpSessionContext:
        safe_id = self._sanitize_session_id(session_id)
        if safe_id in self._session_cache:
            return self._session_cache[safe_id]

        base_dir = self.session_root / safe_id
        base_dir.mkdir(parents=True, exist_ok=True)
        cookie_file = base_dir / "cookies.txt"
        if not cookie_file.exists():
            cookie_file.touch()
            try:
                os.chmod(cookie_file, 0o600)
            except PermissionError:
                pass
        curlrc_path = base_dir / ".curlrc"
        curlrc_content = textwrap.dedent(f"""
            # Auto-generated session config for {session_id}
            cookie = "{cookie_file}"
            cookie-jar = "{cookie_file}"
        """).strip() + "\n"
        existing_content = curlrc_path.read_text() if curlrc_path.exists() else None
        if existing_content != curlrc_content:
            curlrc_path.write_text(curlrc_content)
        config_path = base_dir / SESSION_CONFIG_FILENAME
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
            except Exception:
                config = json.loads(json.dumps(DEFAULT_SESSION_CONFIG))
        else:
            config = json.loads(json.dumps(DEFAULT_SESSION_CONFIG))
            config_path.write_text(json.dumps(config, indent=2))
            try:
                os.chmod(config_path, 0o600)
            except PermissionError:
                pass
        ctx = HttpSessionContext(
            session_id=session_id,
            safe_id=safe_id,
            base_dir=base_dir,
            cookie_file=cookie_file,
            curlrc_path=curlrc_path,
            config_path=config_path,
            config=config
        )
        self._session_cache[safe_id] = ctx
        return ctx

    def _sanitize_session_id(self, session_id: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", session_id.strip())
        return safe or "default"

    def _save_session_config(self, ctx: HttpSessionContext) -> None:
        ctx.config_path.write_text(json.dumps(ctx.config, indent=2))
        try:
            os.chmod(ctx.config_path, 0o600)
        except PermissionError:
            pass

    def _apply_session_update(self, ctx: HttpSessionContext, update: Dict[str, Any]) -> None:
        config = ctx.config or json.loads(json.dumps(DEFAULT_SESSION_CONFIG))
        headers = config.get("default_headers") or {}
        for key, value in (update.get("default_headers") or {}).items():
            headers[str(key)] = str(value)
        for key in update.get("remove_headers", []):
            headers.pop(str(key), None)
        config["default_headers"] = headers

        variables = config.get("variables") or {}
        for key, value in (update.get("variables") or {}).items():
            variables[str(key)] = "" if value is None else str(value)
        for key in update.get("remove_variables", []):
            variables.pop(str(key), None)
        config["variables"] = variables

        if "auth_bearer" in update:
            config["auth_bearer"] = update.get("auth_bearer") or None
        if update.get("clear_auth_bearer"):
            config["auth_bearer"] = None

        api_key = config.get("api_key") or {"header": None, "value": None}
        if "api_key_header" in update:
            api_key["header"] = update.get("api_key_header")
        if "api_key_value" in update:
            api_key["value"] = update.get("api_key_value")
        if update.get("clear_api_key"):
            api_key = {"header": None, "value": None}
        config["api_key"] = api_key

        ctx.config = config
        self._save_session_config(ctx)

    def _apply_session_headers(self, headers: Dict[str, str], config: Dict[str, Any]) -> Dict[str, str]:
        result = dict(headers)
        defaults = config.get("default_headers") or {}
        for key, value in defaults.items():
            if not self._has_header(result, key):
                result[key] = value
        bearer = config.get("auth_bearer")
        if bearer and not self._has_header(result, "Authorization"):
            result["Authorization"] = f"Bearer {bearer}"
        api_key = config.get("api_key") or {}
        api_header = api_key.get("header")
        api_value = api_key.get("value")
        if api_header and api_value and not self._has_header(result, api_header):
            result[api_header] = api_value
        return result

    def _has_header(self, headers: Dict[str, str], name: str) -> bool:
        target = name.lower()
        return any(k.lower() == target for k in headers.keys())


# ============================================================================
# Shell Command Execution Tools
# ============================================================================

class RunCommandTool(BaseTool):
    """
    Execute non-interactive shell commands.
    
    Use for: File operations, text processing, system queries, shell pipelines
    Don't use for: Interactive programs (vim, top), Python REPL
    
    Guards:
    - Blocks interactive commands → redirect to run_interactive
    """
    
    def __init__(self, shell: 'ShellIntegration' = None):
        # Initialize shell in the working directory so commands can access files
        self.working_dir = _get_working_dir_path()
        os.makedirs(self.working_dir, exist_ok=True)
        self.shell = shell or ShellIntegration(working_dir=self.working_dir)

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return "Execute a non-interactive shell command. Do not use for: interactive programs (vim, nano, top), or package managers without --noconfirm flag."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Execute a non-interactive shell command. Package managers (yay/pacman) must include --noconfirm flag. Will timeout if used with interactive programs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute"
                        }
                    },
                    "required": ["command"]
                }
            }
        }
    
    @property
    def usage_examples(self) -> List[str]:
        return [
            "ls -la /home/user/projects",
            "grep -r 'TODO' ./src",
            "find . -name '*.py' -type f",
            "ps aux | grep python",
            "df -h"
        ]

    def execute(self, command: str) -> str:
        """
        Execute shell command with safety guards.
        
        Protection layers:
        1. Interactive command detection → redirect to run_interactive
        2. Smart bypass for safe flags (--version, --help, -c for interpreters)
        """
        try:
            # Parse command tokens
            tokens = shlex.split(command) if command.strip() else []
            if not tokens:
                return "Error: Empty command"
            
            # Control operators that delimit simple commands in a pipeline
            CONTROL_OPS = {'|', '||', '&&', ';'}
            
            # Extract first simple command (before any pipe/control operator)
            first_cmd_tokens = []
            for t in tokens:
                if t in CONTROL_OPS:
                    break
                first_cmd_tokens.append(t)
            
            if not first_cmd_tokens:
                return "Error: Empty command"
            
            # Identify the actual command being executed
            base = first_cmd_tokens[0]
            base_name = os.path.basename(base)

            # ----------------------------------------------------------------
            # GUARD: Interactive command detection using robust parser
            # ----------------------------------------------------------------
            is_interactive, reason = parse_command(command)
            
            if is_interactive:
                # Extract command name for error message
                try:
                    cmd_name = shlex.split(command)[0] if command else "command"
                except:
                    cmd_name = "command"
                
                return (
                    f"Error: Interactive command detected - {reason}. "
                    f"Use run_interactive tool to avoid timeout."
                )
            
            # Execute command via shell integration
            # Force reset to working directory before each command (stateless cwd)
            wrapped = f"cd {shlex.quote(self.working_dir)}; {command}"
            result = self.shell.run_command(wrapped, reset_dir=self.working_dir)
            try:
                _record_shell_snapshot(
                    command=command,
                    exit_code=getattr(self.shell, "last_exit_code", None),
                    shell_cwd=self.shell.get_current_dir(),
                    working_dir=self.working_dir,
                )
            except Exception:
                pass
            return result
            
        except Exception as e:
            return f"Error executing command: {str(e)}"



class InteractiveCommandTool(BaseTool):
    """
    Execute interactive programs that require TTY (terminal control).
    
    Use for: Text editors (vim, nano), TUI programs (top, htop), interactive shells
    Requires: TTY-enabled environment (won't work in background/cron jobs)
    Note: Agent cannot interact with the program - user controls it directly
    """
    
    # Commands known to require full terminal control
    INTERACTIVE_COMMANDS = {
        'vim', 'vi', 'nano', 'emacs', 'less', 'more', 'top', 'htop', 
        'man', 'ssh', 'mysql', 'psql', 'mongo', 'python', 'python3',
        'node', 'irb', 'ruby', 'bash', 'zsh', 'sh', 'tmux', 'screen'
    }
    
    @property
    def name(self) -> str:
        return "run_interactive"
    
    @property
    def description(self) -> str:
        return "Execute an interactive command that requires full terminal control (vim, nano, top, etc.)"
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "run_interactive",
                "description": "Execute an interactive command that requires full terminal control (vim, nano, top, etc.)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The interactive command to execute (e.g., 'vim file.txt', 'top', 'nano config.py')"
                        }
                    },
                    "required": ["command"]
                }
            }
        }
    
    @property
    def usage_examples(self) -> List[str]:
        return [
            "vim /etc/hosts",
            "nano ~/.bashrc",
            "top",
            "htop"
        ]
    
    def execute(self, command: str) -> str:
        """
        Pass full terminal control to the command.
        
        Limitations:
        - Requires TTY (fails in non-interactive contexts)
        - Agent cannot see or control the program
        - User must interact directly
        """
        try:
            # Verify TTY availability
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                return "Interactive commands require a TTY; cannot run in non-interactive environment."
            
            # Execute with full terminal control - stdin/stdout/stderr connected
            result = subprocess.run(
                command,
                shell=True,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            
            # Report exit status
            if result.returncode == 0:
                return f"Interactive command '{command}' completed successfully."
            else:
                return f"Interactive command '{command}' exited with code {result.returncode}."
                
        except KeyboardInterrupt:
            return f"Interactive command '{command}' was interrupted by user."
        except Exception as e:
            return f"Error executing interactive command: {str(e)}"


# ============================================================================
# Python Sandbox Tool
# ============================================================================

class RunPythonSandboxTool(BaseTool):
    """
    Execute Python code in an isolated, resource-limited sandbox.
    
    Use ONLY for:
    - Data visualization/plotting (matplotlib, seaborn)
    - Complex algorithms, ML, scientific computing (numpy, scipy, sklearn)
    - API calls or database operations requiring Python libraries
    - Explicit Python library usage (pandas, requests, etc.)
    
    DON'T use for:
    - File operations (use run_command with cat/grep/sed/awk)
    - Text processing (use run_command with shell pipelines)
    - System queries (use run_command)
    
    Features:
    - Resource limits (CPU, memory, file size)
    - Auto-capture matplotlib plots to artifacts
    - Project file access via SANDBOX_PROJECT env var
    - Optional network isolation
    """
    
    @property
    def name(self) -> str:
        return "run_python_sandbox"
    
    @property
    def description(self) -> str:
        return "Run Python code in an isolated, resource-limited sandbox with data science libs (pandas, numpy, matplotlib). Auto-saves plots to artifacts."
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "run_python_sandbox",
                "description": "Run Python code in an isolated, resource-limited sandbox with data science libs (pandas, numpy, matplotlib). Auto-saves plots to artifacts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Path to an existing .py script (alternative to code parameter)"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (optional, uses SANDBOX_TIMEOUT env default)"
                        },
                        "return_artifacts": {
                            "type": "boolean",
                            "description": "List saved artifacts (default: true)",
                            "default": True
                        }
                    }
                }
            }
        }
    
    @property
    def usage_examples(self) -> List[str]:
        """Critical patterns for sandbox file I/O"""
        return [
            """# Reading project CSV files
import os
import pandas as pd
project_dir = os.environ['SANDBOX_PROJECT']
df = pd.read_csv(os.path.join(project_dir, 'data.csv'))
print(df.head())""",
            
            """# Creating plots (automatically saved to artifacts)
import matplotlib.pyplot as plt
import numpy as np
x = np.linspace(0, 10, 100)
plt.plot(x, np.sin(x))
plt.title('Sine Wave')
# Plot automatically saved to artifacts/plot_1.png""",
            
            """# Writing results back to project
import os
project_dir = os.environ['SANDBOX_PROJECT']
with open(os.path.join(project_dir, 'output.txt'), 'w') as f:
    f.write('Analysis results:\\n')
    f.write('Mean: 42.5\\n')"""
        ]
    
    def _select_python_interpreter(self) -> str:
        """Pick sandbox interpreter with preference for dedicated venv."""
        override = os.getenv("SANDBOX_PYTHON")
        if override:
            expanded = Path(override).expanduser()
            if expanded.exists():
                return str(expanded)
            return str(expanded)
        
        root_dir = Path(__file__).resolve().parent
        if os.name == "nt":
            candidate = root_dir / "sandbox_venv" / "Scripts" / "python.exe"
        else:
            candidate = root_dir / "sandbox_venv" / "bin" / "python"
        if candidate.exists():
            return str(candidate)
        
        return sys.executable
    
    def execute(self, code: str = None, file_path: str = None, timeout: int = None, return_artifacts: bool = True) -> str:
        """
        Execute Python code in sandboxed environment.
        
        Sandbox protections:
        - CPU time limit (SANDBOX_MAX_CPU_SEC, default 20s)
        - Memory limit (SANDBOX_MAX_MEM_MB, default 1024MB)
        - File size limit (SANDBOX_MAX_FSIZE_MB, default 50MB)
        - Optional network isolation (SANDBOX_DISABLE_NETWORK=1)
        - Optional project write protection (SANDBOX_ALLOW_PROJECT_WRITES=0)
        
        Environment:
        - SANDBOX_PROJECT: Path to project directory for file access
        - Matplotlib configured for non-interactive backend
        - Plots automatically saved to artifacts/
        """
        import uuid
        import shutil as _shutil
        import textwrap
        import signal
        
        # Validate inputs
        if not code and not file_path:
            return "Error: Either 'code' or 'file_path' parameter is required"
        
        # Optional POSIX resource limits
        try:
            import resource
        except ImportError:
            resource = None
        
        # Capture original working directory for project file access
        original_cwd = Path(os.getcwd()).resolve()
        
        # Setup isolated run directory
        base_path = Path(os.getenv("SANDBOX_PATH", "./sandbox_runs")).resolve()
        run_id = str(uuid.uuid4())
        run_dir = (base_path / "runs" / run_id).resolve()
        artifacts_dir = run_dir / "artifacts"
        
        try:
            os.makedirs(artifacts_dir, mode=0o700, exist_ok=True)
        except Exception as e:
            return f"Error creating sandbox directory: {str(e)}"
        
        # Create symlink to project directory for convenient access
        project_link = run_dir / "project"
        try:
            project_link.symlink_to(original_cwd, target_is_directory=True)
            project_mount = project_link
        except Exception:
            # Symlink not supported (e.g., Windows without privileges)
            project_mount = original_cwd
        
        # Prepare script
        try:
            if file_path:
                src = Path(file_path)
                if not src.exists():
                    return f"Error: file not found: {file_path}"
                script_path = run_dir / src.name
                _shutil.copy2(src, script_path)
            else:
                script_path = run_dir / "script.py"
                script_path.write_text(code or "", encoding='utf-8')
        except Exception as e:
            return f"Error preparing script: {str(e)}"
        
        # ----------------------------------------------------------------
        # Inject sandbox prologue and epilogue
        # ----------------------------------------------------------------
        
        disable_net = os.getenv("SANDBOX_DISABLE_NETWORK", "0") in ("1", "true", "yes")
        
        # Write protection for project directory
        write_protection = """
# Write protection for project directory
_allow_writes = os.environ.get("SANDBOX_ALLOW_PROJECT_WRITES", "1") in ("1", "true", "yes")
if not _allow_writes:
    _original_open = open
    _project_dir = os.environ.get("SANDBOX_PROJECT", "")
    _real_project = os.path.realpath(_project_dir) if _project_dir else ""
    _work_dir = os.environ.get("SANDBOX_WORKDIR", "")
    _real_workdir = os.path.realpath(_work_dir) if _work_dir else ""
    _run_dir = os.environ.get("SANDBOX_RUN_DIR", "")
    _real_run_dir = os.path.realpath(_run_dir) if _run_dir else ""
    _tmp_dir = os.environ.get("SANDBOX_TMPDIR", "")
    _real_tmp_dir = os.path.realpath(_tmp_dir) if _tmp_dir else ""
    import tempfile
    _system_tmp = os.path.realpath(tempfile.gettempdir()) if tempfile.gettempdir() else ""
    _read_roots = []
    for _candidate in (_real_project, _real_workdir):
        if _candidate and _candidate not in _read_roots:
            _read_roots.append(_candidate)
    _write_allowed = []
    for _candidate in (_real_run_dir, _real_tmp_dir, _system_tmp):
        if _candidate and _candidate not in _write_allowed:
            _write_allowed.append(_candidate)
    
    import builtins
    import pathlib
    import shutil
    
    def _normalize_path(target):
        try:
            return os.path.realpath(os.fspath(target))
        except (TypeError, ValueError, OSError):
            return None
    
    def _is_under(path, root):
        return path == root or path.startswith(root + os.sep)
    
    def _guard_project(target):
        real_path = _normalize_path(target)
        if not real_path:
            return
        for _allowed in _write_allowed:
            if _is_under(real_path, _allowed):
                return
        for _root in _read_roots:
            if _is_under(real_path, _root):
                raise PermissionError(f"Write access to project directory is disabled (SANDBOX_ALLOW_PROJECT_WRITES=0): {target}")
    
    def _resolve_project_path(target):
        if not _read_roots:
            return None
        try:
            path_str = os.fspath(target)
        except TypeError:
            return None
        if os.path.isabs(path_str):
            return None
        for _root in _read_roots:
            candidate = os.path.realpath(os.path.join(_root, path_str))
            if candidate.startswith(_root + os.sep) or candidate == _root:
                if os.path.exists(candidate):
                    return candidate
        return None
    
    def _protected_open(file, mode='r', *args, **kwargs):
        if any(flag in mode for flag in ('w', 'a', 'x', '+')):
            _guard_project(file)
            return _original_open(file, mode, *args, **kwargs)
        try:
            return _original_open(file, mode, *args, **kwargs)
        except FileNotFoundError:
            fallback = _resolve_project_path(file)
            if fallback:
                return _original_open(fallback, mode, *args, **kwargs)
            raise
    
    builtins.open = _protected_open
    
    def _wrap_os_single(name):
        original = getattr(os, name, None)
        if original is None:
            return
        def wrapped(path, *args, **kwargs):
            _guard_project(path)
            return original(path, *args, **kwargs)
        setattr(os, name, wrapped)
    
    def _wrap_os_dual(name):
        original = getattr(os, name, None)
        if original is None:
            return
        def wrapped(src, dst, *args, **kwargs):
            _guard_project(src)
            _guard_project(dst)
            return original(src, dst, *args, **kwargs)
        setattr(os, name, wrapped)
    
    for _func in ("remove", "unlink", "rmdir", "mkdir", "makedirs"):
        _wrap_os_single(_func)
    for _func in ("rename", "replace"):
        _wrap_os_dual(_func)
    
    def _wrap_shutil_single(name):
        original = getattr(shutil, name, None)
        if original is None:
            return
        def wrapped(path, *args, **kwargs):
            _guard_project(path)
            return original(path, *args, **kwargs)
        setattr(shutil, name, wrapped)
    
    def _wrap_shutil_copylike(name):
        original = getattr(shutil, name, None)
        if original is None:
            return
        def wrapped(src, dst, *args, **kwargs):
            _guard_project(dst)
            return original(src, dst, *args, **kwargs)
        setattr(shutil, name, wrapped)
    
    def _wrap_shutil_move(name):
        original = getattr(shutil, name, None)
        if original is None:
            return
        def wrapped(src, dst, *args, **kwargs):
            _guard_project(src)
            _guard_project(dst)
            return original(src, dst, *args, **kwargs)
        setattr(shutil, name, wrapped)
    
    for _func in ("copy", "copy2", "copytree"):
        _wrap_shutil_copylike(_func)
    _wrap_shutil_single("rmtree")
    _wrap_shutil_move("move")
    
    _Path = pathlib.Path
    
    def _wrap_path_single(method_name):
        original = getattr(_Path, method_name, None)
        if original is None:
            return
        def wrapped(self, *args, **kwargs):
            _guard_project(self)
            return original(self, *args, **kwargs)
        setattr(_Path, method_name, wrapped)
    
    def _wrap_path_target(method_name):
        original = getattr(_Path, method_name, None)
        if original is None:
            return
        def wrapped(self, target, *args, **kwargs):
            _guard_project(self)
            _guard_project(target)
            return original(self, target, *args, **kwargs)
        setattr(_Path, method_name, wrapped)
    
    for _method in ("unlink", "rmdir", "mkdir"):
        _wrap_path_single(_method)
    for _method in ("rename", "replace"):
        _wrap_path_target(_method)
"""
        
        prologue = """
import os
import sys
{write_protection}
# Matplotlib: configure non-interactive backend
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    def _no_show(*args, **kwargs): pass
    plt.show = _no_show
except ImportError:
    pass  # matplotlib not available
# Optional network isolation
{disable_net}
""".format(
            disable_net=textwrap.dedent("""
try:
    import socket
    class _BlockedSocket(socket.socket):
        def __init__(self, *a, **k): raise RuntimeError("Network disabled in sandbox")
    socket.socket = _BlockedSocket
    socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Network disabled"))
except Exception: pass
""") if disable_net else "",
            write_protection=write_protection
        )

        # Auto-save matplotlib figures to artifacts
        epilogue = """
# Auto-save matplotlib figures
try:
    import matplotlib.pyplot as _plt
    import os
    artifacts_path = os.path.join(os.getcwd(), "artifacts")
    os.makedirs(artifacts_path, exist_ok=True)
    for i, num in enumerate(_plt.get_fignums(), start=1):
        _plt.figure(num).savefig(os.path.join(artifacts_path, f"plot_{i}.png"), dpi=150, bbox_inches="tight")
except ImportError:
    pass  # matplotlib not available
except Exception as _e:
    import sys
    print(f"[sandbox] plot save error: {_e}", file=sys.stderr)
"""

        # Inject prologue and epilogue into script
        try:
            original = script_path.read_text(encoding='utf-8')
            script_path.write_text(prologue + "\n" + original + "\n" + epilogue, encoding='utf-8')
        except Exception as e:
            return f"Error injecting sandbox wrappers: {str(e)}"
        
        # ----------------------------------------------------------------
        # Configure execution environment
        # ----------------------------------------------------------------
        
        # Python binary
        py = self._select_python_interpreter()
        args = [py, "-I", "-B", script_path.name]
        
        # Create isolated tmp directory
        tmp_dir = run_dir / "tmp"
        try:
            os.makedirs(tmp_dir, mode=0o700, exist_ok=True)
        except Exception:
            pass
        
        workdir_path = Path(_get_working_dir_path()).resolve()
        workdir_env = str(workdir_path) if workdir_path.exists() else ""
        
        # Minimal environment
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(run_dir),
            "PYTHONNOUSERSITE": "1",
            "PYTHONHASHSEED": "0",
            "MPLBACKEND": "Agg",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "SANDBOX_ORIGINAL_CWD": str(original_cwd),
            "SANDBOX_PROJECT": str(project_mount),  # Access project files via this path
            "SANDBOX_RUN_DIR": str(run_dir),
            "SANDBOX_ALLOW_PROJECT_WRITES": os.getenv("SANDBOX_ALLOW_PROJECT_WRITES", "0"),  # Default: write-protected
            "SANDBOX_WORKDIR": workdir_env,
            "SANDBOX_TMPDIR": str(tmp_dir),
            "TMPDIR": str(tmp_dir),
            "MPLCONFIGDIR": str(run_dir / ".mplconfig"),
        }
        # Preserve locale settings
        env.update({k: v for k, v in os.environ.items() if k in ("LC_ALL", "LANG")})
        
        # Resource limits (configurable via environment)
        max_cpu = int(os.getenv("SANDBOX_MAX_CPU_SEC", "20"))
        max_mem_mb = int(os.getenv("SANDBOX_MAX_MEM_MB", "1024"))
        max_fsize_mb = int(os.getenv("SANDBOX_MAX_FSIZE_MB", "50"))
        if timeout is None:
            timeout = int(os.getenv("SANDBOX_TIMEOUT", str(max_cpu)))
        
        def _apply_limits():
            """Apply POSIX resource limits in subprocess"""
            try:
                os.setsid()  # Create new process group for clean termination
                os.umask(0o077)  # Tighten file permissions (owner-only)
                if resource:
                    # CPU time limit
                    resource.setrlimit(resource.RLIMIT_CPU, (max_cpu, max_cpu))
                    # Memory limit
                    if hasattr(resource, "RLIMIT_AS"):
                        resource.setrlimit(resource.RLIMIT_AS, (max_mem_mb * 1024 * 1024, max_mem_mb * 1024 * 1024))
                    elif hasattr(resource, "RLIMIT_DATA"):
                        resource.setrlimit(resource.RLIMIT_DATA, (max_mem_mb * 1024 * 1024, max_mem_mb * 1024 * 1024))
                    # File size limit
                    resource.setrlimit(resource.RLIMIT_FSIZE, (max_fsize_mb * 1024 * 1024, max_fsize_mb * 1024 * 1024))
                    # File descriptor limit
                    if hasattr(resource, "RLIMIT_NOFILE"):
                        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
                    # Note: RLIMIT_NPROC disabled to allow matplotlib threading
            except Exception:
                pass  # Resource limits not critical
        
        # ----------------------------------------------------------------
        # Execute sandboxed code
        # ----------------------------------------------------------------
        
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(run_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                preexec_fn=_apply_limits if os.name == "posix" else None
            )
        except Exception as e:
            return f"Error starting sandbox process: {str(e)}"
        
        # Wait for completion with timeout
        timed_out = False
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Kill process group to clean up any child processes
            try:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except Exception:
                pass
            out, err = proc.communicate()
        except Exception as e:
            return f"Error executing sandbox: {str(e)}"
        
        # ----------------------------------------------------------------
        # Collect artifacts (plots, exports)
        # ----------------------------------------------------------------
        
        artifacts = []
        if return_artifacts and artifacts_dir.exists():
            for p in sorted(artifacts_dir.glob("*")):
                if p.suffix.lower() in (".png", ".svg", ".html", ".csv", ".json"):
                    try:
                        artifacts.append({"path": str(p), "size": p.stat().st_size})
                    except Exception:
                        pass
        
        # Save execution manifest
        manifest = {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "exit_code": None if timed_out else proc.returncode,
            "timed_out": timed_out,
            "artifacts": artifacts,
        }
        
        try:
            (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        except Exception:
            pass  # Non-critical
        
        # ----------------------------------------------------------------
        # Format result for agent
        # ----------------------------------------------------------------
        
        parts = []
        parts.append(f"[python-sandbox] run_id={run_id}")
        parts.append(f"Interpreter: {py}")
        parts.append(f"Project Mount: {project_mount}")
        parts.append(f"Timeout: {timeout}s (timed_out={timed_out})")
        parts.append(f"Exit code: {manifest['exit_code']}")
        
        if out:
            parts.append("Stdout:\n" + out)
        if err:
            parts.append("Stderr:\n" + err)
        if artifacts:
            parts.append("Artifacts:")
            for a in artifacts:
                parts.append(f"- {a['path']} ({a['size']} bytes)")
        
        parts.append(f"Manifest: {run_dir / 'manifest.json'}")
        
        # Cleanup old runs to prevent unbounded disk usage
        try:
            max_runs = int(os.getenv("SANDBOX_MAX_RUNS", "10"))
        except ValueError:
            max_runs = 10
        self._cleanup_old_runs(base_path / "runs", max_runs)
        
        return "\n".join(parts)
    
    def _cleanup_old_runs(self, runs_root: Path, keep: int):
        """Remove old sandbox run directories, keeping most recent N."""
        if keep <= 0 or not runs_root.exists():
            return
        try:
            run_dirs = sorted(
                [p for p in runs_root.iterdir() if p.is_dir()],
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            for stale_dir in run_dirs[keep:]:
                shutil.rmtree(stale_dir, ignore_errors=True)
        except Exception:
            # Cleanup best-effort; ignore failures to avoid breaking sandbox output
            pass


# ============================================================================
# History SQL Tool
# ============================================================================

class HistorySQLTool(BaseTool):
    # v1.3 legacy tool - only register if USE_EVENT_MEMORY=1
    AUTO_REGISTER = _USE_EVENT_MEMORY
    """
    Run guarded SELECT/INSERT/UPDATE statements against the history DB.
    """

    def __init__(self):
        self._executor_factory = get_history_sql_executor

    @property
    def name(self) -> str:
        return "history_sql"

    @property
    def description(self) -> str:
        return (
            "Primary interface for the history DB: run parameterized SELECT/INSERT/UPDATE statements "
            "to recall or store memories. DELETE/DROP and other destructive verbs are blocked."
        )

    @property
    def usage_examples(self) -> List[str]:
        return [
            "history_sql(statement=\"SELECT <columns> FROM events WHERE <conditions> ORDER BY <field> DESC\", max_rows=<int>)",
            "history_sql(statement=\"INSERT INTO agent_memories(session_id, topic, content) VALUES('<session>', '<topic>', '<content>')\")",
            "history_sql(statement=\"UPDATE agent_memories SET tags = '<tags>' WHERE id = <row_id>\")",
        ]

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "history_sql",
                "description": (
                    "Query or append to the long-term history database with SELECT/INSERT/UPDATE statements. "
                    "Use parameter binding instead of string concatenation. DELETE/DROP are forbidden."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "statement": {
                            "type": "string",
                            "description": "SQL statement (single SELECT/INSERT/UPDATE). Omit trailing semicolons."
                        },
                        "params": {
                            "type": "array",
                            "items": {"type": ["string", "number", "boolean", "null"]},
                            "description": "Optional positional parameters bound in order (use ? placeholders)."
                        },
                        "named_params": {
                            "type": "object",
                            "additionalProperties": {"type": ["string", "number", "boolean", "null"]},
                            "description": "Optional named parameters (use :name placeholders). Cannot combine with params."
                        },
                        "max_rows": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "description": "Row cap for SELECT queries (default 50)."
                        }
                    },
                    "required": ["statement"],
                    "additionalProperties": False
                }
            }
        }

    def execute(
        self,
        statement: str,
        params: Optional[List[Any]] = None,
        named_params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
    ) -> str:
        if params and named_params:
            return "Provide either positional params or named_params, not both."
        bindings: Optional[Any] = named_params if named_params is not None else params
        try:
            executor = self._executor_factory()
            result = executor.execute(statement, params=bindings, max_rows=max_rows)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except HistorySQLExecutionError as exc:
            return f"History SQL error: {exc}"
        except Exception as exc:
            return f"Unexpected history SQL error: {exc}"


class HistorySchemaTool(BaseTool):
    # v1.3 legacy tool - only register if USE_EVENT_MEMORY=1
    AUTO_REGISTER = _USE_EVENT_MEMORY
    """Expose history DB schema metadata (tables + columns)."""

    def __init__(self):
        self._executor_factory = get_history_sql_executor

    @property
    def name(self) -> str:
        return "history_schema"

    @property
    def description(self) -> str:
        return "Inspect the history database schema (list tables or describe a table's columns)."

    @property
    def usage_examples(self) -> List[str]:
        return [
            "history_schema()",
            "history_schema(action=\"describe_table\", table=\"events\")",
        ]

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "history_schema",
                "description": (
                    "Inspect history DB schema: list tables or describe columns before issuing history_sql queries."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list_tables", "describe_table"],
                            "description": "list_tables (default) returns table names; describe_table returns column metadata.",
                        },
                        "table": {
                            "type": "string",
                            "description": "Table name to describe when action is describe_table.",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        }

    def execute(self, action: str = "list_tables", table: Optional[str] = None) -> str:
        executor = self._executor_factory()
        try:
            if action == "describe_table":
                if not table:
                    raise HistorySQLExecutionError("table is required for describe_table")
                columns = executor.describe_table(table)
                return json.dumps({"table": table, "columns": columns}, ensure_ascii=False, indent=2)
            tables = executor.list_tables()
            return json.dumps({"tables": tables}, ensure_ascii=False, indent=2)
        except HistorySQLExecutionError as exc:
            return f"History schema error: {exc}"
        except Exception as exc:
            return f"Unexpected history schema error: {exc}"


# ============================================================================
# Context Tool
# ============================================================================

class GetContextTool(BaseTool):
    """
    Get comprehensive agent execution context.
    
    Returns JSON with:
    - Execution state: working_dir, shell_cwd, recent_writes (backward compatible)
    - Session info: id, start_time, duration, interaction counts
    - Tool history: Recent tool calls with timestamps, exit codes, success status
    - Recent errors: Last 3 errors with context
    - Available tools: List of all available tool names
    - Activity: Last command exit code
    
    Use to: Check state, debug failures, understand session context without redundant commands
    """
    
    @property
    def name(self) -> str:
        return "get_context"
    
    @property
    def description(self) -> str:
        return "Get comprehensive execution context: session info, tool history, errors, available tools, and execution state"
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_context",
                "description": "Get agent execution context including session history, tool calls, errors, available tools, and execution state. Use for debugging, understanding session state, or checking recent results. Prefer this over redundant pwd/ls/git status commands.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False
                }
            }
        }
    
    def execute(self) -> str:
        """Return comprehensive execution context as JSON"""
        working_dir = _get_working_dir_path()
        
        # Get shell cwd from the run_command tool instance if available
        shell_cwd = None
        shell_instance = None
        try:
            tools_dict = globals().get("TOOLS", {})
            if "run_command" in tools_dict:
                rc_tool = tools_dict["run_command"]
                if hasattr(rc_tool, "shell") and rc_tool.shell:
                    shell_instance = rc_tool.shell
                    shell_cwd = shell_instance.get_current_dir()
        except Exception:
            pass
        if shell_cwd is not None and not isinstance(shell_cwd, str):
            shell_cwd = str(shell_cwd)
        
        # Get git repository context
        git_context = {}
        try:
            from utils.system_info import get_git_info
            git_info = get_git_info()
            if git_info:
                git_context = {
                    "in_repo": True,
                    "branch": git_info.get("branch"),
                    "repo_name": git_info.get("repo_name"),
                    "uncommitted_changes": int(git_info.get("uncommitted_changes", 0)) if git_info.get("uncommitted_changes") else 0
                }
            else:
                git_context = {"in_repo": False}
        except Exception:
            git_context = {"in_repo": False}
        
        # Get available interpreters
        interpreters = {}
        for interpreter in ["python", "python3", "node", "ruby", "bash", "perl"]:
            path = shutil.which(interpreter)
            interpreters[interpreter] = path
        
        requested_isolation = os.getenv("SANDBOX_ENABLE_ISOLATION") == "1"
        isolation_active = False
        isolation_warning = None
        isolation_rootfs = os.getenv("SANDBOX_ROOTFS_SHA256")
        if shell_instance:
            isolation_active = bool(getattr(shell_instance, "isolation_enabled", False))
            isolation_rootfs = getattr(shell_instance, "rootfs_sha256", isolation_rootfs)
            if requested_isolation and not isolation_active:
                isolation_warning = getattr(shell_instance, "isolation_warning", None) or \
                    "Namespace isolation requested but not active."
        elif requested_isolation:
            isolation_warning = "Namespace isolation requested but shell not initialized."
        if isolation_rootfs is not None and not isinstance(isolation_rootfs, str):
            isolation_rootfs = str(isolation_rootfs)
        if isolation_warning is not None and not isinstance(isolation_warning, str):
            isolation_warning = str(isolation_warning)
        
        isolation_config = {
            "requested": requested_isolation,
            "enabled": isolation_active,
            "active": isolation_active,
            "rootfs_sha256": isolation_rootfs
        }
        if isolation_warning:
            isolation_config["warning"] = isolation_warning
            isolation_config["status"] = "degraded"
        else:
            isolation_config["status"] = "active" if isolation_active else "disabled"
        
        # Build comprehensive context
        context = {
            # Backward compatible fields (existing)
            "working_dir": working_dir,
            "shell_cwd": shell_cwd,
            "recent_writes": list(_RECENT_WRITES),
            
            # Session information (new)
            "session": _SESSION_STATE.get_session_info(),
            
            # Tool execution history (new)
            "tool_history": _SESSION_STATE.get_tool_history(),
            
            # Available tools (new)
            "available_tools": {
                "all": sorted(list(TOOLS.keys())),
                "interactive": ["run_interactive"],
                "sandboxed": ["run_python_sandbox"]
            },
            
            # Recent errors (new)
            "recent_errors": _SESSION_STATE.get_recent_errors(),
            
            # Configuration state (new)
            "configuration": {
                "sandbox": {
                    "enabled": bool(os.getenv("SANDBOX_PYTHON")),
                    "timeout_seconds": int(os.getenv("SANDBOX_TIMEOUT", "30")),
                    "max_memory_mb": int(os.getenv("SANDBOX_MAX_MEM_MB", "1024")),
                    "max_cpu_seconds": int(os.getenv("SANDBOX_MAX_CPU_SEC", "20")),
                    "network_disabled": os.getenv("SANDBOX_DISABLE_NETWORK", "1") in ("1", "true", "yes"),
                    "write_protected": os.getenv("SANDBOX_ALLOW_PROJECT_WRITES", "0") not in ("1", "true", "yes")
                },
                "isolation": isolation_config
            },
            
            # Repository context (new)
            "repository": git_context,
            
            # Capabilities (new)
            "capabilities": {
                "interpreters_available": interpreters
            },
            
            # Activity tracking (new)
            "activity": {
                "last_command_exit_code": _SESSION_STATE.last_exit_code
            }
        }

        context["filesystem"] = {
            "workspace_root": working_dir,
            "workspace_hint": os.path.join(working_dir, "workspace"),
            "recent_activity": list(_RECENT_FILE_EVENTS)
        }
        
        event_summary = summarize_event_log(_SESSION_STATE.session_id)
        if event_summary:
            context["event_memory"] = event_summary

        store = _get_fs_store()
        if store and _SESSION_STATE.session_id:
            try:
                persisted_snapshot = store.get_latest_snapshot(_SESSION_STATE.session_id)
                persisted_events = store.get_recent_events(_SESSION_STATE.session_id, limit=5)
                if persisted_snapshot:
                    context["filesystem"]["persisted_snapshot"] = persisted_snapshot
                if persisted_events:
                    context["filesystem"]["persisted_events"] = persisted_events
            except Exception:
                pass
        
        return json.dumps(context, indent=2)


# ============================================================================
# Filesystem snapshot tool
# ============================================================================

class FilesystemSnapshotTool(BaseTool):
    # v1.3 legacy tool - only register if USE_EVENT_MEMORY=1
    AUTO_REGISTER = _USE_EVENT_MEMORY
    """
    Fetch the latest persisted filesystem snapshot plus recent file events.
    """

    @property
    def name(self) -> str:
        return "filesystem_snapshot"

    @property
    def description(self) -> str:
        return "Return the latest persisted filesystem snapshot plus recent file events for the active session."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "filesystem_snapshot",
                "description": "Return the latest filesystem snapshot and recent file events captured from shell activity.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of recent file events to include (default 15).",
                            "minimum": 1,
                            "maximum": 50
                        }
                    },
                    "additionalProperties": False
                }
            }
        }

    def execute(self, limit: int = 15) -> str:
        store = _get_fs_store()
        if not store or not _SESSION_STATE.session_id:
            fallback = list(_RECENT_FILE_EVENTS)[-limit:]
            payload = {
                "session_id": _SESSION_STATE.session_id,
                "snapshot": None,
                "recent_events": fallback
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 15
        limit = max(1, min(limit, 50))
        snapshot = store.get_latest_snapshot(_SESSION_STATE.session_id)
        events = store.get_recent_events(_SESSION_STATE.session_id, limit=limit)
        if not events:
            events = list(_RECENT_FILE_EVENTS)[-limit:]
        payload = {
            "session_id": _SESSION_STATE.session_id,
            "snapshot": snapshot,
            "recent_events": events
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


# ============================================================================
# Search DB Tool (Context v2 - Institutional Memory)
# ============================================================================

class SearchDBTool(BaseTool):
    """
    FAST institutional memory search via FTS5.
    
    Searches orchestrator database for:
    - chat_history: Previous conversations (user queries + agent responses)
    - step_outputs: Past tool executions (commands, outputs, results)
    - interactions: LLM interaction logs (all agent roles)
    - intention_cache: Cached query→tool mappings
    
    Performance: <50ms typical, uses SQLite FTS5 indexes.
    Safety: Enum-based targets, no SQL injection possible.
    """
    
    @property
    def name(self) -> str:
        return "search_db"
    
    @property
    def description(self) -> str:
        return "Search institutional memory (chat history, tool executions, LLM logs) via FTS5. Fast (<50ms), safe enum targets."
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["chat_history", "step_outputs", "interactions", "intention_cache"],
                        "description": "Which memory table to search. chat_history=conversations, step_outputs=tool executions, interactions=LLM logs, intention_cache=cached queries"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (natural language). Use quotes for exact phrases: '\"exact match\"'. Supports wildcards: 'term*', boolean: 'term1 AND term2'"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10, max 50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional: Filter results to specific session (default: all sessions)"
                    },
                    "tool_filter": {
                        "type": "string",
                        "description": "Optional: For step_outputs only - filter by tool name (e.g., 'run_command')"
                    },
                    "role_filter": {
                        "type": "string",
                        "enum": ["A", "B", "C"],
                        "description": "Optional: For interactions only - filter by agent role"
                    },
                    "success_only": {
                        "type": "boolean",
                        "description": "Optional: For step_outputs only - return only successful executions (default false)",
                        "default": False
                    }
                },
                "required": ["target", "query"]
            }
        }
    
    def execute(
        self,
        target: str,
        query: str,
        limit: int = 10,
        session_id: Optional[str] = None,
        tool_filter: Optional[str] = None,
        role_filter: Optional[str] = None,
        success_only: bool = False
    ) -> str:
        """
        Execute institutional memory search.
        
        Returns:
            Formatted search results with metadata (JSON or human-readable)
        """
        # Import Memory here to avoid circular dependencies
        from memory.api import Memory
        
        # Validate inputs
        valid_targets = ["chat_history", "step_outputs", "interactions", "intention_cache"]
        if target not in valid_targets:
            return json.dumps({
                "success": False,
                "error": f"Invalid target '{target}'. Must be one of: {', '.join(valid_targets)}"
            }, indent=2)
        
        if not query or not query.strip():
            return json.dumps({
                "success": False,
                "error": "Query cannot be empty"
            }, indent=2)
        
        # Enforce limit bounds
        limit = max(1, min(50, limit))
        
        try:
            # Initialize memory (reuses existing connection if available)
            memory = Memory()
            
            # Route to appropriate search method
            start_time = time.time()
            
            if target == "chat_history":
                results = memory.search_chat_history(
                    query=query,
                    session_id=session_id,
                    limit=limit
                )
                formatted = self._format_chat_results(results)
            
            elif target == "step_outputs":
                results = memory.search_step_outputs(
                    query=query,
                    session_id=session_id,
                    tool_name=tool_filter,
                    success_only=success_only,
                    limit=limit
                )
                formatted = self._format_step_results(results)
            
            elif target == "interactions":
                results = memory.search_interactions(
                    query=query,
                    role=role_filter,
                    session_id=session_id,
                    limit=limit
                )
                formatted = self._format_interaction_results(results)
            
            elif target == "intention_cache":
                # Direct FTS5 query for intention cache
                results = self._search_intention_cache(memory, query, limit)
                formatted = self._format_intention_results(results)
            
            else:
                return json.dumps({"success": False, "error": f"Unknown target: {target}"}, indent=2)
            
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            # Return success response
            return json.dumps({
                "success": True,
                "target": target,
                "query": query,
                "result_count": len(results),
                "latency_ms": elapsed_ms,
                "results": formatted
            }, indent=2)
        
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Search failed: {str(e)}"
            }, indent=2)
    
    def _search_intention_cache(self, memory: Any, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search intention_cache table using FTS5."""
        sanitized = memory._sanitize_fts5_query(query)
        
        sql = """
            SELECT 
                ic.id,
                ic.user_query_text,
                ic.normalized_intent,
                ic.tool_name,
                ic.tool_args_json,
                ic.usage_count,
                ic.last_used_at,
                fts.rank
            FROM intention_cache_fts fts
            JOIN intention_cache ic ON ic.id = fts.rowid
            WHERE intention_cache_fts MATCH ?
            ORDER BY fts.rank, ic.usage_count DESC
            LIMIT ?
        """
        
        cursor = memory.conn.execute(sql, (sanitized, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "user_query": row[1],
                "intent": row[2],
                "tool_name": row[3],
                "tool_args": json.loads(row[4]) if row[4] else {},
                "usage_count": row[5],
                "last_used": row[6],
                "rank": row[7]
            })
        
        return results
    
    def _format_chat_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format chat_history results for agent consumption."""
        formatted = []
        for r in results:
            formatted.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "timestamp": r["timestamp"],
                "user_query": r["user_query"],
                "agent_response": r["agent_response"][:200] + "..." if len(r["agent_response"]) > 200 else r["agent_response"],
                "relevance_rank": r["rank"]
            })
        return formatted
    
    def _format_step_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format step_outputs results for agent consumption."""
        formatted = []
        for r in results:
            formatted.append({
                "id": r["id"],
                "cycle_id": r["cycle_id"],
                "step_id": r["step_id"],
                "tool_name": r["tool_name"],
                "tool_args": r["tool_args"],
                "success": r["success"],
                "exit_code": r.get("exit_code"),
                "output_preview": r["output_preview"][:150] + "..." if r["output_preview"] and len(r["output_preview"]) > 150 else r["output_preview"],
                "created_at": r["created_at"],
                "relevance_rank": r["rank"]
            })
        return formatted
    
    def _format_interaction_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format interactions results for agent consumption."""
        formatted = []
        for r in results:
            formatted.append({
                "id": r["id"],
                "cycle_id": r["cycle_id"],
                "role": r["role"],
                "prompt_preview": r["prompt_preview"][:100] + "..." if r["prompt_preview"] and len(r["prompt_preview"]) > 100 else r["prompt_preview"],
                "response_preview": r["response_preview"][:100] + "..." if r["response_preview"] and len(r["response_preview"]) > 100 else r["response_preview"],
                "latency_ms": r["latency_ms"],
                "created_at": r["created_at"],
                "relevance_rank": r["rank"]
            })
        return formatted
    
    def _format_intention_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format intention_cache results for agent consumption."""
        formatted = []
        for r in results:
            formatted.append({
                "id": r["id"],
                "user_query": r["user_query"],
                "normalized_intent": r["intent"],
                "tool_name": r["tool_name"],
                "tool_args": r["tool_args"],
                "usage_count": r["usage_count"],
                "last_used": r["last_used"],
                "relevance_rank": r["rank"]
            })
        return formatted


# ============================================================================
# Tool Registry - Automatic Discovery
# ============================================================================

def _iter_tool_classes(module):
    """
    Discover all BaseTool subclasses defined in this module.
    
    Auto-registers all concrete tool classes unless AUTO_REGISTER=False.
    """
    for _, obj in inspect.getmembers(module, inspect.isclass):
        # Only classes defined in this file
        if obj.__module__ != module.__name__:
            continue
        # Skip BaseTool itself and non-subclasses
        if not issubclass(obj, BaseTool) or obj is BaseTool:
            continue
        # Skip abstract classes
        if inspect.isabstract(obj):
            continue
        # Allow opt-out via class attribute
        if not getattr(obj, "AUTO_REGISTER", True):
            continue
        yield obj


def _instantiate_tool(cls):
    """
    Instantiate a tool class.
    
    Raises TypeError if class doesn't have a zero-arg constructor.
    """
    try:
        return cls()
    except TypeError as e:
        raise TypeError(f"Auto-registration requires a no-arg constructor: {cls.__name__}: {e}")


def _build_tools():
    """
    Build the TOOLS dictionary from discovered tool classes.
    
    Returns:
        Dict mapping tool names to tool instances
    """
    instances = [_instantiate_tool(cls) for cls in _iter_tool_classes(sys.modules[__name__])]
    # Sort by tool name for deterministic order
    instances.sort(key=lambda t: t.name)
    tools = {}
    for inst in instances:
        if inst.name in tools:
            raise ValueError(f"Duplicate tool name detected: {inst.name}")
        tools[inst.name] = inst
    return tools


# Global tool registry - automatically populated
TOOLS: Dict[str, BaseTool] = _build_tools()


def get_tool_schemas() -> List[Dict[str, Any]]:
    """
    Get JSON schemas for all registered tools.
    
    Used by the agent to provide tool definitions to the LLM.
    """
    return [tool.schema for tool in TOOLS.values()]
