"""
Orchestrator - Routerless dual-agent controller.

Coordinates: Agent A (plan/chat) → Agent B (commands) → Agent A narrator.
Every user query now enters through Agent A, which decides between
direct responses or structured plans that Agent B executes.
"""

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
from orchestrator.prompts import get_agent_a_system_prompt, get_agent_a_user_message, get_agent_b_system_prompt, get_agent_b_user_message
from orchestrator.metrics import CycleMetrics, StepMetrics, LLMMetrics, get_metrics
from orchestrator.system_context_builder import SystemContextBuilder
from orchestrator.plan_validator import PlanValidator, PlanValidationError
from orchestrator.plan_schema import detect_response_type
from orchestrator.output_parser import OutputParser, OutputParserError
from orchestrator.routes import Route
from tool_executor import ToolExecutor
from tools import TOOLS


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
    MAX_PLAN_RETRIES = 2  # Max attempts for Agent A to generate valid plan
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
        self.tool_executor = ToolExecutor()  # ToolExecutor does NOT access memory directly
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
                        "stage": "execution",
                        "error_type": "CycleFailure",
                        "error_message": result.error or "Cycle marked unsuccessful",
                        "payload": {
                            "execution_result": result.execution_result,
                            "agent_response": result.agent_response
                        }
                    }

            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)
                error_msg = f"Error during orchestration: {str(e)}"
                fallback_context = f"""The user asked: {query}

A fatal orchestrator error occurred before the cycle could finish.

Stage: orchestrator
Success: False

Details:
{error_msg}

Explain what happened and advise the user to retry after checking logs."""
                agent_response = self._call_agent_a_direct_response(
                    cycle_id=cycle_id,
                    user_context=fallback_context
                )

                result = OrchestratorResult(
                    cycle_id=cycle_id,
                    route=route_value,
                    query=query,
                    agent_response=agent_response,
                    latency_ms=latency_ms,
                    error=str(e),
                    response_segments=[{"type": "text", "content": agent_response}]
                )
                failure_context = {
                    "stage": "orchestrator",
                    "error_type": e.__class__.__name__,
                    "error_message": error_msg,
                    "payload": {
                        "traceback": traceback.format_exc()
                    }
                }
                cycle_success = False

        if session_activity_needed:
            self.memory.update_session_activity(self.session_id)

        if not cycle_success and cycle_id:
            if failure_context is None:
                failure_context = {
                    "stage": "execution",
                    "error_type": "CycleFailure",
                    "error_message": result.error if result else "Cycle failed",
                    "payload": {
                        "execution_result": getattr(result, "execution_result", None)
                    }
                }
            self._record_cycle_failure(
                cycle_id=cycle_id,
                query=query,
                route_value=route_value,
                failure_context=failure_context
            )

        return result

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
    
    def _call_agent_a_direct_response(
        self,
        cycle_id: str,
        user_context: str
    ) -> str:
        """
        Call Agent A once with the unified system prompt and ask for a direct response.
        
        Args:
            cycle_id: Cycle ID for logging
            user_context: Instructional payload describing what to explain to the user
        
        Returns:
            Final narration content extracted from Agent A's {"response": "..."} JSON payload
        """
        available_tools = sorted(TOOLS.keys())
        system_context = self.context_builder.build_for_role(
            role="A",
            session_id=self.session_id,
            tool_registry=TOOLS,
            shell_cwd=self._get_effective_shell_cwd()
        )
        system_prompt = system_context + "\n\n" + get_agent_a_system_prompt(available_tools)
        
        user_context_msg = (
            f"{user_context.strip()}\n\n"
            "Respond with a direct JSON object {\"response\": \"...\"} for the user. "
            "Do not propose a new tool plan."
        )
        
        user_prompt = get_agent_a_user_message(user_context_msg)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        llm_client = LLMClient(
            config=self.config,
            role="A",
            memory=self.memory
        )
        llm_result = llm_client.call(messages=messages, cycle_id=cycle_id, temperature=self.config.agent_a_temperature)
        
        if llm_result["error"]:
            return f"[Agent A response failed: {llm_result['error']}]\n\n{user_context}"
        
        content = llm_result["message"].content or ""
        try:
            # Use robust parsing to handle <think> tags or markdown blocks
            payload = self._parse_agent_b_json(content)
            if isinstance(payload, dict) and "response" in payload:
                return payload["response"]
        except (json.JSONDecodeError, ValueError):
            pass
        
        return content or user_context
    
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
        4. Retry if validation fails (up to MAX_PLAN_RETRIES)
        5. Handle based on response type
        
        Target: <2s response generation, 95%+ valid JSON on first attempt
        """
        self._emit_status("planning", {"route": "PLANNER", "stage": "agent_a"})
        # Get available tools for validation
        available_tools = sorted(TOOLS.keys())
        
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
        system_prompt = system_context + "\n\n" + get_agent_a_system_prompt(available_tools)
        
        # Build context for Agent A: include last 3 chat interactions (Chat→Planner handoff)
        context_msg = self._build_agent_a_context_message(query)
        
        user_message = get_agent_a_user_message(context_msg)
        
        # Retry loop
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        response = None
        last_error = None
        
        for attempt in range(self.MAX_PLAN_RETRIES + 1):
            self._emit_status(
                "planning",
                {"route": "PLANNER", "stage": "agent_a", "attempt": attempt + 1}
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
                temperature=self.config.agent_a_temperature
            )
            
            if llm_result["error"]:
                last_error = f"LLM call failed: {llm_result['error']}"
                break
            
            llm_response = llm_result["message"].content or ""
            
            # Validate response
            response, error_hint = validator.validate_with_hints(llm_response)
            
            if response:
                # Success!
                break
            
            # Validation failed
            last_error = error_hint
            
            # If this was the last attempt, give up
            if attempt >= self.MAX_PLAN_RETRIES:
                break
            
            # Add error feedback and retry
            messages.append({"role": "assistant", "content": llm_response})
            messages.append({
                "role": "user",
                "content": f"ERROR: {error_hint}\n\nPlease try again with a valid JSON response."
            })
        
        # Check if we got a valid response
        if not response:
            # Failed after all retries - fallback to Agent A explanation
            self._emit_status(
                "preparing_response",
                {"route": "PLANNER", "error": True}
            )
            fallback_context = f"""The user asked: {query}

Agent A could not produce valid planner JSON after {self.MAX_PLAN_RETRIES + 1} attempts.

Last validation hint:
{last_error}

Explain the failure to the user and suggest trying again.
IMPORTANT: Respond with a valid JSON object containing a single "response" key.
Example: {{"response": "I apologize, but I encountered an internal error..."}}"""
            
            # Re-inject history so Agent A knows what "it" refers to
            history_context = self._build_agent_a_context_message(query)
            full_fallback_context = f"{history_context}\n\n{fallback_context}"

            agent_response = self._call_agent_a_direct_response(
                cycle_id=cycle_id,
                user_context=full_fallback_context
            )
            
            return OrchestratorResult(
                cycle_id=cycle_id,
                route=Route.PLANNER.value,
                query=query,
                agent_response=agent_response,
                error=last_error,
                response_segments=[{"type": "text", "content": agent_response}]
            )
        
        # Detect response type and handle accordingly
        response_type = detect_response_type(response)
        
        if response_type == "response":
            agent_response = response["response"]
            response_segments = [{"type": "text", "content": agent_response}]
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
                status="done",
                current_step_id=len(plan["steps"]) - 1
            )
            
            if execution_result["success"]:
                try:
                    self._emit_status(
                        "preparing_response",
                        {"route": "PLANNER", "success": True}
                    )
                    template_values = self._build_template_value_map(execution_result)
                    final_response, response_segments = self._render_narration_template(
                        template=plan["narration_template"],
                        output_values=template_values
                    )
                    execution_result["narration_segments"] = response_segments
                except KeyError as e:
                    final_response = (
                        "[Template rendering failed: "
                        f"missing value for '{e.args[0]}']\n\n"
                        "Raw outputs:\n"
                        f"{execution_result.get('output_values', {})}"
                    )
                    response_segments = [{"type": "text", "content": final_response}]
                self.memory.save_chat_exchange(
                    session_id=self.session_id,
                    cycle_id=cycle_id,
                    user_query=query,
                    agent_response=final_response
                )
            else:
                self._emit_status(
                    "preparing_response",
                    {"route": "PLANNER", "success": False}
                )
                summary_lines = [
                    f"The user asked: {query}",
                    "",
                    "A multi-step plan was executed but did not fully succeed.",
                    f"Plan steps: {len(plan['steps'])}",
                    f"Steps completed: {execution_result['steps_completed']}",
                    f"Steps failed: {execution_result['steps_failed']}",
                    f"Overall success flag: {execution_result['success']}",
                    "",
                    "Step details:"
                ]
                for result in execution_result["step_results"]:
                    status = "PASS" if result["success"] else "FAIL"
                    summary_lines.append(
                        f"- [{status}] Step {result['step_id']}: {result['description']}"
                    )
                    if result["success"]:
                        output_preview = result["output"][:200]
                        if len(result["output"]) > 200:
                            output_preview += "..."
                        summary_lines.append(f"  Output preview: {output_preview}")
                    else:
                        summary_lines.append(f"  Error: {result['error']}")
                summary_lines.append("")
                summary_lines.append(
                    "Explain the outcome to the user and mention what succeeded or failed."
                )
                final_response = self._call_agent_a_direct_response(
                    cycle_id=cycle_id,
                    user_context="\n".join(summary_lines)
                )
                response_segments = [{"type": "text", "content": final_response}]

            execution_result["narration_segments"] = response_segments
            
            return OrchestratorResult(
                cycle_id=cycle_id,
                route=Route.PLANNER.value,
                query=query,
                agent_response=final_response,
                execution_result=execution_result,
                response_segments=response_segments
            )
        
        except Exception as e:
            # Mark as error
            self.memory.update_task_status(
                cycle_id=cycle_id,
                status="error",
                error_message=str(e)
            )
            
            # Call Agent A to explain error
            error_context = f"""The user asked: {query}

A failure occurred while executing the plan steps.

Error:
{str(e)}

Describe the failure and tell the user what to do next."""
            agent_response = self._call_agent_a_direct_response(
                cycle_id=cycle_id,
                user_context=error_context
            )
            
            return OrchestratorResult(
                cycle_id=cycle_id,
                route=Route.PLANNER.value,
                query=query,
                agent_response=agent_response,
                error=str(e),
                response_segments=[{"type": "text", "content": agent_response}]
            )
    
    def _execute_plan(
        self,
        cycle_id: str,
        query: str,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute plan steps sequentially via Agent B → ToolExecutor.
        
        Args:
            cycle_id: Cycle ID for logging
            query: User's original query
            plan: Validated plan dict (from Agent A with tool_name + intent)
        
        Returns:
            Dict with execution summary:
                - steps_completed: Number of steps completed
                - steps_failed: Number of steps failed
                - step_results: List of step execution results
                - success: Overall success flag
        
        Workflow:
        1. For each step in plan:
           a. Call Agent B (LLM) to generate precise tool_args from intent
           b. Substitute variables in tool_args ($PREVIOUS_OUTPUT, $STEP_N_OUTPUT)
           c. Execute via ToolExecutor
           d. Log to step_outputs table
           e. Update task_state current_step_id
           f. On failure: record error, continue
        2. Return execution summary
        """
        step_results = []
        steps_completed = 0
        steps_failed = 0
        output_values: Dict[str, str] = {}
        template_values: Dict[str, Any] = {}
        output_value_types: Dict[str, str] = {}
        output_value_sources: Dict[str, Dict[str, Any]] = {}
        total_steps = len(plan["steps"])
        
        for step_id, step in enumerate(plan["steps"]):
            # Update current step in task_state
            self.memory.update_task_status(
                cycle_id=cycle_id,
                status="in_progress",
                current_step_id=step_id
            )
            description = step.get("description", "")
            self._emit_status(
                "executing",
                {
                    "route": "PLANNER",
                    "step": step_id + 1,
                    "total_steps": total_steps,
                    "tool": step["tool_name"],
                    "description": description
                }
            )
            
            # Call Agent B to generate precise tool_args
            agent_b_result = self._call_agent_b(
                cycle_id=cycle_id,
                plan=plan,
                step_id=step_id,
                previous_results=step_results
            )
            
            step_output_format = agent_b_result.get("output_format") or {}
            
            if not agent_b_result["success"]:
                # Agent B failed to generate valid tool_args
                step_result = {
                    "step_id": step_id,
                    "tool_name": step["tool_name"],
                    "tool_args": {},
                    "description": description,
                    "success": False,
                    "output": "",
                    "exit_code": None,
                    "error": agent_b_result["error"]
                }
                step_results.append(step_result)
                steps_failed += 1
                error_text = agent_b_result.get("error", "Agent B failed to generate tool_args")
                
                # CRITICAL: Persist Agent B failure to step_outputs so it's visible in debugging
                # (Previously these failures were never saved, causing them to "disappear" from step_outputs)
                self.memory.save_step_output(
                    cycle_id=cycle_id,
                    step_id=step_id,
                    tool_name=step["tool_name"],
                    tool_args={},
                    success=False,
                    exit_code=None,
                    output_preview=error_text[:1000],
                    stdout=None,
                    stderr=error_text,
                    raw_stdout=None,
                    raw_stderr=error_text,
                    output_format=step_output_format,
                    parsed_outputs=None,
                    artifact_path=None
                )
                continue
            
            tool_args = agent_b_result["tool_args"]
            
            # Substitute variables in tool_args
            tool_args = self._substitute_step_variables(
                tool_args,
                step_results
            )
            if "command" in tool_args:
                self._emit_status(
                    "executing",
                    {
                        "route": "PLANNER",
                        "step": step_id + 1,
                        "total_steps": total_steps,
                        "tool": step["tool_name"],
                        "description": description,
                        "command": tool_args.get("command")
                    }
                )
            
            # Execute step
            exec_result = self.tool_executor.execute(
                tool_name=step["tool_name"],
                tool_args=tool_args,
                cycle_id=cycle_id,
                step_id=step_id
            )
            
            parsed_outputs = None
            rendered_values = None
            parse_error = None
            if exec_result["success"] and step_output_format:
                try:
                    parsed_outputs, rendered_values = self.output_parser.parse(
                        output_format=step_output_format,
                        stdout=exec_result.get("stdout"),
                        raw_stdout=exec_result.get("raw_stdout")
                    )
                except OutputParserError as exc:
                    parse_error = str(exc)
            
            step_success = exec_result["success"] and parse_error is None
            step_output_value = exec_result.get("stdout") if exec_result["success"] else None
            if step_output_value is None:
                step_output_value = exec_result.get("result")
            step_result = {
                "step_id": step_id,
                "tool_name": step["tool_name"],
                "tool_args": tool_args,
                "description": description,
                "output_format": step_output_format,
                "success": step_success,
                "output": step_output_value,
                "stdout": exec_result.get("stdout"),
                "stderr": exec_result.get("stderr"),
                "raw_stdout": exec_result.get("raw_stdout"),
                "raw_stderr": exec_result.get("raw_stderr"),
                "exit_code": exec_result.get("exit_code"),
                "error": parse_error or exec_result.get("error")
            }
            step_results.append(step_result)
            self._emit_tool_output({
                "route": "PLANNER",
                "step_id": step_id,
                "total_steps": total_steps,
                "tool_name": step["tool_name"],
                "tool_args": tool_args,
                "command": tool_args.get("command"),
                "stdout": exec_result.get("stdout"),
                "stderr": exec_result.get("stderr"),
                "raw_stdout": exec_result.get("raw_stdout"),
                "raw_stderr": exec_result.get("raw_stderr"),
                "success": step_success,
                "exit_code": exec_result.get("exit_code"),
                "description": description
            })
            
            # Persist step output to database
            output_preview = exec_result.get("output_preview")
            if output_preview is None:
                result_text = exec_result.get("result")
                output_preview = result_text[:1000] if result_text else None
            self.memory.save_step_output(
                cycle_id=cycle_id,
                step_id=step_id,
                tool_name=step["tool_name"],
                tool_args=tool_args,
                success=step_success,
                exit_code=exec_result.get("exit_code"),
                output_preview=output_preview,
                stdout=exec_result.get("stdout"),
                stderr=exec_result.get("stderr"),
                raw_stdout=exec_result.get("raw_stdout"),
                raw_stderr=exec_result.get("raw_stderr"),
                output_format=step_output_format,
                parsed_outputs=parsed_outputs if step_success else None,
                artifact_path=None  # TODO: Implement artifact storage for large outputs
            )
            
            # Record step metrics
            output_size = len(exec_result["result"]) if exec_result["result"] else 0
            step_latency = exec_result.get("latency_ms", 0)
            step_metric = StepMetrics(
                step_id=step_id,
                tool_name=step["tool_name"],
                success=step_success,
                latency_ms=step_latency,
                output_size_bytes=output_size
            )
            if hasattr(self.memory, "record_step_metric"):
                self.memory.record_step_metric(
                    step_id=step_metric.step_id,
                    tool_name=step_metric.tool_name,
                    success=step_metric.success,
                    latency_ms=step_metric.latency_ms,
                    output_size_bytes=step_metric.output_size_bytes
                )
            else:
                metrics = get_metrics()
                metrics.record_step_metric(step_metric)
            
            if step_success:
                source_metadata = self._build_output_source_metadata(
                    step=step,
                    step_id=step_id,
                    description=description,
                    tool_args=tool_args,
                    exec_result=exec_result
                )
                if rendered_values:
                    parsed_for_step = parsed_outputs or {}
                    for key, value in rendered_values.items():
                        fmt = (step_output_format or {}).get(key, "str")
                        final_value = value
                        source_for_key = dict(source_metadata) if source_metadata else {}
                        typed_candidate = parsed_for_step.get(key)
                        if self._should_use_no_output_message(
                            fmt=fmt,
                            rendered_value=value,
                            parsed_value=parsed_for_step.get(key),
                            exec_result=exec_result
                        ):
                            final_value = self._format_no_output_message(
                                step=step,
                                tool_args=tool_args
                            )
                            source_for_key["no_output"] = True
                            typed_value_for_template = final_value
                        elif fmt in {"int", "float"} and typed_candidate is not None:
                            typed_value_for_template = typed_candidate
                        else:
                            typed_value_for_template = final_value
                        output_values[key] = final_value
                        output_value_types[key] = fmt
                        output_value_sources[key] = source_for_key
                        template_values[key] = typed_value_for_template
                elif not step_output_format:
                    recorded_keys = self._record_step_outputs(
                        step=step,
                        raw_output=exec_result.get("result"),
                        output_values=output_values
                    )
                    for key in recorded_keys:
                        output_value_types[key] = "str"
                        output_value_sources[key] = source_metadata
                        template_values[key] = output_values.get(key)
            
            if step_success:
                steps_completed += 1
            else:
                steps_failed += 1
                # For now, continue execution even on failure
                # Future: make this configurable per step or plan
        
        return {
            "steps_completed": steps_completed,
            "steps_failed": steps_failed,
            "total_steps": len(plan["steps"]),
            "step_results": step_results,
            "success": steps_failed == 0,
            "output_values": output_values,
            "template_values": template_values,
            "output_value_types": output_value_types,
            "output_value_sources": output_value_sources
        }
    
    def _call_agent_b(
        self,
        cycle_id: str,
        plan: Dict[str, Any],
        step_id: int,
        previous_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Call Agent B to generate precise tool_args for a step.
        
        Args:
            cycle_id: Cycle ID for logging
            plan: Complete plan from Agent A
            step_id: Current step index
            previous_results: Results from previous steps
        
        Returns:
            Dict with:
                - success: bool
                - tool_args: dict (if successful)
                - command: Optional[str]
                - output_format: dict mapping output_keys -> types
                - error: str (if failed)
        """
        # Get current step's tool name and schema
        current_step = plan["steps"][step_id]
        suggested_tool_name = current_step["tool_name"]
        
        # ARCHITECTURAL FIX: Give Agent B access to ALL tools, not just the one Agent A picked.
        # Agent B is the Engineer; if Agent A (Planner) picked the wrong tool (e.g. read_file for 2 files),
        # Agent B must be able to switch to a better tool (e.g. run_command).
        
        # We prioritize the suggested tool in the prompt, but provide the full registry.
        # For token efficiency, we could filter this, but for now we pass the full registry
        # so Agent B has the "generic" tools (run_command, write_file) available as fallbacks.
        tool_schemas = [t.schema for t in TOOLS.values()]
        
        # Build system context for Agent B
        system_context = self.context_builder.build_for_role(
            role="B",
            session_id=self.session_id,
            tool_registry=TOOLS,
            shell_cwd=self._get_effective_shell_cwd()
        )
        
        # Build Agent B prompt
        system_prompt = system_context + "\n\n" + get_agent_b_system_prompt()
        
        user_message = get_agent_b_user_message(
            plan=plan,
            current_step_id=step_id,
            previous_outputs=previous_results,
            tool_schemas=tool_schemas  # Pass ALL schemas
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # Call LLM in Agent B role
        llm_client = LLMClient(
            config=self.config,
            role="B",
            memory=self.memory
        )
        
        max_retries = 2
        current_try = 0
        
        while True:
            llm_result = llm_client.call(
                messages=messages,
                cycle_id=cycle_id,
                temperature=self.config.agent_b_temperature
            )
            
            if llm_result["error"]:
                return {
                    "success": False,
                    "tool_args": {},
                    "error": f"Agent B LLM call failed: {llm_result['error']}"
                }
            
            # Parse Agent B response
            response_text = llm_result["message"].content or ""
            
            try:
                response_json = self._parse_agent_b_json(response_text)
                
                # Allow Agent B to override the tool name
                # If response_json has "tool_name", use it. Otherwise default to plan's tool.
                selected_tool_name = response_json.get("tool_name", suggested_tool_name)
                
                # Validate the selected tool exists
                if selected_tool_name not in TOOLS:
                     raise ValueError(f"Agent B selected unknown tool '{selected_tool_name}'")

                # Update the step object temporarily for normalization (so it validates against the NEW tool)
                # We don't mutate the original plan, just the context for normalization
                step_context = current_step.copy()
                step_context["tool_name"] = selected_tool_name
                
                normalized = self._normalize_agent_b_payload(
                    step=step_context,
                    step_id=step_id,
                    payload=response_json
                )
                
                # Return the selected tool name so the executor knows what to run
                return {
                    "success": True,
                    "tool_name": selected_tool_name, # Pass back the actual tool used
                    "tool_args": normalized["tool_args"],
                    "command": normalized.get("command"),
                    "output_format": normalized.get("output_format", {}),
                    "error": None
                }
            except (json.JSONDecodeError, ValueError) as e:
                current_try += 1
                if current_try > max_retries:
                    return {
                        "success": False,
                        "tool_args": {},
                        "output_format": {},
                        "command": None,
                        "error": str(e)
                    }
                
                # Add error to history and retry
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": f"Error: {str(e)}\nPlease fix the JSON payload."})
    
    def _parse_agent_b_json(self, text: str) -> Dict[str, Any]:
        """
        Parse JSON from Agent B response using STRICT protocol.
        
        Protocol:
        1. The payload MUST be wrapped in a ```json ... ``` code block.
        2. If multiple blocks exist, the LAST one is used (allows for scratchpad blocks).
        3. <think> blocks are explicitly ignored.
        
        Args:
            text: Raw Agent B response
        
        Returns:
            Parsed JSON dict
        
        Raises:
            ValueError: If no valid JSON block is found
            json.JSONDecodeError: If JSON is malformed
        """
        import json
        
        # 1. Remove <think> blocks to prevent false positives
        clean_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # 2. Extract all ```json blocks
        # Regex finds content between ```json and ```
        matches = re.findall(r'```json\s*(.*?)\s*```', clean_text, re.DOTALL)
        
        if not matches:
            # Fallback: Look for generic ``` blocks if json tag was missed
            matches = re.findall(r'```\s*(\{.*?\})\s*```', clean_text, re.DOTALL)
            
        if not matches:
            # STRICT MODE: Do not attempt to find raw JSON outside blocks.
            # This prevents capturing "I will use {"foo": "bar"}" from reasoning text.
            raise ValueError("Protocol Violation: No ```json code block found in response.")
            
        # 3. Use the LAST block (allows Agent to refine its thought in previous blocks)
        json_text = matches[-1].strip()
        
        return json.loads(json_text)

    def _normalize_agent_b_payload(
        self,
        step: Dict[str, Any],
        step_id: int,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize Agent B payload into {command, tool_args, output_format}."""
        tool_name = step["tool_name"]
        is_shell_tool = tool_name in self.SHELL_TOOLS
        output_format = payload.get("output_format")
        
        if is_shell_tool:
            command = payload.get("command")
            if not command and isinstance(payload.get("tool_args"), dict):
                command = payload["tool_args"].get("command")
            if not isinstance(command, str) or not command.strip():
                raise ValueError(
                    f"Agent B must provide a 'command' for shell tool step {step_id}"
                )
            normalized_tool_args = {"command": command.strip()}
        else:
            tool_args = payload.get("tool_args")
            if not isinstance(tool_args, dict):
                raise ValueError(
                    f"Agent B must provide 'tool_args' dict for tool '{tool_name}' (step {step_id})"
                )
            normalized_tool_args = tool_args
            command = tool_args.get("command") if isinstance(tool_args.get("command"), str) else None
        
        normalized_output_format = self._validate_agent_b_output_format(
            step=step,
            step_id=step_id,
            output_format=output_format
        )
        
        return {
            "command": command.strip() if isinstance(command, str) else None,
            "tool_args": normalized_tool_args,
            "output_format": normalized_output_format
        }

    def _validate_agent_b_output_format(
        self,
        step: Dict[str, Any],
        step_id: int,
        output_format: Optional[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Validate and normalize Agent B output_format payload."""
        expected_keys = step.get("output_keys") or []
        
        if not expected_keys:
            return {}
        
        if not isinstance(output_format, dict):
            raise ValueError(
                f"Agent B must specify 'output_format' for step {step_id} with keys {expected_keys}"
            )
        
        normalized: Dict[str, str] = {}
        missing_keys = [key for key in expected_keys if key not in output_format]
        if missing_keys:
            raise ValueError(
                f"Agent B output_format missing keys {missing_keys} for step {step_id}"
            )
        
        for key, value in output_format.items():
            if key not in expected_keys:
                raise ValueError(
                    f"Agent B output_format provided unexpected key '{key}' for step {step_id}"
                )
            if not isinstance(value, str):
                raise ValueError(
                    f"Agent B output_format for key '{key}' must be string in step {step_id}"
                )
            fmt = value.strip().lower()
            if fmt not in self.SUPPORTED_OUTPUT_FORMAT_TYPES:
                raise ValueError(
                    f"Unsupported output_format type '{value}' for key '{key}' (step {step_id})"
                )
            normalized[key] = fmt
        
        return normalized
    
    def _substitute_step_variables(
        self,
        tool_args: Dict[str, Any],
        previous_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Substitute variables in tool arguments using safe recursive dict walk.
        
        Supports:
        - $PREVIOUS_OUTPUT: Output from last step
        - $STEP_N_OUTPUT: Output from step N (0-indexed)
        
        Args:
            tool_args: Tool arguments dict (may contain variable references)
            previous_results: List of previous step results
        
        Returns:
            Tool arguments with variables substituted
        """
        import re
        import copy
        
        def substitute_in_value(value: Any) -> Any:
            """Recursively substitute variables in a value (str, dict, list, or primitive)"""
            if isinstance(value, str):
                # Substitute $PREVIOUS_OUTPUT
                if previous_results and "$PREVIOUS_OUTPUT" in value:
                    last_output = previous_results[-1]["output"]
                    value = value.replace("$PREVIOUS_OUTPUT", last_output)
                
                # Substitute $STEP_N_OUTPUT
                for match in re.finditer(r'\$STEP_(\d+)_OUTPUT', value):
                    step_num = int(match.group(1))
                    if step_num < len(previous_results):
                        step_output = previous_results[step_num]["output"]
                        value = value.replace(match.group(0), step_output)
                
                return value
            
            elif isinstance(value, dict):
                # Recursively process dict
                return {k: substitute_in_value(v) for k, v in value.items()}
            
            elif isinstance(value, list):
                # Recursively process list
                return [substitute_in_value(item) for item in value]
            
            else:
                # Primitive type (int, float, bool, None) - return as-is
                return value
        
        # Deep copy to avoid mutating original
        result = copy.deepcopy(tool_args)
        
        # Recursively substitute variables
        return substitute_in_value(result)
    
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
        """Fill narration template with collected output values and segments."""
        formatter = Formatter()
        required_keys = set()
        segments: List[Dict[str, Any]] = []
        for literal, field_name, _, _ in formatter.parse(template):
            if literal:
                segments.append({"type": "text", "content": literal})
            if field_name:
                required_keys.add(field_name)
                segments.append({"type": "output", "key": field_name})
        missing = [key for key in required_keys if key not in output_values]
        if missing:
            raise KeyError(missing[0])
        return template.format(**output_values), segments

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

    def _record_step_outputs(
        self,
        step: Dict[str, Any],
        raw_output: Optional[str],
        output_values: Dict[str, str]
    ) -> List[str]:
        """
        Map each output key from the step to the raw output.
        
        Returns the list of keys that were populated.
        """
        output_text = raw_output or ""
        recorded: List[str] = []
        for key in step.get("output_keys", []):
            normalized = key.strip()
            if not normalized:
                continue
            output_values[normalized] = output_text
            recorded.append(normalized)
        return recorded

    def _build_output_source_metadata(
        self,
        *,
        step: Dict[str, Any],
        step_id: int,
        description: str,
        tool_args: Dict[str, Any],
        exec_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Capture metadata for output rendering in the REPL."""
        return {
            "step_id": step_id,
            "tool_name": step.get("tool_name"),
            "description": description,
            "command": tool_args.get("command"),
            "tool_args": tool_args,
            "stdout": exec_result.get("stdout"),
            "stderr": exec_result.get("stderr"),
            "raw_stdout": exec_result.get("raw_stdout"),
            "raw_stderr": exec_result.get("raw_stderr"),
            "exit_code": exec_result.get("exit_code"),
        }

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
        failure_context: Dict[str, Any]
    ) -> None:
        """Persist an unsuccessful cycle snapshot for debugging."""
        try:
            self.memory.record_cycle_failure(
                cycle_id=cycle_id,
                session_id=self.session_id,
                query_text=query,
                route=route_value,
                stage=failure_context.get("stage"),
                error_type=failure_context.get("error_type"),
                error_message=failure_context.get("error_message") or "Cycle failed",
                payload=failure_context.get("payload")
            )
        except Exception:
            # Never let failure logging explode user experience
            pass
