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
from orchestrator.prompts import (
    get_agent_a_system_prompt,
    get_agent_a_user_message,
    get_agent_b_system_prompt,
    get_agent_b_user_message,
    AGENT_A_TOOLS
)
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
            "Use the 'respond_to_user' tool to explain this to the user."
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
        llm_result = llm_client.call(
            messages=messages, 
            cycle_id=cycle_id, 
            temperature=self.config.agent_a_temperature,
            tools=AGENT_A_TOOLS
        )
        
        if llm_result["error"]:
            return f"[Agent A response failed: {llm_result['error']}]\n\n{user_context}"
        
        msg = llm_result["message"]
        content = msg.content or ""
        
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.function.name == "respond_to_user":
                    try:
                        args = json.loads(tc.function.arguments)
                        return args.get("response", "")
                    except Exception:
                        pass
        
        # Use PlanValidator to robustly parse Agent A's response
        validator = PlanValidator(available_tools=[])
        payload, _ = validator.validate_with_hints(content)
        
        if payload and isinstance(payload, dict) and "response" in payload:
            return payload["response"]
        
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
        4. Handle based on response type
        
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
                        response = {
                            "intent": args.get("intent"),
                            "success_criteria": args.get("success_criteria")
                        }
                    elif fname == "respond_to_user":
                        response = {
                            "response": args.get("response")
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
            # Failed - fallback to Agent A explanation
            self._emit_status(
                "preparing_response",
                {"route": "PLANNER", "error": True}
            )
            fallback_context = f"""The user asked: {query}

Agent A could not produce valid planner JSON.

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
            
            # If we successfully generated a fallback response, treat it as a valid direct response
            # This handles cases where Agent A outputs plain text instead of JSON but the content is valid
            return OrchestratorResult(
                cycle_id=cycle_id,
                route=Route.PLANNER.value,
                query=query,
                agent_response=agent_response,
                execution_result={"success": True, "fallback_triggered": True, "validation_error": last_error},
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
                current_step_id=execution_result.get("total_steps", 0) - 1
            )
            
            if execution_result["success"]:
                try:
                    self._emit_status(
                        "preparing_response",
                        {"route": "PLANNER", "success": True}
                    )
                    template_values = self._build_template_value_map(execution_result)
                    
                    # Use narration template from Agent B (in execution_result)
                    narration_template = execution_result.get("narration_template", "Task completed.")
                    
                    final_response, response_segments = self._render_narration_template(
                        template=narration_template,
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
                    f"Steps completed: {execution_result['steps_completed']}",
                    f"Steps failed: {execution_result['steps_failed']}",
                    f"Overall success flag: {execution_result['success']}",
                    "",
                    "Step details:"
                ]
                # ... (rest of error handling remains similar)
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
    
    def _get_tool_schemas(self, role: str) -> List[Dict[str, Any]]:
        """Get native tool schemas for the given role."""
        if role == "B":
            return [tool.schema for tool in TOOLS.values()]
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
        # We pass empty list to system prompt as we don't need schema injection
        system_prompt = get_agent_b_system_prompt([]) 
        user_msg = get_agent_b_user_message(plan)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]
        
        tools = self._get_tool_schemas("B")
        max_loops = 15
        
        step_results = []
        steps_completed = 0
        steps_failed = 0
        total_steps_attempted = 0
        
        llm_client = LLMClient(
            config=self.config,
            role="B",
            memory=self.memory
        )
        
        final_response = ""
        
        for loop_idx in range(max_loops):
             # Call LLM
             response = llm_client.call(
                 messages=messages,
                 tools=tools,
                 cycle_id=cycle_id,
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
                 break
             
             # Execute tools
             for tc in msg.tool_calls:
                 total_steps_attempted += 1
                 tool_name = tc.function.name
                 try:
                     args = json.loads(tc.function.arguments)
                 except json.JSONDecodeError:
                     args = {}
                 
                 # Log execution
                 step_id = len(step_results)
                 self._emit_status(
                    "executing", 
                    {
                        "route": "PLANNER", 
                        "step": step_id + 1, 
                        "tool": tool_name,
                        "command": args.get("command")
                    }
                 )
                 
                 self.memory.update_task_status(
                    cycle_id=cycle_id,
                    status="in_progress",
                    current_step_id=step_id
                 )

                 exec_result = self.tool_executor.execute(
                     tool_name=tool_name,
                     tool_args=args,
                     cycle_id=cycle_id,
                     step_id=step_id
                 )
                 
                 success = exec_result["success"]
                 if success:
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
                     "output": exec_result.get("stdout") or exec_result.get("stderr") or exec_result.get("result"),
                     "error": exec_result.get("error")
                 }
                 step_results.append(step_result)
                 
                 # Emit tool output event
                 self._emit_tool_output({
                    "route": "PLANNER",
                    "step_id": step_id,
                    "tool_name": tool_name,
                    "tool_args": args,
                    "stdout": exec_result.get("stdout"),
                    "stderr": exec_result.get("stderr"),
                    "success": success,
                    "events": exec_result.get("events")
                 })
                 
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
                    output_format=None,
                    parsed_outputs=exec_result.get("events"),
                    artifact_path=exec_result.get("artifact_path")
                 )

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
        
        return {
            "steps_completed": steps_completed,
            "steps_failed": steps_failed,
            "total_steps": total_steps_attempted,
            "step_results": step_results,
            "success": steps_failed == 0,
            "final_response": final_response,
            "narration_template": final_response, 
            "output_values": {} 
        }

    def _execute_plan(
        self,
        cycle_id: str,
        query: str,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute plan via Agent B using native tool calling loop.
        Replaces the old One-Shot Manifest approach.
        """
        self._emit_status(
            "planning",
            {"route": "PLANNER", "stage": "agent_b_loop"}
        )
        return self._run_agent_b_tool_loop(cycle_id, query, plan)
    

    
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
