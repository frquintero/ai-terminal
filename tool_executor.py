"""
ToolExecutor - Reusable tool execution wrapper for v2.0 Orchestrator

Extracted from agent.py for use in Agent B (Executor) and Router cached execution.
Handles tool validation, execution, error handling, and logging.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

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
    
    def __init__(self, memory=None):
        """
        Initialize tool executor.
        
        Args:
            memory: Optional Memory instance for logging
        """
        self.memory = memory
    
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
        
        Returns:
            Dict with:
                - success: bool
                - result: str (tool output)
                - exit_code: int (for shell commands)
                - error: str (if failed)
        """
        # Validate tool exists
        tool = TOOLS.get(tool_name)
        if not tool:
            error_msg = f"Unknown tool: {tool_name}"
            if self.memory and cycle_id and step_id is not None:
                self._log_to_memory(
                    cycle_id=cycle_id,
                    step_id=step_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    success=False,
                    result=error_msg,
                    exit_code=None
                )
            return {
                "success": False,
                "result": error_msg,
                "exit_code": None,
                "error": error_msg
            }
        
        # Execute tool
        try:
            result = tool.execute(**tool_args)
            result_str = result if isinstance(result, str) else str(result)
            
            # Extract exit code if available
            # Note: Some tools set exit code in _SESSION_STATE, but we'll track it separately
            exit_code = self._extract_exit_code(tool_name, result)
            
            # Log to memory
            if self.memory and cycle_id and step_id is not None:
                self._log_to_memory(
                    cycle_id=cycle_id,
                    step_id=step_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    success=True,
                    result=result_str,
                    exit_code=exit_code
                )
            
            return {
                "success": True,
                "result": result_str,
                "exit_code": exit_code,
                "error": None
            }
        
        except Exception as e:
            error_msg = f"Tool '{tool_name}' raised error: {e}"
            
            # Log error to memory
            if self.memory and cycle_id and step_id is not None:
                self._log_to_memory(
                    cycle_id=cycle_id,
                    step_id=step_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    success=False,
                    result=error_msg,
                    exit_code=None
                )
            
            return {
                "success": False,
                "result": error_msg,
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
        
        # Future enhancement: Schema validation
        # tool_schema = get_tool_schemas().get(tool_name)
        # validate args against schema
        
        return True, None
    
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
        # For shell commands, exit code is in _SESSION_STATE
        # but ToolExecutor should be stateless, so we parse from result
        
        # Future enhancement: Standardize exit code in tool return values
        # For now, return None (actual exit codes tracked in _SESSION_STATE)
        
        return None
    
    def _log_to_memory(
        self,
        cycle_id: str,
        step_id: int,
        tool_name: str,
        tool_args: Dict[str, Any],
        success: bool,
        result: str,
        exit_code: Optional[int]
    ):
        """
        Log tool execution to Memory.
        
        Args:
            cycle_id: Cycle ID
            step_id: Step number
            tool_name: Tool executed
            tool_args: Tool arguments
            success: Whether execution succeeded
            result: Tool output
            exit_code: Exit code (if available)
        """
        # Truncate output for storage
        output_preview = result[:self.MAX_OUTPUT_PREVIEW]
        if len(result) > self.MAX_OUTPUT_PREVIEW:
            output_preview += f"... [{len(result) - self.MAX_OUTPUT_PREVIEW} more chars]"
        
        # Save to step_outputs
        self.memory.save_step_output(
            cycle_id=cycle_id,
            step_id=step_id,
            tool_name=tool_name,
            tool_args=tool_args,
            success=success,
            exit_code=exit_code,
            output_preview=output_preview,
            artifact_path=None  # Future enhancement: Save large outputs to files
        )


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
