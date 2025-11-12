"""
Orchestrator - Main controller for v2.0 multi-role architecture

Coordinates: Router → Execution → Agent C narrator
Implements CHAT, SHELL, and CACHED routes (Phase 2)
PLANNER route implemented in Phase 3
"""

import os
import time
import uuid
from typing import Any, Dict, Optional

from config import Config
from llm_client import LLMClient
from memory.api import Memory
from orchestrator.prompts import get_agent_c_prompt
from router.router import Router
from router.rules import Route
from tool_executor import ToolExecutor


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
                # Phase 3 implementation
                result = OrchestratorResult(
                    cycle_id=cycle_id,
                    route="PLANNER",
                    query=query,
                    agent_c_response="PLANNER route not yet implemented (Phase 3)",
                    error="PLANNER route requires Phase 3 implementation"
                )
            else:
                raise ValueError(f"Unknown route: {router_result.route}")
            
            # Calculate total latency
            result.latency_ms = int((time.time() - start_time) * 1000)
            
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
        2. Call LLM in Agent C (chat mode)
        3. Log to chat_history
        4. Return result
        """
        # Get chat history for context
        chat_history = self.memory.get_chat_history(
            session_id=self.session_id,
            last_n=10
        )
        
        # Build messages for Agent C
        messages = [
            {"role": "system", "content": get_agent_c_prompt("chat")}
        ]
        
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
        1. Execute command via ToolExecutor (run_command)
        2. Call Agent C narrator to present results
        3. Cache successful execution for future CACHED hits
        4. Return result
        
        Target: <500ms end-to-end
        """
        # Execute shell command directly
        exec_result = self.tool_executor.execute(
            tool_name="run_command",
            tool_args={"command": query},
            cycle_id=cycle_id,
            step_id=0  # Single-step execution
        )
        
        # Call Agent C narrator
        agent_c_response = self._call_agent_c_narrator(
            cycle_id=cycle_id,
            query=query,
            tool_name="run_command",
            tool_output=exec_result["result"],
            success=exec_result["success"],
            exit_code=exec_result.get("exit_code")
        )
        
        # Cache successful execution for future hits
        if exec_result["success"]:
            self._cache_execution(
                query=query,
                tool_name="run_command",
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
        
        messages = [
            {"role": "system", "content": get_agent_c_prompt("narrator")},
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
