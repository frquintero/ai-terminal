"""
Orchestrator - Main controller for v2.0 multi-role architecture

Coordinates: Router → Execution → Agent C narrator
Implements CHAT, SHELL, and CACHED routes (Phase 2)
PLANNER route implemented in Phase 3
"""

import os
import time
import uuid
from typing import Any, Dict, List, Optional

from config import Config
from llm_client import LLMClient
from memory.api import Memory
from orchestrator.prompts import get_agent_a_prompt, get_agent_b_prompt, get_agent_c_prompt
from orchestrator.metrics import RouteMetrics, StepMetrics, LLMMetrics, get_metrics
from orchestrator.system_context_builder import SystemContextBuilder
from tools import get_tool_schemas
from orchestrator.plan_validator import PlanValidator, PlanValidationError
from router.router import Router
from router.rules import Route
from tool_executor import ToolExecutor
from tools import TOOLS


class OrchestratorResult:
    """Result of orchestration cycle"""
    
    def __init__(
        self,
        cycle_id: str,
        route: str,
        query: str,
        agent_c_response: str,
        execution_result: Optional[Dict[str, Any]] = None,
        latency_ms: int = 0,
        error: Optional[str] = None
    ):
        self.cycle_id = cycle_id
        self.route = route
        self.query = query
        self.agent_c_response = agent_c_response
        self.execution_result = execution_result
        self.latency_ms = latency_ms
        self.error = error
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for testing/logging"""
        return {
            "cycle_id": self.cycle_id,
            "route": self.route,
            "query": self.query,
            "agent_c_response": self.agent_c_response,
            "execution_result": self.execution_result,
            "latency_ms": self.latency_ms,
            "error": self.error
        }


class Orchestrator:
    """
    Main orchestrator for v2.0 multi-role architecture.
    
    Entry point: handle_query(query) → OrchestratorResult
    
    Workflow:
    1. Create cycle_id and log to Memory
    2. Router.classify(query) → route decision
    3. Route-specific handler (CHAT/SHELL/CACHED/PLANNER)
    4. Agent C narrator (universal final step)
    5. Return OrchestratorResult
    """
    
    # Constants
    MAX_PLAN_RETRIES = 2  # Max attempts for Agent A to generate valid plan
    
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
        self.router = Router(self.memory)
        self.tool_executor = ToolExecutor(memory=self.memory)
        self.context_builder = SystemContextBuilder(memory=self.memory)
        
        # Session management
        self.session_id = self._initialize_session()
    
    def _initialize_session(self) -> str:
        """Create or retrieve session"""
        # For MVP, create new session each time
        # Phase 3+ will support session persistence
        session_id = str(uuid.uuid4())
        
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
    
    def handle_query(self, query: str) -> OrchestratorResult:
        """
        Main entry point - orchestrate query through full pipeline.
        
        Args:
            query: User query text
        
        Returns:
            OrchestratorResult with route, response, and metadata
        
        Workflow:
        1. Create cycle_id
        2. Router classification
        3. Route-specific execution
        4. Agent C narrator
        5. Update Memory and return result
        """
        start_time = time.time()
        
        # Step 1: Create cycle
        cycle_id = self.memory.create_cycle(
            session_id=self.session_id,
            query=query
        )
        
        # Step 2: Router classification
        router_result = self.router.classify(query)
        self.router.log_decision(cycle_id, query, router_result)
        
        # Step 3: Route-specific execution
        try:
            if router_result.route == Route.CHAT:
                result = self._handle_chat_route(cycle_id, query)
            elif router_result.route == Route.SHELL:
                result = self._handle_shell_route(cycle_id, query)
            elif router_result.route == Route.CACHED:
                result = self._handle_cached_route(cycle_id, query, router_result)
            elif router_result.route == Route.PLANNER:
                result = self._handle_planner_route(cycle_id, query)
            else:
                raise ValueError(f"Unknown route: {router_result.route}")
            
            # Calculate total latency
            result.latency_ms = int((time.time() - start_time) * 1000)
            
            # Record metrics
            metrics = get_metrics()
            metrics.record_route_metric(RouteMetrics(
                route=router_result.route.value,
                confidence=router_result.confidence,
                latency_ms=result.latency_ms,
                cache_hit=hasattr(router_result, 'cache_hit') and router_result.cache_hit is not None,
                interactive=self.router.rule_engine.is_interactive_command(query)
            ))
            
            # Update session activity
            self.memory.update_session_activity(self.session_id)
            
            return result
        
        except Exception as e:
            # Error handling - still call Agent C to explain
            latency_ms = int((time.time() - start_time) * 1000)
            
            error_msg = f"Error during orchestration: {str(e)}"
            agent_c_response = self._call_agent_c_narrator(
                cycle_id=cycle_id,
                query=query,
                tool_name="orchestrator",
                tool_output=error_msg,
                success=False
            )
            
            return OrchestratorResult(
                cycle_id=cycle_id,
                route=router_result.route.value,
                query=query,
                agent_c_response=agent_c_response,
                latency_ms=latency_ms,
                error=str(e)
            )
    
    def _handle_chat_route(self, cycle_id: str, query: str) -> OrchestratorResult:
        """
        CHAT route: Simple informational query → Agent C
        
        Workflow:
        1. Retrieve last 10 chat exchanges from Memory
        2. Check for recent task completions (Planner→Chat handoff)
        3. Call LLM in Agent C (chat mode) with full context
        4. Log to chat_history
        5. Return result
        """
        # Get chat history for context
        chat_history = self.memory.get_chat_history(
            session_id=self.session_id,
            last_n=10
        )
        
        # Build system context for Agent C
        system_context = self.context_builder.build_for_role(
            role="C",
            session_id=self.session_id,
            tool_registry=TOOLS,
            shell_cwd=os.getcwd()
        )
        
        # Build messages for Agent C
        messages = [
            {"role": "system", "content": system_context + "\n\n" + get_agent_c_prompt("chat")}
        ]
        
        # Planner→Chat handoff: Include summary of most recent completed task if available
        recent_plan = self.memory.get_recent_completed_plan(
            session_id=self.session_id,
            last_n=1
        )
        
        if recent_plan and len(recent_plan) > 0:
            # Add task summary to context
            task_summary = recent_plan[0]
            task_context = f"\n[Context: User recently completed a task: {task_summary.get('query', 'task')}']\n"
            messages[0]["content"] = messages[0]["content"] + task_context
        
        # Add previous chat context
        for exchange in chat_history:
            messages.append({"role": "user", "content": exchange["user_query"]})
            messages.append({"role": "assistant", "content": exchange["agent_response"]})
        
        # Add current query
        messages.append({"role": "user", "content": query})
        
        # Call LLM in Agent C role
        llm_client = LLMClient(
            config=self.config,
            role="C",
            memory=self.memory
        )
        
        llm_result = llm_client.call(
            messages=messages,
            cycle_id=cycle_id
        )
        
        if llm_result["error"]:
            raise RuntimeError(f"LLM call failed: {llm_result['error']}")
        
        agent_c_response = llm_result["message"].content or ""
        
        # Save to chat_history
        self.memory.save_chat_exchange(
            session_id=self.session_id,
            cycle_id=cycle_id,
            user_query=query,
            agent_response=agent_c_response
        )
        
        return OrchestratorResult(
            cycle_id=cycle_id,
            route="CHAT",
            query=query,
            agent_c_response=agent_c_response,
            execution_result=None
        )
    
    def _handle_shell_route(self, cycle_id: str, query: str) -> OrchestratorResult:
        """
        SHELL route: Direct shell command execution → Agent C narrator
        
        Workflow:
        1. Detect if interactive command (vim, top, etc.) or regular command
        2. Execute via appropriate tool (run_interactive for TTY commands, run_command for regular)
        3. Call Agent C narrator to present results
        4. Cache successful execution for future CACHED hits
        5. Return result
        
        Target: <500ms end-to-end for non-interactive commands
        """
        # Detect if this is an interactive command requiring TTY
        is_interactive = self.router.rule_engine.is_interactive_command(query)
        tool_name = "run_interactive" if is_interactive else "run_command"
        
        # Execute command directly
        exec_result = self.tool_executor.execute(
            tool_name=tool_name,
            tool_args={"command": query},
            cycle_id=cycle_id,
            step_id=0  # Single-step execution
        )
        
        # Call Agent C narrator
        # For interactive commands, the output is minimal (exit status message)
        # since the user was controlling the program directly
        agent_c_response = self._call_agent_c_narrator(
            cycle_id=cycle_id,
            query=query,
            tool_name=tool_name,
            tool_output=exec_result["result"],
            success=exec_result["success"],
            exit_code=exec_result.get("exit_code")
        )
        
        # Cache successful execution for future hits (only for non-interactive commands)
        # Interactive commands are typically user-controlled and may not be repeatable
        if exec_result["success"] and not is_interactive:
            self._cache_execution(
                query=query,
                tool_name=tool_name,
                tool_args={"command": query}
            )
        
        return OrchestratorResult(
            cycle_id=cycle_id,
            route="SHELL",
            query=query,
            agent_c_response=agent_c_response,
            execution_result=exec_result
        )
    
    def _handle_cached_route(
        self,
        cycle_id: str,
        query: str,
        router_result
    ) -> OrchestratorResult:
        """
        CACHED route: Retrieve cached tool + Execute → Agent C narrator
        
        Workflow:
        1. Retrieve cached tool/args from router_result
        2. Execute via ToolExecutor
        3. Call Agent C narrator
        4. Update cache usage counter
        5. Return result
        
        Target: <200ms end-to-end (zero LLM overhead for execution)
        """
        cache_hit = router_result.cache_hit
        
        if not cache_hit:
            raise ValueError("CACHED route requires cache_hit in router_result")
        
        # Execute cached tool
        exec_result = self.tool_executor.execute(
            tool_name=cache_hit.tool_name,
            tool_args=cache_hit.tool_args,
            cycle_id=cycle_id,
            step_id=0
        )
        
        # Call Agent C narrator
        agent_c_response = self._call_agent_c_narrator(
            cycle_id=cycle_id,
            query=query,
            tool_name=cache_hit.tool_name,
            tool_output=exec_result["result"],
            success=exec_result["success"],
            exit_code=exec_result.get("exit_code")
        )
        
        # Update cache usage counter
        self.memory.update_cache_usage(cache_hit.cache_id)
        
        return OrchestratorResult(
            cycle_id=cycle_id,
            route="CACHED",
            query=query,
            agent_c_response=agent_c_response,
            execution_result={
                **exec_result,
                "cache_hit": cache_hit.to_dict()
            }
        )
    
    def _call_agent_c_narrator(
        self,
        cycle_id: str,
        query: str,
        tool_name: str,
        tool_output: str,
        success: bool,
        exit_code: Optional[int] = None
    ) -> str:
        """
        Call Agent C in narrator mode to present tool results conversationally.
        
        Args:
            cycle_id: Cycle ID for logging
            query: User's original query
            tool_name: Tool that was executed
            tool_output: Raw tool output
            success: Whether execution succeeded
            exit_code: Exit code (if applicable)
        
        Returns:
            Conversational response from Agent C
        """
        # Build context message for Agent C
        context = f"""User Query: {query}

Tool Executed: {tool_name}
Success: {success}
"""
        
        if exit_code is not None:
            context += f"Exit Code: {exit_code}\n"
        
        context += f"\nTool Output:\n{tool_output}"
        
        # Build system context for Agent C
        system_context = self.context_builder.build_for_role(
            role="C",
            session_id=self.session_id,
            tool_registry=TOOLS,
            shell_cwd=os.getcwd()
        )
        
        messages = [
            {"role": "system", "content": system_context + "\n\n" + get_agent_c_prompt("narrator")},
            {"role": "user", "content": context}
        ]
        
        # Call LLM in Agent C role
        llm_client = LLMClient(
            config=self.config,
            role="C",
            memory=self.memory
        )
        
        llm_result = llm_client.call(
            messages=messages,
            cycle_id=cycle_id
        )
        
        if llm_result["error"]:
            # Fallback to raw output if Agent C fails
            return f"[Agent C narrator failed: {llm_result['error']}]\n\n{tool_output}"
        
        return llm_result["message"].content or tool_output
    
    def _handle_planner_route(self, cycle_id: str, query: str) -> OrchestratorResult:
        """
        PLANNER route: Multi-step task planning via Agent A
        
        Workflow:
        1. Retrieve Chat→Planner context (last 3 chat interactions)
        2. Call Agent A (Planner) to generate JSON plan with context
        3. Validate plan structure and tools
        4. Retry if validation fails (up to MAX_PLAN_RETRIES)
        5. Save plan to task_state table
        6. Return stub result (Phase 4 will implement execution)
        
        Target: <2s plan generation, 95%+ valid JSON on first attempt
        """
        # Get available tools for validation
        available_tools = sorted(TOOLS.keys())
        
        # Create validator
        validator = PlanValidator(available_tools=available_tools)
        
        # Build system context for Agent A
        system_context = self.context_builder.build_for_role(
            role="A",
            session_id=self.session_id,
            tool_registry=TOOLS,
            shell_cwd=os.getcwd()
        )
        
        # Build Agent A prompt
        system_prompt = system_context + "\n\n" + get_agent_a_prompt(available_tools)
        
        # Build context for Agent A: include last 3 chat interactions (Chat→Planner handoff)
        context_msg = query
        
        chat_history = self.memory.get_chat_history(
            session_id=self.session_id,
            last_n=3
        )
        
        if chat_history:
            # Prepend previous chat context to help Agent A understand user intent
            context_lines = ["Context from previous conversation:"]
            for exchange in chat_history:
                context_lines.append(f"User: {exchange['user_query']}")
                context_lines.append(f"Assistant: {exchange['agent_response']}")
            context_lines.append(f"\nNow, the user asks: {query}")
            context_msg = "\n".join(context_lines)
        
        # Retry loop
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_msg}
        ]
        
        plan = None
        last_error = None
        
        for attempt in range(self.MAX_PLAN_RETRIES + 1):
            # Call LLM in Agent A role
            llm_client = LLMClient(
                config=self.config,
                role="A",
                memory=self.memory
            )
            
            llm_result = llm_client.call(
                messages=messages,
                cycle_id=cycle_id
            )
            
            if llm_result["error"]:
                last_error = f"LLM call failed: {llm_result['error']}"
                break
            
            llm_response = llm_result["message"].content or ""
            
            # Validate plan
            plan, error_hint = validator.validate_with_hints(llm_response)
            
            if plan:
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
                "content": f"ERROR: {error_hint}\n\nPlease try again with a valid JSON plan."
            })
        
        # Check if we got a valid plan
        if not plan:
            # Failed after all retries - fallback to Agent C explanation
            agent_c_response = self._call_agent_c_narrator(
                cycle_id=cycle_id,
                query=query,
                tool_name="agent_a_planner",
                tool_output=f"Failed to generate valid plan after {self.MAX_PLAN_RETRIES + 1} attempts.\n\n{last_error}",
                success=False
            )
            
            return OrchestratorResult(
                cycle_id=cycle_id,
                route="PLANNER",
                query=query,
                agent_c_response=agent_c_response,
                error=last_error
            )
        
        # Save plan to task_state
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
            
            # Call Agent C summarizer to generate final response
            agent_c_response = self._call_agent_c_summarizer(
                cycle_id=cycle_id,
                query=query,
                plan=plan,
                execution_result=execution_result
            )
            
            return OrchestratorResult(
                cycle_id=cycle_id,
                route="PLANNER",
                query=query,
                agent_c_response=agent_c_response,
                execution_result=execution_result
            )
        
        except Exception as e:
            # Mark as error
            self.memory.update_task_status(
                cycle_id=cycle_id,
                status="error",
                error_message=str(e)
            )
            
            # Call Agent C to explain error
            agent_c_response = self._call_agent_c_narrator(
                cycle_id=cycle_id,
                query=query,
                tool_name="plan_executor",
                tool_output=f"Execution failed: {str(e)}",
                success=False
            )
            
            return OrchestratorResult(
                cycle_id=cycle_id,
                route="PLANNER",
                query=query,
                agent_c_response=agent_c_response,
                error=str(e)
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
        
        # Get tool schemas for Agent B
        tool_schemas = get_tool_schemas()
        
        for step_id, step in enumerate(plan["steps"]):
            # Update current step in task_state
            self.memory.update_task_status(
                cycle_id=cycle_id,
                status="in_progress",
                current_step_id=step_id
            )
            
            # Call Agent B to generate precise tool_args
            agent_b_result = self._call_agent_b(
                cycle_id=cycle_id,
                plan=plan,
                step_id=step_id,
                previous_results=step_results,
                tool_schemas=tool_schemas
            )
            
            if not agent_b_result["success"]:
                # Agent B failed to generate valid tool_args
                step_result = {
                    "step_id": step_id,
                    "tool_name": step["tool_name"],
                    "tool_args": {},
                    "description": step["description"],
                    "success": False,
                    "output": "",
                    "exit_code": None,
                    "error": agent_b_result["error"]
                }
                step_results.append(step_result)
                steps_failed += 1
                continue
            
            tool_args = agent_b_result["tool_args"]
            
            # Substitute variables in tool_args
            tool_args = self._substitute_step_variables(
                tool_args,
                step_results
            )
            
            # Execute step
            exec_result = self.tool_executor.execute(
                tool_name=step["tool_name"],
                tool_args=tool_args,
                cycle_id=cycle_id,
                step_id=step_id
            )
            
            # Record result
            step_result = {
                "step_id": step_id,
                "tool_name": step["tool_name"],
                "tool_args": tool_args,
                "description": step["description"],
                "success": exec_result["success"],
                "output": exec_result["result"],
                "exit_code": exec_result.get("exit_code"),
                "error": exec_result.get("error")
            }
            step_results.append(step_result)
            
            # Persist step output to database
            output_preview = exec_result["result"][:1000] if exec_result["result"] else None
            self.memory.save_step_output(
                cycle_id=cycle_id,
                step_id=step_id,
                tool_name=step["tool_name"],
                tool_args=tool_args,
                success=exec_result["success"],
                exit_code=exec_result.get("exit_code"),
                output_preview=output_preview,
                artifact_path=None  # TODO: Implement artifact storage for large outputs
            )
            
            # Record step metrics
            output_size = len(exec_result["result"]) if exec_result["result"] else 0
            step_latency = exec_result.get("latency_ms", 0)
            metrics = get_metrics()
            metrics.record_step_metric(StepMetrics(
                step_id=step_id,
                tool_name=step["tool_name"],
                success=exec_result["success"],
                latency_ms=step_latency,
                output_size_bytes=output_size
            ))
            
            if exec_result["success"]:
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
            "success": steps_failed == 0
        }
    
    def _call_agent_b(
        self,
        cycle_id: str,
        plan: Dict[str, Any],
        step_id: int,
        previous_results: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Call Agent B to generate precise tool_args for a step.
        
        Args:
            cycle_id: Cycle ID for logging
            plan: Complete plan from Agent A
            step_id: Current step index
            previous_results: Results from previous steps
            tool_schemas: Tool schemas for Agent B
        
        Returns:
            Dict with:
                - success: bool
                - tool_args: dict (if successful)
                - error: str (if failed)
        """
        import json
        
        # Build system context for Agent B
        system_context = self.context_builder.build_for_role(
            role="B",
            session_id=self.session_id,
            tool_registry=TOOLS,
            shell_cwd=os.getcwd()
        )
        
        # Build Agent B prompt
        system_prompt = system_context + "\n\n" + get_agent_b_prompt(
            plan=plan,
            current_step_id=step_id,
            previous_outputs=previous_results,
            tool_schemas=tool_schemas
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Generate tool_args for step {step_id}"}
        ]
        
        # Call LLM in Agent B role
        llm_client = LLMClient(
            config=self.config,
            role="B",
            memory=self.memory
        )
        
        llm_result = llm_client.call(
            messages=messages,
            cycle_id=cycle_id
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
            # Try to extract JSON from response
            response_json = self._parse_agent_b_json(response_text)
            
            if "tool_args" not in response_json:
                return {
                    "success": False,
                    "tool_args": {},
                    "error": "Agent B response missing 'tool_args' field"
                }
            
            return {
                "success": True,
                "tool_args": response_json["tool_args"],
                "error": None
            }
        
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "tool_args": {},
                "error": f"Agent B returned invalid JSON: {e}"
            }
    
    def _parse_agent_b_json(self, text: str) -> Dict[str, Any]:
        """
        Parse JSON from Agent B response (similar to plan validator).
        
        Args:
            text: Raw Agent B response
        
        Returns:
            Parsed JSON dict
        
        Raises:
            json.JSONDecodeError: If JSON cannot be parsed
        """
        import json
        
        # Strip whitespace
        text = text.strip()
        
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code block
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                json_text = text[start:end].strip()
                return json.loads(json_text)
        
        # Try extracting from generic code block
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                json_text = text[start:end].strip()
                return json.loads(json_text)
        
        # Try finding first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_text = text[start:end+1]
            return json.loads(json_text)
        
        # Give up
        return json.loads(text)
    
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
    
    def _call_agent_c_summarizer(
        self,
        cycle_id: str,
        query: str,
        plan: Dict[str, Any],
        execution_result: Dict[str, Any]
    ) -> str:
        """
        Call Agent C in summarizer mode to present execution results.
        
        Args:
            cycle_id: Cycle ID for logging
            query: User's original query
            plan: The plan that was executed
            execution_result: Results from _execute_plan
        
        Returns:
            Conversational summary from Agent C
        """
        # Build context for Agent C
        context = f"""User Query: {query}

Plan Executed: {len(plan['steps'])} steps
- Steps completed: {execution_result['steps_completed']}
- Steps failed: {execution_result['steps_failed']}
- Overall success: {execution_result['success']}

Step Results Summary:
"""
        
        for result in execution_result["step_results"]:
            status = "✓" if result["success"] else "✗"
            context += f"\n{status} Step {result['step_id']}: {result['description']}"
            if result["success"]:
                # Include output preview
                output_preview = result["output"][:200]
                if len(result["output"]) > 200:
                    output_preview += "..."
                context += f"\n  Output: {output_preview}"
            else:
                context += f"\n  Error: {result['error']}"
        
        # Build system context for Agent C
        system_context = self.context_builder.build_for_role(
            role="C",
            session_id=self.session_id,
            tool_registry=TOOLS,
            shell_cwd=os.getcwd()
        )
        
        messages = [
            {"role": "system", "content": system_context + "\n\n" + get_agent_c_prompt("summarizer")},
            {"role": "user", "content": context}
        ]
        
        # Call LLM in Agent C role
        llm_client = LLMClient(
            config=self.config,
            role="C",
            memory=self.memory
        )
        
        llm_result = llm_client.call(
            messages=messages,
            cycle_id=cycle_id
        )
        
        if llm_result["error"]:
            # Fallback to raw summary if Agent C fails
            return f"[Agent C summarizer failed: {llm_result['error']}]\n\n{context}"
        
        return llm_result["message"].content or context
    
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
    
    def close(self):
        """Clean up resources"""
        self.memory.close()
