"""
Orchestrator - Routerless dual-agent controller.

Coordinates: Agent A (plan/chat) → Agent B (commands) → Agent A narrator.
Every user query now enters through Agent A, which decides between
direct responses or structured plans that Agent B executes.
"""

import hashlib
import json
import os
import re
import time
import traceback
import uuid
from string import Formatter
from typing import Any, Callable, Dict, List, Optional, Tuple

from config import Config
from llm_client import LLMClient
from memory.api import Memory
from orchestrator.prompts import (
    get_agent_a_system_prompt,
    get_agent_a_user_message,
    get_agent_b_system_prompt,
    get_agent_b_user_message,
    AGENT_A_TOOLS,
    RESPOND_TO_USER_TOOL
)
from orchestrator.metrics import CycleMetrics, StepMetrics, LLMMetrics, get_metrics
from orchestrator.system_context_builder import SystemContextBuilder
from orchestrator.plan_validator import PlanValidator, PlanValidationError
from orchestrator.plan_schema import detect_response_type
from orchestrator.output_parser import OutputParser, OutputParserError
from orchestrator.routes import Route
from tool_executor import ToolExecutor
from tools import TOOLS, _SESSION_STATE


class OrchestratorResult:
    """Result of orchestration cycle"""
    
    def __init__(
        self,
        cycle_id: str,
        route: str,
        query: str,
        agent_response: str,
        execution_result: Optional[Dict[str, Any]] = None,
        latency_ms: int = 0,
        error: Optional[str] = None,
        response_segments: Optional[List[Dict[str, Any]]] = None
    ):
        self.cycle_id = cycle_id
        self.route = route
        self.query = query
        self.agent_response = agent_response
        self.execution_result = execution_result
        self.latency_ms = latency_ms
        self.error = error
        self.response_segments = response_segments
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for testing/logging"""
        return {
            "cycle_id": self.cycle_id,
            "route": self.route,
            "query": self.query,
            "agent_response": self.agent_response,
            "execution_result": self.execution_result,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "response_segments": self.response_segments
        }


class OrchestratorProcessError(Exception):
    """Represents a failure in a specific orchestrator process (Agent A, Agent B, executor, etc.)."""

    def __init__(
        self,
        message: str,
        *,
        process: str,
        stage: str,
        facts: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        root_error: Optional[BaseException] = None
    ):
        super().__init__(message)
        self.process = process
        self.stage = stage
        self.facts = facts or {}
        self.error_code = error_code
        self.root_error = root_error

    @property
    def root_error_type(self) -> str:
        if self.root_error:
            return self.root_error.__class__.__name__
        return self.__class__.__name__

class Orchestrator:
    """
    Main orchestrator for the dual-agent architecture.
    
    Entry point: handle_query(query) → OrchestratorResult
    
    Workflow:
    1. Create cycle_id and log to Memory
    2. Call Agent A (planner/chat) to produce a direct reply or execution plan
    3. If a plan is returned, Agent B engineers tool commands and ToolExecutor runs them
    4. Agent A narrator or narration template produces the final response
    5. Return OrchestratorResult with route + metrics
    """
    
    # Constants
    SHELL_TOOLS = {"run_command", "run_interactive"}
    SUPPORTED_OUTPUT_FORMAT_TYPES = {"int", "float", "str", "list", "raw", "table", "json"}
    
    def __init__(self, config: Config, memory: Optional[Memory] = None):
        """
        Initialize orchestrator.
        
        Args:
            config: Config object with LLM settings
            memory: Optional Memory instance (creates new if None)
        """
        self.config = config
        self.memory = memory or Memory()
        
        # Initialize components
        # Enable strict mode for implementation phase (no JSON fallbacks)
        self.tool_executor = ToolExecutor(strict_mode=True)
        self.output_parser = OutputParser()
        self.context_builder = SystemContextBuilder(memory=self.memory)

        # Detect system state once at startup (cached for session)
        self.system_state = self.context_builder.detect_system_state()

        # Session management
        self.session_id = self._initialize_session()
        self._event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    
    def _initialize_session(self) -> str:
        """Create or retrieve session with detected system state"""
        # For MVP, create new session each time
        # Phase 3+ will support session persistence
        session_id = str(uuid.uuid4())
        
        # Use detected system state (already cached in self.system_state)
        # Fallback to basic info if detection failed
        if self.system_state:
            system_info = self.system_state
        else:
            system_info = {
                "os": os.uname().sysname if hasattr(os, 'uname') else "Unknown",
                "cwd": os.getcwd(),
                "model": self.config.model
            }
        
        self.memory.create_session(
            session_id=session_id,
            model=self.config.model,
            system_info=system_info
        )

        return session_id

    def set_event_callback(
        self,
        callback: Optional[Callable[[str, Dict[str, Any]], None]]
    ) -> None:
        """Register a callback for orchestration status/tool events."""
        self._event_callback = callback

    def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Safely emit orchestration events to the registered callback."""
        if not self._event_callback:
            return
        try:
            self._event_callback(event_type, payload)
        except Exception:
            # Never allow UI callback failures to break orchestration
            pass

    def _emit_status(self, phase: str, details: Optional[Dict[str, Any]] = None) -> None:
        payload = {"phase": phase}
        if details:
            payload.update(details)
        self._emit_event("status", payload)

    def _emit_tool_output(self, payload: Dict[str, Any]) -> None:
        self._emit_event("tool_output", payload)
    
    def _extract_tool_hint(self, error_text: Optional[str]) -> Optional[str]:
        """Best-effort extraction of a tool name from an error string."""
        if not error_text:
            return None
        patterns = [
            r"tool ['\"]?([A-Za-z0-9_]+)['\"]?",
            r"\"name\"\\s*:\\s*\"([A-Za-z0-9_]+)\"",
        ]
        for pattern in patterns:
            match = re.search(pattern, error_text)
            if match:
                return match.group(1)
        return None
    
    def _get_effective_shell_cwd(self) -> str:
        """
        Get the effective shell working directory for system prompts.
        
        Returns the actual sandbox/container cwd where commands execute,
        not the host process cwd. This ensures agents receive accurate
        context about where their commands will run.
        
        - If isolation enabled: returns "/workspace" (rootfs mount point)
        - If isolation disabled: returns TOOLS['run_command'].working_dir (sandbox path)
        """
        return TOOLS['run_command'].get_effective_cwd()

    
    def handle_query(self, query: str) -> OrchestratorResult:
        """Main entry point – every query flows through Agent A first."""
        start_time = time.time()
        result: Optional[OrchestratorResult] = None
        route_value: str = Route.PLANNER.value
        cycle_id: Optional[str] = None
        session_activity_needed = False
        cycle_success = False
        failure_context: Optional[Dict[str, Any]] = None

        with self.memory.cycle_transaction() as txn:
            cycle_id = self.memory.create_cycle(
                session_id=self.session_id,
                query=query
            )

            try:
                result = self._run_agent_a_cycle(cycle_id, query)
                # Guarantee result references the orchestrator-assigned cycle
                result.cycle_id = cycle_id
                route_value = result.route or Route.PLANNER.value

                self.memory.save_router_decision(
                    cycle_id=cycle_id,
                    route=route_value,
                    confidence=1.0,
                    rules=None,
                    cache_hit_tool=None,
                    cache_hit_args=None
                )

                result.latency_ms = int((time.time() - start_time) * 1000)
                self._record_cycle_metric(
                    route_value=route_value,
                    latency_ms=result.latency_ms,
                    execution_result=result.execution_result,
                    cycle_id=cycle_id
                )

                session_activity_needed = True

                cycle_success = self._cycle_succeeded(route_value, result)

                if cycle_success:
                    txn.commit()
                else:
                    failure_context = {
                        "process": "executor",
                        "stage": "execution",
                        "error_type": "CycleFailure",
                        "error_message": result.error or "Cycle marked unsuccessful",
                        "facts": {
                            "execution_result": self._json_safe(result.execution_result),
                            "agent_response": result.agent_response
                        }
                    }

            except OrchestratorProcessError as e:
                latency_ms = int((time.time() - start_time) * 1000)
                agent_response = self._build_failure_notice(cycle_id)
                result = OrchestratorResult(
                    cycle_id=cycle_id,
                    route=route_value,
                    query=query,
                    agent_response=agent_response,
                    latency_ms=latency_ms,
                    error=str(e),
                    response_segments=[{"kind": "text", "text": agent_response}]
                )
                failure_context = {
                    "process": e.process,
                    "stage": e.stage,
                    "error_type": e.root_error_type,
                    "error_code": e.error_code,
                    "error_message": str(e),
                    "facts": e.facts
                }
                cycle_success = False
            except PlanValidationError as e:
                latency_ms = int((time.time() - start_time) * 1000)
                agent_response = self._build_failure_notice(cycle_id)
                result = OrchestratorResult(
                    cycle_id=cycle_id,
                    route=route_value,
                    query=query,
                    agent_response=agent_response,
                    latency_ms=latency_ms,
                    error=str(e),
                    response_segments=[{"kind": "text", "text": agent_response}]
                )
                failure_context = {
                    "process": "agent_a_planner",
                    "stage": "planning",
                    "error_type": "PlanValidationError",
                    "error_message": str(e),
                    "facts": {"detail": str(e)}
                }
                cycle_success = False

            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)
                agent_response = self._build_failure_notice(cycle_id)
                result = OrchestratorResult(
                    cycle_id=cycle_id,
                    route=route_value,
                    query=query,
                    agent_response=agent_response,
                    latency_ms=latency_ms,
                    error=str(e),
                    response_segments=[{"kind": "text", "text": agent_response}]
                )
                failure_context = {
                    "process": "orchestrator",
                    "stage": "orchestrator",
                    "error_type": e.__class__.__name__,
                    "error_message": str(e),
                    "facts": {
                        "traceback": traceback.format_exc()
                    }
                }
                cycle_success = False

        if session_activity_needed:
            self.memory.update_session_activity(self.session_id)

        if not cycle_success and cycle_id:
            if failure_context is None:
                failure_context = {
                    "process": "executor",
                    "stage": "execution",
                    "error_type": "CycleFailure",
                    "error_message": result.error if result else "Cycle failed",
                    "facts": {
                        "execution_result": self._json_safe(getattr(result, "execution_result", None)),
                        "agent_response": getattr(result, "agent_response", None)
                    }
                }
            self._record_cycle_failure(
                cycle_id=cycle_id,
                query=query,
                route_value=route_value,
                failure_context=failure_context,
                result=result
            )
            if result:
                failure_notice = self._build_failure_notice(cycle_id)
                result.agent_response = failure_notice
                result.response_segments = [{"kind": "text", "text": failure_notice}]

        return result

    def _build_failure_notice(self, cycle_id: Optional[str]) -> str:
        identifier = cycle_id or "unknown-cycle"
        return (
            f"Cycle {identifier} failed. Detailed telemetry is stored in cycle_failures."
        )

    def _record_cycle_metric(
        self,
        *,
        cycle_id: str,
        route_value: str,
        latency_ms: int,
        execution_result: Optional[Dict[str, Any]]
    ) -> None:
        interactive = False
        exec_result = execution_result or {}

        if isinstance(exec_result, dict):
            if exec_result.get("tool_name") == "run_interactive":
                interactive = True
            step_results = exec_result.get("step_results")
            if isinstance(step_results, list):
                interactive = any(
                    step.get("tool_name") == "run_interactive"
                    for step in step_results
                )

        used_plan = route_value == Route.PLANNER.value
        cycle_metric = CycleMetrics(
            cycle_id=cycle_id,
            used_plan=used_plan,
            latency_ms=latency_ms,
            interactive=interactive
        )

        if hasattr(self.memory, "record_cycle_metric"):
            self.memory.record_cycle_metric(
                cycle_id=cycle_metric.cycle_id,
                used_plan=cycle_metric.used_plan,
                latency_ms=cycle_metric.latency_ms,
                interactive=cycle_metric.interactive
            )
        else:
            metrics = get_metrics()
            metrics.record_cycle_metric(cycle_metric)
    
    def _run_agent_a_cycle(self, cycle_id: str, query: str) -> OrchestratorResult:
        """
        Unified Agent A entry point (planning + narration).
        
        Agent A can respond with TWO types:
        1. Execution plan (steps + narration template)
        2. Direct response (no tool usage)
        
        Workflow:
        1. Retrieve Chat→Planner context (last 3 chat interactions)
        2. Call Agent A (Planner) to generate JSON response with context
        3. Validate response structure
        4. Handle based on response type
        
        Target: <2s response generation, 95%+ valid JSON on first attempt
        """
        self._emit_status("planning", {"route": "PLANNER", "stage": "agent_a"})
        # Get available tools for validation
        available_tools = sorted(TOOLS.keys())
        tool_schemas = self._get_tool_schemas("B")

        # Create validator
        validator = PlanValidator(available_tools=available_tools)
        
        # Build system context for Agent A
        system_context = self.context_builder.build_for_role(
            role="A",
            session_id=self.session_id,
            tool_registry=TOOLS,
            shell_cwd=self._get_effective_shell_cwd()
        )
        
        # Build Agent A prompt
        system_prompt = system_context + "\n\n" + get_agent_a_system_prompt(tool_schemas)
        context_msg = self._build_agent_a_context_message(query)
        
        user_message = get_agent_a_user_message(context_msg)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        # Execute Agent A (Planner) - Single Shot (No Retries)
        self._emit_status(
            "planning",
            {"route": "PLANNER", "stage": "agent_a"}
        )
        
        # Call LLM in Agent A role
        llm_client = LLMClient(
            config=self.config,
            role="A",
            memory=self.memory
        )
        
        llm_result = llm_client.call(
            messages=messages,
            cycle_id=cycle_id,
            session_id=self.session_id,
            temperature=self.config.agent_a_temperature,
            tools=AGENT_A_TOOLS
        )
        
        response = None
        last_error = None
        
        if llm_result["error"]:
            last_error = f"LLM call failed: {llm_result['error']}"
        else:
            msg = llm_result["message"]
            # Check for tool calls
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tc = msg.tool_calls[0]
                fname = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                    if fname == "delegate_to_agent_b":
                        response = self._normalize_agent_a_plan(
                            {
                                "intent": args.get("intent"),
                                "success_criteria": args.get("success_criteria"),
                                "todos": args.get("todos")
                            },
                            query=query
                        )
                    elif fname == "respond_to_user":
                        response = {
                            "segments": args.get("segments"),
                            "policy_contract": args.get("policy_contract"),
                            "policy_summary": args.get("policy_summary"),
                            "attachments": args.get("attachments"),
                            "template_values": args.get("template_values")
                        }
                    else:
                        last_error = f"Unknown tool called: {fname}"
                except json.JSONDecodeError as e:
                    last_error = f"Invalid tool arguments JSON: {e}"
            else:
                # Fallback: Check if content is present and try to use it
                if msg.content:
                    # Attempt to parse as JSON just in case model ignored tools but followed old prompt
                    response, error_hint = validator.validate_with_hints(msg.content)
                    if not response:
                        last_error = "Agent A did not call any tool (and content was not valid JSON)"
                else:
                    last_error = "Agent A did not call any tool or provide content"

        # Check if we got a valid response
        if not response:
            raise PlanValidationError(last_error or "Planner failed to produce a valid tool call")
        
        # Detect response type and handle accordingly
        response_type = detect_response_type(response)
        
        if response_type == "response":
            response_segments = self._sanitize_empty_segments(
                response.get("segments") or [],
                []
            )
            agent_response = self._segments_to_text(response_segments)
            # Treat as final answer without tool execution
            self.memory.save_chat_exchange(
                session_id=self.session_id,
                cycle_id=cycle_id,
                user_query=query,
                agent_response=agent_response
            )
            self._emit_status(
                "preparing_response",
                {"route": "PLANNER", "direct_response": True}
            )
            return OrchestratorResult(
                cycle_id=cycle_id,
                route=Route.CHAT.value,
                query=query,
                agent_response=agent_response,
                execution_result=None,
                response_segments=response_segments
            )
        
        if response_type != "execution_plan":
            raise PlanValidationError("Agent A produced an unknown response type")
        
        # Save plan to task_state
        plan = response
        self.memory.save_plan(
            cycle_id=cycle_id,
            plan=plan,
            status="in_progress"
        )
        
        # Phase 4: Execute plan via Agent B step loop
        try:
            execution_result = self._execute_plan(cycle_id, query, plan)
            
            # Mark as completed
            self.memory.update_task_status(
                cycle_id=cycle_id,
                status="done" if execution_result.get("success") else "error",
                current_step_id=execution_result.get("total_steps", 0) - 1
            )
            
            self._emit_status(
                "preparing_response",
                {"route": "PLANNER", "success": execution_result.get("success")}
            )

            response_segments = (
                execution_result.get("narration_segments")
                or execution_result.get("response_segments")
            )
            if not response_segments:
                fallback_text = (
                    execution_result.get("final_response")
                    or execution_result.get("narration_template")
                    or "Task completed."
                )
                response_segments = [{"kind": "text", "text": fallback_text}]

            final_response = self._segments_to_text(response_segments)
            execution_result["narration_segments"] = response_segments

            self.memory.save_chat_exchange(
                session_id=self.session_id,
                cycle_id=cycle_id,
                user_query=query,
                agent_response=final_response
            )
            
            return OrchestratorResult(
                cycle_id=cycle_id,
                route=Route.PLANNER.value,
                query=query,
                agent_response=final_response,
                execution_result=execution_result,
                response_segments=response_segments
            )
        
        except OrchestratorProcessError:
            raise
        except Exception as e:
            self.memory.update_task_status(
                cycle_id=cycle_id,
                status="error",
                error_message=str(e)
            )
            tool_hint = self._extract_tool_hint(str(e))
            facts = {
                "tool_hint": tool_hint,
                "exception": str(e),
                "traceback": traceback.format_exc()
            }
            raise OrchestratorProcessError(
                "Agent B execution failed",
                process="agent_b_execution",
                stage="execution",
                facts=facts,
                root_error=e
            )
    
    def _auto_fence_code(self, text: str) -> str:
        """Heuristically add fences if text looks like raw code."""
        if not text or "```" in text:
            return text
        
        # PHP
        if text.strip().startswith("<?php"):
            return f"```php\n{text}\n```"
        
        # Shell script
        if text.strip().startswith("#!"):
             return f"```bash\n{text}\n```"
             
        return text

    def _normalize_agent_a_plan(self, plan: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Ensure Agent A plans always include required intent/success metadata."""
        if not isinstance(plan, dict):
            plan = {}

        normalized: Dict[str, Any] = dict(plan)

        query_text = (query or "").strip() or "user request"

        intent = normalized.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            normalized["intent"] = f"Fulfill user request: {query_text}"
        else:
            normalized["intent"] = intent.strip()

        success_criteria = normalized.get("success_criteria")
        if isinstance(success_criteria, list):
            filtered = [str(item).strip() for item in success_criteria if isinstance(item, str) and item.strip()]
        else:
            filtered = []
        if not filtered:
            filtered = [
                "All TODO items complete successfully",
                f"User request '{query_text}' is satisfied"
            ]
        normalized["success_criteria"] = filtered

        todos = self._normalize_todo_items(normalized.get("todos"), query_text)
        if not todos:
            fallback_desc = f"Execute requested action: {query_text}"
            todos = [{
                "description": fallback_desc,
                "success_criteria": [
                    f"{fallback_desc} completes without errors",
                    "Output is reviewed or shared with the user"
                ],
                "required": True,
                "subtasks": []
            }]
        normalized["todos"] = todos

        return normalized

    def _normalize_todo_items(
        self,
        todos: Any,
        query_text: str,
        parent_description: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Normalize TODO entries recursively, guaranteeing success criteria."""
        normalized: List[Dict[str, Any]] = []
        if not isinstance(todos, list):
            return normalized

        for idx, raw in enumerate(todos, start=1):
            if not isinstance(raw, dict):
                continue

            description = raw.get("description")
            if not isinstance(description, str) or not description.strip():
                base = parent_description or "Task"
                description = f"{base} {idx}" if parent_description else f"Task {idx}"
            else:
                description = description.strip()

            success_list = raw.get("success_criteria")
            if isinstance(success_list, list):
                filtered_success = [
                    str(item).strip()
                    for item in success_list
                    if isinstance(item, str) and item.strip()
                ]
            else:
                filtered_success = []
            if not filtered_success:
                filtered_success = [f"{description} completes without errors"]

            subtasks = self._normalize_todo_items(
                raw.get("subtasks"),
                query_text,
                parent_description=description
            )

            preserved = {
                key: value
                for key, value in raw.items()
                if key not in {"description", "success_criteria", "subtasks"}
            }

            normalized.append({
                **preserved,
                "description": description,
                "success_criteria": filtered_success,
                "subtasks": subtasks
            })

        return normalized

    def _get_tool_schemas(self, role: str) -> List[Dict[str, Any]]:
        """Get native tool schemas for the given role."""
        if role == "B":
            schemas = [tool.schema for tool in TOOLS.values()]
            schemas.append(RESPOND_TO_USER_TOOL)
            return schemas
        return []

    def _run_agent_b_tool_loop(
        self,
        cycle_id: str,
        query: str,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute the plan using Agent B's native tool loop.
        """
        # Parse and initialize TODO tracking
        todos = plan.get("todos", [])
        current_todo_index = 0
        
        # Initialize TODO tracking in database
        for i, todo in enumerate(todos):
            if isinstance(todo, dict) and "description" in todo:
                self.memory.record_todo_status(
                    cycle_id=cycle_id,
                    todo_index=i,
                    description=todo["description"],
                    status="pending"
                )
        
        # We pass empty list to system prompt as we don't need schema injection for the execution phase
        system_prompt = get_agent_b_system_prompt([]) 
        user_msg = get_agent_b_user_message(plan)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]

        tool_outputs_by_call_id: Dict[str, Dict[str, Any]] = {}
        last_data_source: Optional[Dict[str, Any]] = None
        
        tools = self._get_tool_schemas("B")
        max_loops = 15
        
        step_results = []
        steps_completed = 0
        steps_failed = 0
        total_steps_attempted = 0
        parsed_outputs = None
        output_values: Dict[str, Any] = {}
        output_value_types: Dict[str, Any] = {}
        output_value_sources: Dict[str, Any] = {}
        template_values: Dict[str, Any] = {}
        
        llm_client = LLMClient(
            config=self.config,
            role="B",
            memory=self.memory
        )
        
        final_response = ""
        agent_b_notes = ""
        last_stdout = None
        last_raw_stdout = None
        respond_to_user_called = False
        respond_segments: Optional[List[Dict[str, Any]]] = None
        respond_policy_contract: Optional[Dict[str, Any]] = None
        respond_policy_summary: Optional[str] = None
        respond_attachments: Optional[List[Dict[str, Any]]] = None

        def _is_informative_negative(exit_code: Optional[int], stdout: Optional[str], stderr: Optional[str]) -> bool:
            """
            Treat common non-zero exit codes with meaningful output as informative (not fatal):
            - 1/2: general/usage errors that still convey "not found"/"no matches"
            - 127: command not found diagnostics
            Only when there is some stdout/stderr to explain the condition.
            """
            if exit_code not in {1, 2, 127}:
                return False
            diagnostic = (stdout or "") + (stderr or "")
            return diagnostic.strip() != ""
        
        def _validate_tool_call_against_todo(tool_name: str, tool_args: Dict[str, Any]) -> bool:
            """
            Validate that the tool call aligns with the current TODO item.
            
            Returns True if the tool call is approved for the current TODO.
            """
            if not todos or current_todo_index >= len(todos):
                # No TODOs defined, allow all tools
                return True
            
            current_todo = todos[current_todo_index]
            if not isinstance(current_todo, dict):
                return True
            
            todo_description = current_todo.get("description", "").lower()
            
            # Simple heuristic validation - check if tool/command relates to TODO
            if tool_name == "run_command":
                command = tool_args.get("command", "").lower()
                # Check if command keywords appear in TODO description
                command_keywords = command.split()
                description_words = todo_description.split()
                
                # Allow if any command keyword appears in TODO description
                for keyword in command_keywords:
                    if keyword in description_words:
                        return True
                
                # Special cases for common commands
                if "list" in todo_description and command in ["ls", "ls -la", "ls -l"]:
                    return True
                if "directory" in todo_description and "ls" in command:
                    return True
            
            # For other tools, be more permissive for now
            return True
        
        def _check_todo_completion() -> bool:
            """
            Check if current TODO is complete based on success criteria.
            
            Returns True if TODO should be marked complete.
            """
            if not todos or current_todo_index >= len(todos):
                return False
            
            current_todo = todos[current_todo_index]
            if not isinstance(current_todo, dict):
                return False
            
            success_criteria = current_todo.get("success_criteria", [])
            if not success_criteria:
                # No explicit criteria, assume complete after any successful step
                return len(step_results) > 0 and step_results[-1].get("success", False)
            
            # Simple heuristic: if we have successful steps and the criteria mention
            # common outcomes, assume completion
            last_step = step_results[-1] if step_results else None
            if last_step and last_step.get("success"):
                criteria_text = " ".join(success_criteria).lower()
                if any(keyword in criteria_text for keyword in ["executed", "completed", "successful", "run"]):
                    return True
            
            return False
        
        try:
            for loop_idx in range(max_loops):
                # Call LLM
                response = llm_client.call(
                    messages=messages,
                    tools=tools,
                    cycle_id=cycle_id,
                    session_id=self.session_id,
                    temperature=self.config.agent_b_temperature
                )
                
                if response["error"]:
                    # Log error and break
                    final_response = f"Error calling Agent B: {response['error']}"
                    break
                    
                msg = response["message"]
                if not msg:
                    final_response = "Error: No message returned from Agent B"
                    break
                
                # Append assistant message to history
                assistant_msg_dict = {
                    "role": "assistant",
                    "content": msg.content
                }
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    # Convert tool_calls objects to dicts for serialization
                    tool_calls_list = []
                    for tc in msg.tool_calls:
                        if hasattr(tc, "model_dump"):
                            tool_calls_list.append(tc.model_dump())
                        elif hasattr(tc, "to_dict"):
                            tool_calls_list.append(tc.to_dict())
                        else:
                            tool_calls_list.append(tc)
                    assistant_msg_dict["tool_calls"] = tool_calls_list
                    
                messages.append(assistant_msg_dict)
                
                if not getattr(msg, "tool_calls", None):
                    # No tools called = Final response
                    raw_content = msg.content or ""
                    # Clean <think> tags and extra whitespace
                    final_response = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
                    agent_b_notes = final_response
                    break
                
                # Execute tools
                for tc in msg.tool_calls:
                    total_steps_attempted += 1
                    tool_name = tc.function.name
                    tool_call_id = getattr(tc, "id", None)
                    parsed_outputs = None
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    if not isinstance(args, dict):
                        args = {}
                   
                    output_format = args.pop("output_format", {})
                    exec_args = dict(args)
                    input_data_ref = exec_args.pop("input_data_ref", None)
                    resolved_input_error = None
                    resolved_input_data = None

                    if input_data_ref is not None:
                        if tool_name != "run_command":
                            resolved_input_error = "input_data_ref is only supported on run_command"
                        elif exec_args.get("input_data"):
                            resolved_input_error = "Provide either input_data or input_data_ref, not both"
                        else:
                            ok, data_or_error = self._resolve_input_data_ref(
                                input_data_ref,
                                tool_outputs_by_call_id
                            )
                            if ok:
                                resolved_input_data = data_or_error
                            else:
                                resolved_input_error = data_or_error
                   
                    exec_args = self._strip_null_values(exec_args)
                    args = self._strip_null_values(args)

                    if tool_name == "respond_to_user":
                        validation_errors = []
                        raw_segments = args.get("segments")
                        policy_contract = args.get("policy_contract")
                        policy_summary = args.get("policy_summary")
                        template_values_update = args.get("template_values") or {}
                        attachments_payload = args.get("attachments") or []

                        if not isinstance(raw_segments, list) or not raw_segments:
                            validation_errors.append("segments must be a non-empty array")
                        if not isinstance(policy_contract, dict):
                            validation_errors.append("policy_contract must be an object")
                        if not isinstance(policy_summary, str) or not policy_summary.strip():
                            validation_errors.append("policy_summary must be a non-empty string")
                        if validation_errors:
                            raise OrchestratorProcessError(
                                "respond_to_user payload invalid",
                                process="agent_b_finalization",
                                stage="validation",
                                facts={
                                    "errors": validation_errors,
                                    "payload": self._json_safe(args)
                                },
                                error_code="invalid_final_payload"
                            )

                        sanitized_segments = self._sanitize_empty_segments(raw_segments, step_results)
                        respond_segments = sanitized_segments
                        respond_policy_contract = policy_contract
                        respond_policy_summary = policy_summary.strip()
                        respond_attachments = attachments_payload if isinstance(attachments_payload, list) else []
                        if isinstance(template_values_update, dict):
                            template_values.update(template_values_update)

                        final_response = self._segments_to_text(sanitized_segments)
                        agent_b_notes = final_response
                        steps_completed += 1

                        step_id = len(step_results)
                        step_result = {
                            "step_id": step_id,
                            "tool_name": "respond_to_user",
                            "tool_args": args,
                            "description": f"Step {step_id}: respond_to_user",
                            "success": True,
                            "exit_code": None,
                            "stdout": final_response,
                            "stderr": None,
                            "output": final_response,
                            "error": None,
                            "informative_negative": False,
                            "output_format": None
                        }
                        step_results.append(step_result)

                        preview_text = (final_response or "")[:500]
                        try:
                            self.memory.save_step_output(
                                cycle_id=cycle_id,
                                step_id=step_id,
                                tool_name="respond_to_user",
                                tool_args=args,
                                success=True,
                                exit_code=None,
                                output_preview=preview_text,
                                stdout=final_response,
                                stderr=None,
                                raw_stdout=final_response,
                                raw_stderr=None,
                                output_format=None,
                                parsed_outputs={
                                    "segments": sanitized_segments,
                                    "policy_contract": policy_contract,
                                    "policy_summary": respond_policy_summary
                                },
                                artifact_path=None
                            )
                        except Exception:
                            pass

                        _SESSION_STATE.record_tool_call(
                            tool_name="respond_to_user",
                            args=args,
                            success=True,
                            exit_code=None,
                            error=None,
                            tool_call_id=tool_call_id,
                            step_id=step_id,
                            output_preview=preview_text
                        )

                        if tool_call_id:
                            tool_outputs_by_call_id[tool_call_id] = {
                                "tool_name": "respond_to_user",
                                "result": {
                                    "segments": sanitized_segments,
                                    "policy_contract": policy_contract,
                                    "policy_summary": respond_policy_summary
                                }
                            }

                        respond_to_user_called = True
                        break

                    # TODO Enforcement: Validate tool call against current TODO
                    if not _validate_tool_call_against_todo(tool_name, args):
                        # Tool call not approved for current TODO - this would be a violation
                        # For now, we'll log it but allow the execution to continue
                        # In a stricter implementation, we might reject the tool call
                        self.memory.record_todo_status(
                            cycle_id=cycle_id,
                            todo_index=current_todo_index,
                            description=todos[current_todo_index].get("description", "Unknown TODO"),
                            status="modified",
                            modifications_json={
                                "violation": "tool_call_not_aligned",
                                "tool_name": tool_name,
                                "tool_args": args,
                                "reason": "Tool call does not align with current TODO"
                            }
                        )
                    
                    # Log execution
                    step_id = len(step_results)
                    # Build metadata from current context since 'steps' key is deprecated in v3 plans
                    step_meta = {
                        "tool_name": tool_name,
                        "tool_args": args,
                        "intent": todos[current_todo_index].get("description") if todos and current_todo_index < len(todos) else None
                    }
                    
                    self._emit_status(
                       "executing", 
                       {
                           "route": "PLANNER", 
                           "step": step_id + 1, 
                           "tool": tool_name,
                           "command": args.get("command") if isinstance(args, dict) else None
                       }
                    )
                    
                    self.memory.update_task_status(
                       cycle_id=cycle_id,
                       status="in_progress",
                       current_step_id=step_id
                    )
    
                    if resolved_input_data is not None:
                        exec_args["input_data"] = resolved_input_data

                    try:
                        if resolved_input_error:
                            preview = resolved_input_error[:self.tool_executor.MAX_OUTPUT_PREVIEW]
                            exec_result = {
                                "success": False,
                                "stdout": "",
                                "stderr": resolved_input_error,
                                "raw_stdout": "",
                                "raw_stderr": "",
                                "exit_code": None,
                                "output_preview": preview,
                                "error": resolved_input_error,
                                    "result": ""
                                }
                        else:
                            exec_result = self.tool_executor.execute(
                                tool_name=tool_name,
                                tool_args=exec_args,
                                cycle_id=cycle_id,
                                step_id=step_id
                            )
                    except Exception as exec_error:
                        steps_failed += 1
                        description = f"Step {step_id}: {tool_name}"
                        step_result = {
                            "step_id": step_id,
                            "tool_name": tool_name,
                            "tool_args": args,
                            "description": description,
                            "success": False,
                            "exit_code": None,
                            "stdout": None,
                            "stderr": None,
                            "output": None,
                            "error": str(exec_error),
                            "output_format": output_format
                        }
                        step_results.append(step_result)

                        # Persist the failure for debugging/recall before any further LLM calls
                        try:
                            self._emit_tool_output({
                               "route": "PLANNER",
                               "step_id": step_id,
                               "tool_name": tool_name,
                               "tool_args": args,
                               "stdout": None,
                               "stderr": str(exec_error),
                               "success": False,
                               "events": None
                            })
                            self.memory.save_step_output(
                               cycle_id=cycle_id,
                               step_id=step_id,
                               tool_name=tool_name,
                               tool_args=args,
                               success=False,
                               exit_code=None,
                               output_preview=str(exec_error)[:500],
                               stdout=None,
                               stderr=str(exec_error),
                               raw_stdout=None,
                               raw_stderr=None,
                               output_format=output_format or None,
                               parsed_outputs=None,
                               artifact_path=None
                            )
                        except Exception:
                            # Never let logging failures mask the primary executor error
                            pass

                        raise OrchestratorProcessError(
                            f"ToolExecutor failed for {tool_name}",
                            process="agent_b_tool_executor",
                            stage="execution",
                            facts={
                                "tool_name": tool_name,
                                "tool_args": self._json_safe(args),
                                "error": str(exec_error),
                                "traceback": traceback.format_exc()
                            },
                            root_error=exec_error
                        )
                    
                    validation_error_text = self._extract_schema_validation_error(exec_result)
                    if validation_error_text:
                        raise OrchestratorProcessError(
                            "Tool call validation failed",
                            process="agent_b_tool_executor",
                            stage="execution",
                            facts={
                                "tool_name": tool_name,
                                "tool_args": self._json_safe(args),
                                "tool_call_id": tool_call_id,
                                "error": validation_error_text,
                                "executor_result": self._json_safe(exec_result)
                            },
                            error_code="tool_use_failed"
                        )
                    
                    snapshot_meta = self._build_output_snapshot(exec_result)
                    parsed_payload_for_memory: Optional[Any] = exec_result.get("events")
                    stdin_warning: Optional[str] = None
                    is_run_command = tool_name == "run_command"
                    provided_input_ref = args.get("input_data_ref")
                    provided_literal_input = args.get("input_data")
                    if is_run_command:
                        if provided_input_ref and last_data_source:
                            ref_id = None
                            if isinstance(provided_input_ref, dict):
                                ref_id = provided_input_ref.get("tool_call_id")
                            if ref_id and ref_id == last_data_source.get("tool_call_id"):
                                last_data_source = None
                        needs_warning = (
                            last_data_source is not None
                            and not provided_literal_input
                            and not provided_input_ref
                            and resolved_input_data is None
                            and exec_result.get("exit_code") not in (None, 0)
                            and (step_id - last_data_source.get("step_id", step_id)) <= 2
                        )
                        if needs_warning:
                            source_path = last_data_source.get("file_path") or "previous output"
                            source_tool = last_data_source.get("tool_name", "read_file")
                            source_id = last_data_source.get("tool_call_id")
                            exit_code = exec_result.get("exit_code")
                            stdin_warning = (
                                f"{tool_name} exited {exit_code} with empty stdin even though "
                                f"{source_tool} ({source_path}) just produced data (tool_call_id '{source_id}'). "
                                "Re-run with input_data_ref pointing at that call to pipe the content."
                            )
                            last_data_source = None
                        elif not provided_input_ref and resolved_input_data is None:
                            # Do not let stale read_file references linger forever once a command runs.
                            last_data_source = None
                    if stdin_warning:
                        prior_agent_msg = exec_result.get("agent_message")
                        if prior_agent_msg:
                            exec_result["agent_message"] = f"{stdin_warning}\n\n{prior_agent_msg}"
                        else:
                            exec_result["agent_message"] = stdin_warning
                        exec_result.setdefault("warnings", []).append(stdin_warning)
                    
                    if exec_result.get("stdout"):
                        last_stdout = exec_result.get("stdout")
                    if exec_result.get("raw_stdout"):
                        last_raw_stdout = exec_result.get("raw_stdout")
    
                    # Shell tools with non-zero exit codes should be marked failed even if the tool call itself returned
                    exit_code = exec_result.get("exit_code")
                    success = exec_result["success"]
                    informative_negative = False
                    if exit_code not in (None, 0):
                        if _is_informative_negative(exit_code, exec_result.get("stdout"), exec_result.get("stderr")):
                            informative_negative = True
                            success = True
                        else:
                            success = False
                    step_error = exec_result.get("error")
                    stderr_preview = exec_result.get("stderr")
                    if not success and not step_error:
                        if stderr_preview not in (None, ""):
                            step_error = stderr_preview
                        elif exit_code not in (None, 0):
                            step_error = f"Non-zero exit code {exit_code}"
                    if success or informative_negative:
                        steps_completed += 1
                    else:
                        steps_failed += 1
                    
                    description = f"Step {step_id}: {tool_name}"
                    
                    step_result = {
                        "step_id": step_id,
                        "tool_name": tool_name,
                        "tool_args": args,
                        "description": description,
                        "success": success,
                        "exit_code": exit_code,
                        "stdout": exec_result.get("stdout"),
                        "stderr": exec_result.get("stderr"),
                        "output": exec_result.get("stdout") or exec_result.get("stderr") or exec_result.get("result"),
                        "error": step_error,
                        "informative_negative": informative_negative,
                        "output_format": output_format
                    }
                    step_results.append(step_result)
                    
                    # TODO Enforcement: Check if current TODO is complete
                    if _check_todo_completion() and current_todo_index < len(todos):
                        self.memory.record_todo_status(
                            cycle_id=cycle_id,
                            todo_index=current_todo_index,
                            description=todos[current_todo_index].get("description", "Unknown TODO"),
                            status="completed"
                        )
                        current_todo_index += 1
                    
                    if success and output_format:
                        try:
                            parsed_outputs, rendered_outputs = self.output_parser.parse(
                                output_format,
                                exec_result.get("stdout"),
                                exec_result.get("raw_stdout"),
                                exec_result.get("data")
                            )
                        except OutputParserError:
                            parsed_outputs, rendered_outputs = {}, {}
                        parsed_payload_for_memory = parsed_outputs
    
                        for key, fmt in output_format.items():
                            rendered_value = rendered_outputs.get(key)
                            parsed_value = parsed_outputs.get(key)
                            if self._should_use_no_output_message(
                                fmt=fmt,
                                rendered_value=rendered_value,
                                parsed_value=parsed_value,
                                exec_result=exec_result
                            ):
                                fallback = self._format_no_output_message(
                                    step=step_meta or {},
                                    tool_args=args
                                )
                                output_values[key] = fallback
                                template_values[key] = fallback
                                output_value_sources[key] = {"no_output": True}
                            else:
                                output_values[key] = rendered_value
                                if isinstance(fmt, str) and fmt.lower() in {"int", "float"}:
                                    template_values[key] = parsed_value
                                else:
                                    template_values[key] = rendered_value
                                output_value_sources[key] = {
                                    "tool_name": tool_name,
                                    "tool_args": args,
                                    "command": args.get("command") if isinstance(args, dict) else None,
                                    "stdout": exec_result.get("stdout"),
                                    "raw_stdout": exec_result.get("raw_stdout")
                                }
                            output_value_types[key] = fmt
                    if snapshot_meta:
                        if parsed_payload_for_memory is None:
                            parsed_payload_for_memory = {"snapshot_meta": snapshot_meta}
                        elif isinstance(parsed_payload_for_memory, dict):
                            payload_copy = dict(parsed_payload_for_memory)
                            payload_copy["snapshot_meta"] = snapshot_meta
                            parsed_payload_for_memory = payload_copy
                        else:
                            parsed_payload_for_memory = {
                                "events": parsed_payload_for_memory,
                                "snapshot_meta": snapshot_meta
                            }

                    # Emit tool output event
                    self._emit_tool_output({
                       "route": "PLANNER",
                       "step_id": step_id,
                       "tool_name": tool_name,
                       "tool_args": args,
                       "stdout": exec_result.get("stdout"),
                       "stderr": exec_result.get("stderr"),
                       "success": success,
                       "events": exec_result.get("events"),
                       "warnings": exec_result.get("warnings")
                    })

                    if tool_call_id:
                        tool_outputs_by_call_id[tool_call_id] = {
                            "tool_name": tool_name,
                            "stdout": exec_result.get("stdout"),
                            "stderr": exec_result.get("stderr"),
                            "raw_stdout": exec_result.get("raw_stdout"),
                            "raw_stderr": exec_result.get("raw_stderr"),
                            "result": exec_result.get("result"),
                            "snapshot": snapshot_meta
                        }
                    
                    # Save step output
                    self.memory.save_step_output(
                       cycle_id=cycle_id,
                       step_id=step_id,
                       tool_name=tool_name,
                       tool_args=args,
                       success=success,
                       exit_code=exec_result.get("exit_code"),
                       output_preview=str(exec_result.get("stdout") or exec_result.get("stderr") or "")[:500],
                       stdout=exec_result.get("stdout"),
                       stderr=exec_result.get("stderr"),
                       raw_stdout=exec_result.get("raw_stdout"),
                       raw_stderr=exec_result.get("raw_stderr"),
                       output_format=output_format or None,
                       parsed_outputs=parsed_payload_for_memory,
                       artifact_path=exec_result.get("artifact_path")
                    )

                    preview_payload = (
                        exec_result.get("output_preview")
                        or exec_result.get("stdout")
                        or exec_result.get("stderr")
                        or exec_result.get("result")
                    )
                    if preview_payload is not None:
                        preview_payload = str(preview_payload)
                    _SESSION_STATE.record_tool_call(
                        tool_name=tool_name,
                        args=args,
                        success=success,
                        exit_code=exec_result.get("exit_code"),
                        error=step_error,
                        tool_call_id=tool_call_id,
                        step_id=step_id,
                        output_preview=preview_payload
                    )

                    if (
                        success
                        and tool_call_id
                        and tool_name in {"read_file", "pipe_from"}
                    ):
                        last_data_source = {
                            "tool_call_id": tool_call_id,
                            "file_path": args.get("file_path"),
                            "step_id": step_id,
                            "tool_name": tool_name
                        }
                    
                    # Append tool result to messages for next turn
                    tool_content = (
                       exec_result.get("agent_message")
                       or exec_result.get("stdout")
                       or exec_result.get("stderr")
                       or "Success"
                    )
                    messages.append({
                       "role": "tool",
                       "tool_call_id": tc.id,
                       "name": tool_name,
                       "content": tool_content
                   })
                
                if respond_to_user_called:
                    break
            
        except OrchestratorProcessError:
            raise
        except Exception as e:
            raise OrchestratorProcessError(
                "Agent B loop crashed",
                process="agent_b_loop",
                stage="execution",
                facts={
                    "steps_completed": steps_completed,
                    "steps_failed": steps_failed,
                    "total_steps_attempted": total_steps_attempted,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                },
                root_error=e
            )

        # Mark any remaining TODOs as completed if execution was successful
        if steps_failed == 0 and todos:
            for i in range(current_todo_index, len(todos)):
                if i < len(todos):
                    self.memory.record_todo_status(
                        cycle_id=cycle_id,
                        todo_index=i,
                        description=todos[i].get("description", "Unknown TODO"),
                        status="completed"
                    )

        narration_template: Optional[str] = None
        if respond_to_user_called and respond_segments:
            response_segments_filled = respond_segments
            final_text = final_response or self._segments_to_text(response_segments_filled)
            narration_template = final_text
        else:
            final_segments, narration_template, template_values = self._call_agent_b_final_narration(
                cycle_id=cycle_id,
                plan=plan,
                step_results=step_results,
                output_values=output_values,
                template_values=template_values,
                agent_b_notes=agent_b_notes,
                last_stdout=last_stdout or last_raw_stdout
            )

            if not final_segments and not narration_template:
                 if last_stdout or last_raw_stdout:
                     fallback_body = last_stdout or last_raw_stdout
                     final_segments = [
                         {"kind": "text", "text": "Task completed."},
                         {"kind": "block", "fence": "output", "body": fallback_body[:2000]}
                     ]
                     narration_template = "Task completed."

            response_segments_filled = final_segments or [
                {
                    "kind": "text",
                    "text": narration_template or final_response
                }
            ]
            response_segments_filled = self._sanitize_empty_segments(
                response_segments_filled,
                step_results
            )
            final_text = self._segments_to_text(response_segments_filled)

        total_steps = len(step_results)
        failed_steps = len([
            s for s in step_results
            if not s.get("success") and not s.get("informative_negative")
        ])
        completed_steps = total_steps - failed_steps

        # Determine overall success:
        # - If all steps succeeded: Success
        # - If some failed but were "informative negative" (e.g. checking if file exists): Success
        # - If respond_to_user completed successfully after intermediate failures: Success
        # - If we have a valid final response despite intermediate errors: Success (weak success)
        
        is_success = total_steps > 0 and failed_steps == 0
        
        # If we have a valid final response and at least one successful step, consider it a success
        # This handles cases where we retried or recovered.
        if not is_success and final_text and completed_steps > 0:
             is_success = True

        result_payload = {
            "steps_completed": completed_steps,
            "steps_failed": failed_steps,
            "total_steps": total_steps,
            "step_results": step_results,
            "success": is_success,
            "final_response": final_text,
            "narration_template": narration_template or final_response,
            "output_values": output_values,
            "output_value_types": output_value_types,
            "output_value_sources": output_value_sources,
            "template_values": template_values,
            "response_segments": response_segments_filled,
            "agent_b_final_raw": narration_template or final_response,
            "missing_segments": len(response_segments_filled) == 0
        }
        result_payload["respond_to_user_called"] = respond_to_user_called
        if respond_to_user_called:
            result_payload["response_policy_contract"] = respond_policy_contract
            result_payload["response_policy_summary"] = respond_policy_summary
            result_payload["response_attachments"] = respond_attachments or []

        return result_payload

    def _sanitize_empty_segments(
        self,
        segments: List[Dict[str, Any]],
        step_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Remove empty block segments and, if everything is empty, emit a short note
        explaining that the command produced no output.
        """
        if not segments:
            segments = []

        cleaned: List[Dict[str, Any]] = []
        empty_blocks = 0

        for seg in segments:
            if seg.get("kind") == "block":
                body = seg.get("body")
                if body is None or str(body).strip() == "":
                    empty_blocks += 1
                    continue
            cleaned.append(seg)

        if cleaned:
            return cleaned

        # Everything was empty; synthesize a note from the last step
        note = "Command produced no output (exit 0)."
        last_step = None
        if step_results:
            for s in reversed(step_results):
                # Prefer a step that actually ran a tool and returned 0
                if s.get("tool_name") and s.get("exit_code") in (0, None):
                    last_step = s
                    break
            if not last_step:
                last_step = step_results[-1]

        if last_step:
            cmd = None
            args = last_step.get("tool_args")
            if isinstance(args, dict):
                cmd = args.get("command")
            exit_code = last_step.get("exit_code")
            if cmd:
                note = f"Command `{cmd}` produced no output (exit {exit_code if exit_code is not None else 0})."
            elif last_step.get("tool_name"):
                note = f"Tool {last_step['tool_name']} produced no output (exit {exit_code if exit_code is not None else 0})."

        return [{"kind": "text", "text": note}]

    @staticmethod
    def _strip_null_values(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Remove keys with None values so optional arguments stay omitted."""
        if not isinstance(payload, dict):
            return payload
        return {key: value for key, value in payload.items() if value is not None}

    @staticmethod
    def _extract_schema_validation_error(
        exec_result: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """Detect schema validation failures in executor responses."""
        if not isinstance(exec_result, dict) or exec_result.get("success"):
            return None
        for field in ("error", "stderr", "result", "output_preview"):
            value = exec_result.get(field)
            if isinstance(value, str) and "Tool call validation failed" in value:
                return value
        return None

    def _execute_plan(
        self,
        cycle_id: str,
        query: str,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute plan via Agent B using native tool calling loop.
        """
        self._emit_status(
            "planning",
            {"route": "PLANNER", "stage": "agent_b_loop"}
        )
        return self._run_agent_b_tool_loop(cycle_id, query, plan)
    

    
    def _call_agent_b_final_narration(
        self,
        *,
        cycle_id: str,
        plan: Dict[str, Any],
        step_results: List[Dict[str, Any]],
        output_values: Dict[str, Any],
        template_values: Dict[str, Any],
        agent_b_notes: str,
        last_stdout: Optional[str]
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Dict[str, Any]]:
        """
        Run a final, tool-free Agent B pass to produce narration segments.
        Used only when respond_to_user was never called (legacy fallback for incomplete plans).
        """
        llm_client = LLMClient(
            config=self.config,
            role="B",
            memory=self.memory
        )

        # Build concise execution summary for context.
        def _tail(text: Optional[str], limit: int = 400):
            if not text:
                return ""
            return text if len(text) <= limit else text[-limit:]

        steps_summary = []
        for step in step_results:
            steps_summary.append({
                "id": step.get("step_id"),
                "tool": step.get("tool_name"),
                "command": (step.get("tool_args") or {}).get("command") if isinstance(step.get("tool_args"), dict) else None,
                "success": step.get("success"),
                "exit_code": step.get("exit_code"),
                "stdout_tail": _tail(step.get("stdout")),
                "stderr_tail": _tail(step.get("stderr")),
                "error": step.get("error")
            })

        steps_run = len(step_results)
        steps_successful = steps_run > 0 and all(
            step.get("success") or step.get("informative_negative")
            for step in step_results
        )
        summary_payload = {
            "intent": plan.get("intent"),
            "success_criteria": plan.get("success_criteria") or [],
            "overall_success": steps_successful,
            "steps_run": steps_run,
            "steps": steps_summary,
            "agent_notes": agent_b_notes,
        }
        if last_stdout:
            summary_payload["last_stdout_tail"] = _tail(last_stdout, 1500)

        system_prompt = (
            "You are Agent B preparing the final user-facing response.\n"
            "Tools are DISABLED for this call. Do not call any tools.\n"
            "Base your response ONLY on the structured execution_summary provided; do not invent results.\n"
            "Return a JSON OBJECT (no code fences) with this exact shape:\n"
            "{\n"
            "  \"segments\": [\n"
            "    {\"kind\": \"text\", \"text\": \"summary or notes\"},\n"
            "    {\"kind\": \"block\", \"fence\": \"output|json|bash|md|<lang>\", \"title\": \"optional\", \"body\": \"verbatim output\", \"truncated\": \"optional\"}\n"
            "  ],\n"
            "  \"template_values\": {\"optional_pre_resolved_scalars\": \"for reuse\"}\n"
            "}\n"
            "Always include `kind` for each segment; include `fence` and `body` for blocks."
        )
        user_prompt = json.dumps({"execution_summary": summary_payload}, ensure_ascii=False)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response = llm_client.call(
            messages=messages,
            tools=None,
            tool_choice=None,
            cycle_id=cycle_id,
            session_id=self.session_id,
            temperature=self.config.agent_b_temperature
        )

        if response["error"]:
            fallback = [
                {"kind": "text", "text": f"Error calling Agent B: {response['error']}"}
            ]
            return fallback, "Error", template_values

        msg = response["message"]
        content = msg.content or ""

        # With response_format json_object, content may already be a dict.
        if isinstance(content, dict):
            parsed_final = content
        else:
            parsed_final = json.loads(content)

        narration_template = parsed_final.get("narration_template")
        response_segments = parsed_final.get("segments")
        try:
            extra_template_values = parsed_final.get("template_values") or {}
            for key, value in extra_template_values.items():
                template_values[key] = value
        except Exception:
            response_segments = None

        response_segments_filled = response_segments or [
            {"kind": "text", "text": narration_template}
        ]

        return response_segments_filled, narration_template, template_values

    
    def _build_template_value_map(
        self,
        execution_result: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Combine typed template values with rendered fallbacks."""
        if not execution_result:
            return {}
        template_values = execution_result.get("template_values") or {}
        rendered_values = execution_result.get("output_values") or {}
        if not template_values:
            return rendered_values
        merged: Dict[str, Any] = dict(rendered_values)
        for key, value in template_values.items():
            if value is None and key in merged:
                continue
            merged[key] = value
        return merged

    def _render_narration_template(
        self,
        template: str,
        output_values: Dict[str, Any]
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Fill narration template with collected output values.

        Note: Kept for backward compatibility; returns a single text segment with the fully
        formatted string to avoid downstream rendering decisions.
        """
        formatter = Formatter()
        required_keys = {
            field_name
            for _, field_name, _, _ in formatter.parse(template)
            if field_name
        }
        missing = [key for key in required_keys if key not in output_values]
        if missing:
            raise KeyError(missing[0])
        rendered = template.format(**output_values)
        return rendered, [{"kind": "text", "text": rendered}]

    def _segments_to_text(self, segments: Optional[List[Dict[str, Any]]]) -> str:
        """Coalesce provided segments into a plain text response."""
        if not segments:
            return ""
        parts: List[str] = []
        for segment in segments:
            kind = segment.get("kind") or segment.get("type")
            if kind == "text":
                if segment.get("text") is not None:
                    parts.append(str(segment.get("text")))
                elif segment.get("content") is not None:
                    parts.append(str(segment.get("content")))
            elif kind == "block":
                fence = segment.get("fence") or segment.get("tag") or "output"
                body = segment.get("body") or segment.get("content") or ""
                title = segment.get("title")
                truncated = segment.get("truncated")
                block_text = ""
                if title:
                    block_text += f"{title}\n"
                block_text += f"```{fence}\n{body}\n```"
                if truncated:
                    block_text += f"\n{truncated}"
                parts.append(block_text)
            elif kind == "inline_value":
                if segment.get("text") is not None:
                    parts.append(str(segment.get("text")))
                elif segment.get("content") is not None:
                    parts.append(str(segment.get("content")))
                elif segment.get("value") is not None:
                    parts.append(str(segment.get("value")))
            else:
                content = segment.get("text") or segment.get("content")
                if content:
                    parts.append(str(content))
        return "\n".join([p for p in parts if p])

    def _json_safe(self, data: Any) -> Any:
        """Best-effort JSON-safe conversion, falling back to repr for unknown types."""
        try:
            return json.loads(json.dumps(data, default=self._json_default))
        except Exception as e:
            return {"serialization_error": str(e), "repr": repr(data)}

    @staticmethod
    def _json_default(obj: Any) -> Any:
        if isinstance(obj, bytes):
            return f"<bytes len={len(obj)}>"
        return repr(obj)

    def _append_last_stdout_placeholder(
        self,
        *,
        base_response: str,
        last_stdout: Optional[str]
    ) -> str:
        """Append a placeholder for the last stdout when it's multi-line."""
        if not last_stdout or "\n" not in last_stdout.rstrip("\n"):
            return base_response
        suffix = "{last_stdout}"
        if not base_response:
            return suffix
        if base_response.endswith("\n"):
            return base_response + suffix
        return base_response + "\n" + suffix

    def _build_last_stdout_value(
        self,
        last_stdout: Optional[str]
    ) -> Dict[str, Any]:
        """Provide output_values entry for the last stdout if multi-line."""
        if not last_stdout or "\n" not in last_stdout.rstrip("\n"):
            return {}
        return {"last_stdout": last_stdout}

    def _build_last_stdout_source(
        self,
        *,
        last_stdout: Optional[str],
        last_raw_stdout: Optional[str],
        tool_name: Optional[str],
        tool_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Source metadata for fenced rendering."""
        if not last_stdout or "\n" not in last_stdout.rstrip("\n"):
            return {}
        return {
            "last_stdout": {
                "tool_name": tool_name,
                "tool_args": tool_args or {},
                "stdout": last_stdout,
                "raw_stdout": last_raw_stdout if last_raw_stdout not in (None, "") else last_stdout
            }
        }

    def _build_agent_a_context_message(self, query: str) -> str:
        """Construct the context message for Agent A with recent conversations."""
        history = self.memory.get_chat_history(
            session_id=self.session_id,
            last_n=5
        )
        current_intent = self._normalize_intent_text(query)
        if not history:
            return f"Current intent: {current_intent}"

        header = (
            "These are the previous conversations with the user (oldest to newest)."
        )
        lines = [header]
        ordered_history = sorted(
            history,
            key=lambda entry: (
                entry.get("timestamp") or "",
                entry.get("id", 0)
            )
        )
        for idx, exchange in enumerate(ordered_history, 1):
            intent = self._normalize_intent_text(exchange.get("user_query", ""))
            timestamp = exchange.get("timestamp", "unknown time")
            cycle_id = exchange.get("cycle_id", "unknown-cycle")
            response = self._sanitize_history_response(exchange.get("agent_response"))
            lines.append(
                f"{idx}. User query: {intent} — Cycle {cycle_id} — {timestamp}; Agent A response: {response}"
            )
        lines.append(f"User is now asking: {current_intent}")
        return "\n".join(lines)

    def _normalize_intent_text(self, text: Optional[str]) -> str:
        """Normalize previous queries into an intent-style sentence."""
        if not text:
            return "(no intent captured)"
        collapsed = " ".join(text.strip().split())
        if not collapsed:
            return "(no intent captured)"
        if len(collapsed) == 1:
            return collapsed.upper()
        return collapsed[0].upper() + collapsed[1:]

    def _sanitize_history_response(self, text: Optional[str]) -> str:
        """Strip fenced blocks and condense whitespace for inline inclusion."""
        if not text:
            return "(no prior response captured)"
        cleaned = text.replace("```", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or "(no prior response captured)"

    def _should_use_no_output_message(
        self,
        *,
        fmt: Optional[str],
        rendered_value: Optional[str],
        parsed_value: Any,
        exec_result: Dict[str, Any]
    ) -> bool:
        """Return True if the tool succeeded but produced no stdout to render."""
        fmt_normalized = (fmt or "").strip().lower()
        if fmt_normalized in {"int", "float"}:
            return False
        exit_code = exec_result.get("exit_code")
        if exit_code not in (None, 0):
            return False
        stdout = exec_result.get("stdout")
        raw_stdout = exec_result.get("raw_stdout")
        stderr = exec_result.get("stderr")
        if any(text not in (None, "", " ") for text in (stdout, raw_stdout, stderr)):
            if fmt_normalized == "list":
                return isinstance(parsed_value, list) and len(parsed_value) == 0
            rendered = (rendered_value or "").strip()
            return rendered == ""
        return True

    def _format_no_output_message(
        self,
        *,
        step: Dict[str, Any],
        tool_args: Dict[str, Any]
    ) -> str:
        """Build a sentence explaining that a tool produced no output."""
        tool_name = step.get("tool_name", "tool")
        command = (tool_args.get("command") or "").strip()
        intent = (step.get("intent") or step.get("description") or "the requested action").strip()
        if intent:
            intent_text = intent
        else:
            intent_text = "the requested action"
        intent_clause = f" for \"{intent_text}\"" if intent_text else ""
        if command:
            return (
                f"Tool {tool_name} (command: {command}) completed with no output, "
                f"which I interpret as zero results{intent_clause}."
            )
        return (
            f"Tool {tool_name} completed with no output, which I interpret as zero results{intent_clause}."
        )

    def _build_output_snapshot(self, exec_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Build lightweight hashes/lengths for each channel so tool snapshots survive log truncation.
        """
        snapshot: Dict[str, Any] = {}
        channels = ("stdout", "stderr", "raw_stdout", "raw_stderr", "result")
        for channel in channels:
            data = exec_result.get(channel)
            if data in (None, "", b""):
                continue
            if isinstance(data, (dict, list)):
                try:
                    serialized = json.dumps(data, sort_keys=True)
                except Exception:
                    serialized = str(data)
            else:
                serialized = str(data)
            digest = hashlib.sha256(serialized.encode("utf-8", errors="ignore")).hexdigest()
            snapshot[channel] = {
                "len": len(serialized),
                "sha256": digest
            }
        artifact_path = exec_result.get("artifact_path")
        if artifact_path:
            snapshot["artifact_path"] = artifact_path
        exit_code = exec_result.get("exit_code")
        if exit_code is not None:
            snapshot["exit_code"] = exit_code
        return snapshot or None

    def _resolve_input_data_ref(
        self,
        ref: Dict[str, Any],
        tool_outputs_by_call_id: Dict[str, Dict[str, Any]]
    ) -> Tuple[bool, str]:
        """
        Resolve an input_data_ref spec into concrete stdin content.
        """
        if not isinstance(ref, dict):
            return False, "input_data_ref must be an object with tool_call_id"
        tool_call_id = ref.get("tool_call_id")
        if not tool_call_id:
            return False, "input_data_ref.tool_call_id is required"
        channel = ref.get("channel", "stdout")
        allowed_channels = {"stdout", "stderr", "result", "raw_stdout", "raw_stderr"}
        if channel not in allowed_channels:
            return False, f"input_data_ref.channel must be one of {sorted(allowed_channels)}"
        prior = tool_outputs_by_call_id.get(tool_call_id)
        if not prior:
            return False, f"Tool call '{tool_call_id}' not found. References must point to earlier tool_call_id values."
        data = prior.get(channel)
        if data in (None, ""):
            return False, f"No data available on channel '{channel}' for tool call '{tool_call_id}'"
        if isinstance(data, (dict, list)):
            try:
                data = json.dumps(data)
            except Exception:
                data = str(data)
        else:
            data = str(data)
        return True, data

    def _cache_execution(
        self,
        query: str,
        tool_name: str,
        tool_args: Dict[str, Any]
    ):
        """
        Cache successful execution for future CACHED route hits.
        
        Args:
            query: User query
            tool_name: Tool that was executed
            tool_args: Tool arguments
        """
        # Normalize intent (for FTS matching)
        # For MVP, just use query as-is
        # Phase 3+ can add intent normalization logic
        normalized_intent = query.lower().strip()
        
        self.memory.add_to_intention_cache(
            user_query=query,
            normalized_intent=normalized_intent,
            tool_name=tool_name,
            tool_args=tool_args,
            success=True
        )
    
    def _cycle_succeeded(self, route: Route, result: OrchestratorResult) -> bool:
        """
        Determine whether a cycle completed successfully.
        
        Only successful cycles should remain in Memory.
        """
        if result.error:
            return False
        
        route_value = route.value if isinstance(route, Route) else route
        exec_result = result.execution_result or {}
        
        if route_value in {Route.SHELL.value, Route.CACHED.value}:
            return bool(exec_result.get("success", False))
        
        if route_value == Route.PLANNER.value:
            if not exec_result:
                # Direct responses (no plan execution) count as success
                return True
            return bool(exec_result.get("success", False))
        
        # CHAT and other narrative-only routes succeed if no error was raised
        return True
    
    def close(self):
        """Clean up resources"""
        self.memory.close(force=True)

    def _record_cycle_failure(
        self,
        *,
        cycle_id: str,
        query: str,
        route_value: str,
        failure_context: Dict[str, Any],
        result: Optional[OrchestratorResult] = None
    ) -> None:
        """Persist an unsuccessful cycle snapshot for debugging."""
        try:
            self.memory.record_cycle_failure(
                cycle_id=cycle_id,
                session_id=self.session_id,
                query_text=query,
                process=failure_context.get("process"),
                route=route_value,
                stage=failure_context.get("stage"),
                error_type=failure_context.get("error_type"),
                error_code=failure_context.get("error_code"),
                error_message=failure_context.get("error_message") or "Cycle failed",
                facts=self._json_safe({
                    "context": failure_context.get("facts"),
                    "execution_result": getattr(result, "execution_result", None),
                    "agent_response": getattr(result, "agent_response", None)
                })
            )
        except Exception:
            # Never let failure logging explode user experience
            pass
