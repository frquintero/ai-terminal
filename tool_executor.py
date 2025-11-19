"""
ToolExecutor - Reusable tool execution wrapper for v2.0 Orchestrator

Extracted from agent.py for use in Agent B (Executor) and Router cached execution.
Handles tool validation, execution, error handling, and logging.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

try:
    import jsonschema
except ImportError:
    jsonschema = None

from tools import TOOLS


class ToolExecutor:
    """
    Reusable tool executor for calling registered tools.
    
    Features:
    - Tool validation (unknown tools, malformed args)
    - Execution with error handling
    - Exit code tracking
    - Optional logging to Memory
    - Result truncation for large outputs
    
    Usage:
        executor = ToolExecutor(memory=mem)
        result = executor.execute("run_command", {"command": "ls -la"}, cycle_id=cycle_id)
    """
    
    MAX_OUTPUT_PREVIEW = 1000  # Characters to store in step_outputs
    
    def __init__(self, strict_mode: bool = False, **_unused):
        """
        Initialize tool executor.
        
        Args:
            strict_mode: If True, enforce explicit stdout/stderr in tool returns.
                         If False (default), fallback to JSON dumping dicts.
        
        Note: ToolExecutor does NOT access memory directly.
        The orchestrator is responsible for persisting all execution results.
        ToolExecutor only returns structured data.
        """
        self.strict_mode = strict_mode
    
    def execute(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        cycle_id: Optional[str] = None,
        step_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a tool by name with arguments.
        
        Args:
            tool_name: Tool to execute
            tool_args: Tool arguments dict
            cycle_id: Cycle ID for logging
            step_id: Step number in plan (for PLANNER route)
        
        Returns a dict containing:
            - success: bool
            - result: str (primary text for backward compatibility)
            - stdout / stderr: normalized strings (if provided)
            - raw_stdout / raw_stderr: untrimmed strings for archival
            - exit_code: Optional[int]
            - output_preview: Truncated text for memory snapshots
            - error: Optional[str]
        """
        # Validate tool exists
        tool = TOOLS.get(tool_name)
        if not tool:
            error_msg = f"Unknown tool: {tool_name}"
            return {
                "success": False,
                "result": error_msg,
                "stdout": None,
                "stderr": error_msg,
                "raw_stdout": None,
                "raw_stderr": error_msg,
                "output_preview": error_msg[:self.MAX_OUTPUT_PREVIEW],
                "exit_code": None,
                "error": error_msg
            }
        
        # Validate tool arguments against schema
        validation_error = self._validate_tool_args(tool, tool_args)
        if validation_error:
            return {
                "success": False,
                "result": validation_error,
                "stdout": None,
                "stderr": validation_error,
                "raw_stdout": None,
                "raw_stderr": validation_error,
                "output_preview": validation_error[:self.MAX_OUTPUT_PREVIEW],
                "exit_code": None,
                "error": validation_error
            }
        
        # Execute tool
        try:
            result = tool.execute(**tool_args)
            normalized = self._normalize_tool_result(tool_name, result)
            
            # Extract exit code if available
            # Note: Some tools set exit code in _SESSION_STATE, but we'll track it separately
            exit_code = self._extract_exit_code(tool_name, result)
            preview = self._build_preview(normalized["stdout"], normalized["stderr"])
            primary_text = normalized["stdout"] if normalized["stdout"] is not None else (
                normalized["stderr"] or ""
            )
            agent_message = None
            events = None
            if isinstance(result, dict):
                agent_message = result.get("agent_message")
                events = result.get("events")
            
            return {
                "success": True,
                "result": primary_text,
                "stdout": normalized["stdout"],
                "stderr": normalized["stderr"],
                "raw_stdout": normalized["raw_stdout"],
                "raw_stderr": normalized["raw_stderr"],
                "exit_code": exit_code,
                "output_preview": preview,
                "data": result if isinstance(result, (dict, list)) else None,
                "error": None,
                "agent_message": agent_message,
                "events": events
            }
        
        except Exception as e:
            error_msg = f"Tool '{tool_name}' raised error: {e}"
            return {
                "success": False,
                "result": error_msg,
                "stdout": None,
                "stderr": error_msg,
                "raw_stdout": None,
                "raw_stderr": error_msg,
                "output_preview": error_msg[:self.MAX_OUTPUT_PREVIEW],
                "exit_code": None,
                "error": str(e)
            }
    
    def execute_batch(
        self,
        tool_calls: List[Dict[str, Any]],
        cycle_id: Optional[str] = None,
        step_id_offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple tool calls in sequence.
        
        Args:
            tool_calls: List of {"tool": str, "args": dict}
            cycle_id: Cycle ID for logging
            step_id_offset: Starting step ID
        
        Returns:
            List of execution results
        """
        results = []
        for idx, call in enumerate(tool_calls):
            tool_name = call.get("tool")
            tool_args = call.get("args", {})
            step_id = step_id_offset + idx
            
            result = self.execute(
                tool_name=tool_name,
                tool_args=tool_args,
                cycle_id=cycle_id,
                step_id=step_id
            )
            results.append(result)
        
        return results
    
    def validate_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate tool and arguments before execution.
        
        Args:
            tool_name: Tool name
            tool_args: Tool arguments
        
        Returns:
            (valid: bool, error_message: Optional[str])
        """
        # Check tool exists
        if tool_name not in TOOLS:
            return False, f"Unknown tool: {tool_name}"
        
        # Check args is dict
        if not isinstance(tool_args, dict):
            return False, f"Tool arguments must be dict, got {type(tool_args)}"
        
        # Schema validation (if jsonschema available)
        error = self._validate_tool_args(TOOLS[tool_name], tool_args)
        if error:
            return False, error
        
        return True, None
    
    def _validate_tool_args(self, tool, tool_args: Dict[str, Any]) -> Optional[str]:
        """
        Validate tool arguments against tool schema using jsonschema.
        
        Args:
            tool: Tool object with .schema property
            tool_args: Arguments to validate
        
        Returns:
            Error message if invalid, None if valid
        """
        if not jsonschema:
            # jsonschema not available, skip validation (but allow execution)
            return None
        
        try:
            # Get tool schema
            tool_schema = tool.schema
            if not tool_schema or 'function' not in tool_schema:
                # No schema available, allow execution
                return None
            
            params_schema = tool_schema.get('function', {}).get('parameters', {})
            if not params_schema:
                # No parameters schema, allow execution
                return None
            
            # Validate arguments against schema
            jsonschema.validate(tool_args, params_schema)
            return None  # Valid
        
        except jsonschema.ValidationError as e:
            return f"Invalid tool arguments: {e.message}"
        except Exception as e:
            # In strict mode, schema errors are fatal
            if self.strict_mode:
                return f"Tool schema error for {tool.name}: {str(e)}"
            return None
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return sorted(TOOLS.keys())
    
    def _extract_exit_code(self, tool_name: str, result: Any) -> Optional[int]:
        """
        Extract exit code from tool result if available.
        
        Args:
            tool_name: Tool name
            result: Tool result
        
        Returns:
            Exit code or None
        """
        if isinstance(result, dict):
            exit_code = result.get("exit_code")
            if isinstance(exit_code, int):
                return exit_code
        return None

    def _normalize_tool_result(self, tool_name: str, value: Any) -> Dict[str, Optional[str]]:
        """
        Normalize tool return value into stdout/stderr/raw fields.
        
        In strict_mode, raises ValueError if tool returns a dict without explicit
        stdout/stderr/result fields.
        """
        stdout = None
        stderr = None
        raw_stdout = None
        raw_stderr = None
        
        if isinstance(value, dict):
            stdout = value.get("stdout")
            stderr = value.get("stderr")
            raw_stdout = value.get("raw_stdout", stdout)
            raw_stderr = value.get("raw_stderr", stderr)
            
            # Legacy: allow "result" only as a bridge (optional)
            if stdout is None and "result" in value:
                stdout = str(value["result"])
                if raw_stdout is None:
                    raw_stdout = stdout
            
            if self.strict_mode and stdout is None and stderr is None:
                # Hard fail: tool contract is broken
                raise ValueError(
                    f"Tool '{tool_name}' returned dict without stdout/stderr/result; "
                    "fix the tool to provide explicit output fields."
                )

            # Fallback for non-strict mode
            if stdout is None and stderr is None:
                try:
                    stdout = json.dumps(value, indent=2, ensure_ascii=False)
                    raw_stdout = stdout
                except Exception:
                    stdout = str(value)
                    raw_stdout = stdout

        elif isinstance(value, (list, tuple)):
            stdout = "\n".join(str(item) for item in value)
            raw_stdout = stdout
        elif value is not None:
            stdout = value if isinstance(value, str) else str(value)
            raw_stdout = stdout
        else:
            stdout = ""
            raw_stdout = ""
        
        return {
            "stdout": stdout,
            "stderr": stderr,
            "raw_stdout": raw_stdout,
            "raw_stderr": raw_stderr
        }
    
    def _build_preview(
        self,
        stdout: Optional[str],
        stderr: Optional[str]
    ) -> Optional[str]:
        """Return truncated preview text for Memory snapshots."""
        source = stdout if stdout not in (None, "") else stderr
        if not source:
            return None
        return source[: self.MAX_OUTPUT_PREVIEW]


def format_observation_content(
    tool_name: str,
    result: str,
    success: bool,
    exit_code: Optional[int] = None,
    error_msg: Optional[str] = None
) -> str:
    """
    Format tool execution result as observation content (for LLM).
    
    Extracted helper function from agent.py for use in Agent B.
    
    Args:
        tool_name: Tool that was executed
        result: Tool output
        success: Whether execution succeeded
        exit_code: Exit code (for shell commands)
        error_msg: Error message (if failed)
    
    Returns:
        Formatted observation string
    """
    if not success:
        if error_msg:
            return f"Error executing {tool_name}: {error_msg}"
        return f"Error executing {tool_name}"
    
    # Format successful result
    header = f"Result from {tool_name}"
    if exit_code is not None:
        header += f" (exit code: {exit_code})"
    
    return f"{header}:\n{result}"
