"""
Memory API - CRUD operations for v2.0 Orchestrator

Provides high-level interface to orchestrator.db
All operations are transactional and thread-safe.
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from memory.schema import DEFAULT_DB_PATH, init_db


class Memory:
    """
    Unified Memory System - Single source of truth for all orchestrator state.
    
    Usage:
        mem = Memory()
        cycle_id = mem.create_cycle(session_id, "user query")
        mem.save_router_decision(cycle_id, route="CHAT", confidence=0.95)
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize memory system with database connection."""
        self.db_path = db_path or DEFAULT_DB_PATH
        self.conn = init_db(self.db_path)
        # Thread lock for concurrent cycle operations
        self._lock = threading.RLock()
    
    def close(self):
        """Close database connection."""
        self.conn.close()
    
    # ========== Session Management ==========
    
    def create_session(
        self, 
        session_id: str, 
        model: str, 
        system_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create new session record.
        
        Args:
            session_id: Unique session identifier
            model: LLM model name (e.g., "gpt-4")
            system_info: System context (OS, cwd, etc.)
        
        Returns:
            Session ID (same as input)
        """
        system_info_json = json.dumps(system_info) if system_info else None
        
        self.conn.execute(
            """
            INSERT INTO sessions (session_id, model, system_info_json)
            VALUES (?, ?, ?)
            """,
            (session_id, model, system_info_json)
        )
        self.conn.commit()
        return session_id
    
    def update_session_activity(self, session_id: str):
        """Update session last_activity_at timestamp."""
        self.conn.execute(
            "UPDATE sessions SET last_activity_at = CURRENT_TIMESTAMP WHERE session_id = ?",
            (session_id,)
        )
        self.conn.commit()
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session details."""
        cursor = self.conn.execute(
            "SELECT session_id, created_at, model, system_info_json, last_activity_at FROM sessions WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "session_id": row[0],
            "created_at": row[1],
            "model": row[2],
            "system_info": json.loads(row[3]) if row[3] else None,
            "last_activity_at": row[4]
        }
    
    # ========== Cycle Management ==========
    
    def create_cycle(self, session_id: str, query: str) -> str:
        """
        Create new orchestration cycle.
        
        Args:
            session_id: Session this cycle belongs to
            query: User query text
        
        Returns:
            Unique cycle_id (UUID)
        """
        cycle_id = str(uuid.uuid4())
        
        # Create placeholder router decision (will be updated after routing)
        # Note: Route defaults to PLANNER (conservative fallback) until router classifies
        self.conn.execute(
            """
            INSERT INTO router_decisions (session_id, cycle_id, query_text, route, confidence)
            VALUES (?, ?, ?, 'PLANNER', 0.0)
            """,
            (session_id, cycle_id, query)
        )
        self.conn.commit()
        
        return cycle_id
    
    # ========== Router Operations ==========
    
    def save_router_decision(
        self,
        cycle_id: str,
        route: str,
        confidence: Optional[float] = None,
        rules: Optional[Dict[str, Any]] = None,
        cache_hit_tool: Optional[str] = None,
        cache_hit_args: Optional[Dict[str, Any]] = None
    ):
        """
        Save router classification decision.
        
        Args:
            cycle_id: Cycle ID
            route: Classification (CHAT, CACHED, PLANNER, SHELL)
            confidence: Confidence score (0.0-1.0)
            rules: Rules that matched (for SHELL/CACHED)
            cache_hit_tool: Tool name if cache hit
            cache_hit_args: Tool arguments if cache hit
        """
        rules_json = json.dumps(rules) if rules else None
        cache_hit_args_json = json.dumps(cache_hit_args) if cache_hit_args else None
        
        self.conn.execute(
            """
            UPDATE router_decisions
            SET route = ?, confidence = ?, rules_json = ?, cache_hit_tool = ?, cache_hit_args_json = ?
            WHERE cycle_id = ?
            """,
            (route, confidence, rules_json, cache_hit_tool, cache_hit_args_json, cycle_id)
        )
        self.conn.commit()
    
    def get_router_decision(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        """Get router decision for cycle."""
        cursor = self.conn.execute(
            """
            SELECT id, session_id, cycle_id, query_text, route, confidence, 
                   rules_json, cache_hit_tool, cache_hit_args_json, created_at
            FROM router_decisions WHERE cycle_id = ?
            """,
            (cycle_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "session_id": row[1],
            "cycle_id": row[2],
            "query_text": row[3],
            "route": row[4],
            "confidence": row[5],
            "rules": json.loads(row[6]) if row[6] else None,
            "cache_hit_tool": row[7],
            "cache_hit_args": json.loads(row[8]) if row[8] else None,
            "created_at": row[9]
        }
    
    # ========== Intention Cache Operations ==========
    
    def add_to_intention_cache(
        self,
        user_query: str,
        normalized_intent: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        success: bool = True
    ):
        """
        Add successful execution to intention cache.
        
        Args:
            user_query: Original user query
            normalized_intent: Normalized intent (for FTS matching)
            tool_name: Tool that was executed
            tool_args: Tool arguments
            success: Whether execution succeeded
        """
        tool_args_json = json.dumps(tool_args)
        success_flag = 1 if success else 0
        
        self.conn.execute(
            """
            INSERT INTO intention_cache 
            (user_query_text, normalized_intent, tool_name, tool_args_json, success_flag)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_query, normalized_intent, tool_name, tool_args_json, success_flag)
        )
        self.conn.commit()
    
    def search_intention_cache(
        self, 
        query: str, 
        limit: int = 5,
        min_success: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search intention cache using FTS5 BM25 scoring.
        
        Args:
            query: Search query
            limit: Max results
            min_success: Only return successful executions
        
        Returns:
            List of cache hits with scores
        """
        # Sanitize query for FTS5 MATCH
        # Empty or whitespace-only queries return empty results
        query_stripped = query.strip()
        if not query_stripped:
            return []
        
        # Quote query for FTS5 (escape double quotes)
        fts_query = f'"{query_stripped.replace('"', '""')}"'
        
        success_clause = "AND ic.success_flag = 1" if min_success else ""
        
        cursor = self.conn.execute(
            f"""
            SELECT ic.id, ic.user_query_text, ic.normalized_intent, ic.tool_name, 
                   ic.tool_args_json, ic.usage_count, ic.last_used_at,
                   fts.rank
            FROM intention_cache_fts fts
            JOIN intention_cache ic ON fts.rowid = ic.id
            WHERE intention_cache_fts MATCH ?
            {success_clause}
            ORDER BY fts.rank
            LIMIT ?
            """,
            (fts_query, limit)
        )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "user_query_text": row[1],
                "normalized_intent": row[2],
                "tool_name": row[3],
                "tool_args": json.loads(row[4]),
                "usage_count": row[5],
                "last_used_at": row[6],
                "rank": row[7]
            })
        
        return results
    
    def update_cache_usage(self, cache_id: int):
        """Increment usage count and update last_used_at."""
        self.conn.execute(
            """
            UPDATE intention_cache
            SET usage_count = usage_count + 1, last_used_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (cache_id,)
        )
        self.conn.commit()
    
    # ========== Interaction Logging (Roles A/B/C) ==========
    
    def log_interaction(
        self,
        cycle_id: str,
        role: str,
        system_prompt_checksum: str,
        prompt_preview: Optional[str] = None,
        response_preview: Optional[str] = None,
        token_usage: Optional[Dict[str, int]] = None,
        latency_ms: Optional[int] = None
    ):
        """
        Log LLM interaction (any role: A, B, or C).
        
        Args:
            cycle_id: Cycle ID
            role: Agent role ('A', 'B', or 'C')
            system_prompt_checksum: Hash of system prompt (for tracking)
            prompt_preview: First 500 chars of prompt
            response_preview: First 500 chars of response
            token_usage: Token counts (prompt, completion, total)
            latency_ms: LLM call latency
        """
        token_usage_json = json.dumps(token_usage) if token_usage else None
        
        self.conn.execute(
            """
            INSERT INTO interactions
            (cycle_id, role, system_prompt_checksum, prompt_preview, response_preview, 
             token_usage_json, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cycle_id, role, system_prompt_checksum, prompt_preview, response_preview,
             token_usage_json, latency_ms)
        )
        self.conn.commit()
    
    def get_interactions(
        self, 
        cycle_id: Optional[str] = None,
        role: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get interactions, optionally filtered by cycle or role."""
        query = "SELECT * FROM interactions WHERE 1=1"
        params = []
        
        if cycle_id:
            query += " AND cycle_id = ?"
            params.append(cycle_id)
        
        if role:
            query += " AND role = ?"
            params.append(role)
        
        query += " ORDER BY created_at DESC"
        
        cursor = self.conn.execute(query, params)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "cycle_id": row[1],
                "role": row[2],
                "system_prompt_checksum": row[3],
                "prompt_preview": row[4],
                "response_preview": row[5],
                "token_usage": json.loads(row[6]) if row[6] else None,
                "latency_ms": row[7],
                "created_at": row[8]
            })
        
        return results
    
    # ========== Task State (PLANNER route) ==========
    
    def save_plan(
        self,
        cycle_id: str,
        plan: Dict[str, Any],
        status: str = "pending"
    ):
        """
        Save Agent A plan to task_state.
        
        Args:
            cycle_id: Cycle ID
            plan: Plan JSON (steps, tools, etc.)
            status: pending|in_progress|done|error
        """
        plan_json = json.dumps(plan)
        
        self.conn.execute(
            """
            INSERT INTO task_state (cycle_id, plan_json, status)
            VALUES (?, ?, ?)
            """,
            (cycle_id, plan_json, status)
        )
        self.conn.commit()
    
    def update_task_status(
        self,
        cycle_id: str,
        status: str,
        current_step_id: Optional[int] = None,
        error_message: Optional[str] = None
    ):
        """Update task execution state."""
        self.conn.execute(
            """
            UPDATE task_state
            SET status = ?, current_step_id = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE cycle_id = ?
            """,
            (status, current_step_id, error_message, cycle_id)
        )
        self.conn.commit()
    
    def get_task_state(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        """Get task state for cycle."""
        cursor = self.conn.execute(
            """
            SELECT id, cycle_id, plan_json, status, current_step_id, error_message, 
                   created_at, updated_at
            FROM task_state WHERE cycle_id = ?
            """,
            (cycle_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "cycle_id": row[1],
            "plan": json.loads(row[2]),
            "status": row[3],
            "current_step_id": row[4],
            "error_message": row[5],
            "created_at": row[6],
            "updated_at": row[7]
        }
    
    # ========== Step Outputs (PLANNER route - Agent B) ==========
    
    def save_step_output(
        self,
        cycle_id: str,
        step_id: int,
        tool_name: str,
        tool_args: Dict[str, Any],
        success: bool,
        exit_code: Optional[int] = None,
        output_preview: Optional[str] = None,
        artifact_path: Optional[str] = None
    ):
        """
        Save step execution result.
        
        Args:
            cycle_id: Cycle ID
            step_id: Step number in plan
            tool_name: Tool executed
            tool_args: Tool arguments
            success: Whether step succeeded
            exit_code: Exit code (for shell commands)
            output_preview: First 1000 chars of output
            artifact_path: Path to full output file (if large)
        """
        tool_args_json = json.dumps(tool_args)
        success_flag = 1 if success else 0
        
        self.conn.execute(
            """
            INSERT INTO step_outputs
            (cycle_id, step_id, tool_name, tool_args_json, success, exit_code, 
             output_preview, artifact_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (cycle_id, step_id, tool_name, tool_args_json, success_flag, exit_code,
             output_preview, artifact_path)
        )
        self.conn.commit()
    
    def get_step_outputs(self, cycle_id: str, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get step outputs for cycle.
        
        Args:
            cycle_id: Cycle ID
            last_n: Return only last N steps (for context compression)
        
        Returns:
            List of step outputs
        """
        query = """
            SELECT id, cycle_id, step_id, tool_name, tool_args_json, success, 
                   exit_code, output_preview, artifact_path, created_at
            FROM step_outputs
            WHERE cycle_id = ?
            ORDER BY step_id DESC
        """
        
        if last_n:
            query += f" LIMIT {last_n}"
        
        cursor = self.conn.execute(query, (cycle_id,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "cycle_id": row[1],
                "step_id": row[2],
                "tool_name": row[3],
                "tool_args": json.loads(row[4]),
                "success": bool(row[5]),
                "exit_code": row[6],
                "output_preview": row[7],
                "artifact_path": row[8],
                "created_at": row[9]
            })
        
        return list(reversed(results))  # Return in chronological order
    
    # ========== Chat History (CHAT route) ==========
    
    def save_chat_exchange(
        self,
        session_id: str,
        cycle_id: str,
        user_query: str,
        agent_response: str
    ):
        """Save chat exchange to history."""
        self.conn.execute(
            """
            INSERT INTO chat_history (session_id, cycle_id, user_query, agent_response)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, cycle_id, user_query, agent_response)
        )
        self.conn.commit()
    
    def get_chat_history(
        self, 
        session_id: str, 
        last_n: int = 10,
        token_budget: int = 2000
    ) -> List[Dict[str, Any]]:
        """
        Get recent chat history for session, bounded by token budget.
        
        Args:
            session_id: Session ID
            last_n: Maximum number of exchanges (hard limit, checked first)
            token_budget: Max tokens to include (default: 2000 for LLM context)
        
        Returns:
            List of chat exchanges in chronological order, within budget
        """
        # Get all recent exchanges (up to last_n)
        cursor = self.conn.execute(
            """
            SELECT id, cycle_id, user_query, agent_response, timestamp
            FROM chat_history
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (session_id, last_n)
        )
        
        # Walk backwards, accumulating tokens until budget exceeded
        all_rows = cursor.fetchall()
        results = []
        total_tokens = 0
        
        for row in all_rows:
            user_query = row[2]
            agent_response = row[3]
            
            # Rough token estimate: 4 chars = 1 token (OpenAI convention)
            user_tokens = len(user_query) // 4 if user_query else 0
            response_tokens = len(agent_response) // 4 if agent_response else 0
            
            if total_tokens + user_tokens + response_tokens > token_budget:
                # Budget would be exceeded, stop here
                break
            
            results.append({
                "id": row[0],
                "cycle_id": row[1],
                "user_query": user_query,
                "agent_response": agent_response,
                "timestamp": row[4]
            })
            
            total_tokens += user_tokens + response_tokens
        
        return list(reversed(results))  # Return in chronological order
    
    # ========== LLM Traces (Debugging) ==========
    
    def save_llm_trace(
        self,
        cycle_id: str,
        role: str,
        full_prompt: str,
        full_response: str,
        model: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ):
        """Save full LLM prompt/response for debugging."""
        self.conn.execute(
            """
            INSERT INTO llm_traces
            (cycle_id, role, full_prompt, full_response, model, temperature, max_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cycle_id, role, full_prompt, full_response, model, temperature, max_tokens)
        )
        self.conn.commit()
    
    def get_llm_traces(
        self, 
        cycle_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get LLM traces for debugging."""
        if cycle_id:
            cursor = self.conn.execute(
                "SELECT * FROM llm_traces WHERE cycle_id = ? ORDER BY created_at DESC LIMIT ?",
                (cycle_id, limit)
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM llm_traces ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "cycle_id": row[1],
                "role": row[2],
                "full_prompt": row[3],
                "full_response": row[4],
                "model": row[5],
                "temperature": row[6],
                "max_tokens": row[7],
                "created_at": row[8]
            })
        
        return results
    
    def get_recent_completed_plan(
        self, 
        session_id: str, 
        last_n: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get recently completed plans for Planner→Chat handoff context.
        
        Args:
            session_id: Session ID
            last_n: Number of recent completed plans to retrieve
        
        Returns:
            List of completed plans with query, status, and timestamp
        """
        cursor = self.conn.execute(
            """
            SELECT ts.id, rd.query_text, ts.status, ts.created_at, ts.updated_at
            FROM task_state ts
            JOIN router_decisions rd ON ts.cycle_id = rd.cycle_id
            WHERE rd.session_id = ? AND ts.status = 'done'
            ORDER BY ts.updated_at DESC
            LIMIT ?
            """,
            (session_id, last_n)
        )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "query": row[1],
                "status": row[2],
                "created_at": row[3],
                "updated_at": row[4]
            })
        
        return results
