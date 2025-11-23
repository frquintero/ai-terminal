#!/usr/bin/env python3
"""
debug_cycle.py - Comprehensive cycle analysis tool for v3.0 Orchestrator

Provides detailed information about any cycle execution including:
- Cycle metadata and Agent A decision type
- Variable extraction and placeholder substitution
- Step-by-step execution with tool outputs
- Repair loop history (if any)
- Full audit trail for debugging

Usage:
    python3 debug_cycle.py <cycle_id_prefix>
    python3 debug_cycle.py abc12345          # 8-char prefix
    python3 debug_cycle.py abc12345-xxxx...  # Full UUID

Exit codes:
    0 - Success
    1 - Cycle not found
    2 - Database error
"""

import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple, Set


class CycleDebugger:
    """Comprehensive cycle debugger for v3.0 Orchestrator"""
    
    DB_PATH = Path("logs/orchestrator.db")
    
    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None
        self.available_tables: Set[str] = set()
        self._connect()
    
    def _connect(self):
        """Connect to database"""
        if not self.DB_PATH.exists():
            print(f"❌ Database not found: {self.DB_PATH}")
            sys.exit(2)
        
        try:
            self.conn = sqlite3.connect(self.DB_PATH)
            self.conn.row_factory = sqlite3.Row
        except sqlite3.Error as e:
            print(f"❌ Database error: {e}")
            sys.exit(2)

        self._cache_available_tables()

    def _cache_available_tables(self):
        """Cache the list of tables present in the database."""
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        self.available_tables = {row[0] for row in cursor.fetchall()}

    def _table_exists(self, table_name: str) -> bool:
        """Check if a given table exists in the current database."""
        return table_name in self.available_tables
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
    
    def find_cycle(self, prefix: str) -> Optional[str]:
        """Find full cycle_id from prefix"""
        # Check router_decisions first
        cursor = self.conn.execute(
            "SELECT cycle_id FROM router_decisions WHERE cycle_id LIKE ? LIMIT 1",
            (f"{prefix}%",)
        )
        row = cursor.fetchone()
        if row:
            return row[0]
            
        # Check cycle_failures
        if self._table_exists("cycle_failures"):
             cursor = self.conn.execute(
                "SELECT cycle_id FROM cycle_failures WHERE cycle_id LIKE ? LIMIT 1",
                (f"{prefix}%",)
            )
             row = cursor.fetchone()
             if row:
                 return row[0]
                 
        return None
    
    def get_recent_cycles(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent cycles for display"""
        cursor = self.conn.execute(
            """
            SELECT cycle_id, route, query_text, created_at 
            FROM router_decisions 
            ORDER BY created_at DESC 
            LIMIT ?
            """,
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def get_cycle_metadata(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        """Get cycle metadata"""
        # Try router_decisions first
        cursor = self.conn.execute(
            """
            SELECT cycle_id, route, query_text, confidence, created_at 
            FROM router_decisions 
            WHERE cycle_id = ?
            """,
            (cycle_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
            
        # Try cycle_failures
        if self._table_exists("cycle_failures"):
            cursor = self.conn.execute(
                """
                SELECT cycle_id, route, query_text, '0.0' as confidence, created_at, 
                       error_message, error_type, stage, process, error_code, facts_json
                FROM cycle_failures 
                WHERE cycle_id = ?
                """,
                (cycle_id,)
            )
            row = cursor.fetchone()
            if row:
                data = dict(row)
                data['is_failure'] = True
                return data
                
        return None
    
    def get_agent_interactions(self, cycle_id: str) -> List[Dict[str, Any]]:
        """Get all agent interactions for this cycle"""
        cursor = self.conn.execute(
            """
            SELECT role, prompt_preview, response_preview, token_usage_json, 
                   latency_ms, created_at 
            FROM interactions 
            WHERE cycle_id = ? 
            ORDER BY id
            """,
            (cycle_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def get_task_state(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        """Get stored plan/state for the cycle."""
        if not self._table_exists("task_state"):
            return None
        cursor = self.conn.execute(
            """
            SELECT plan_json, status, current_step_id, error_message, updated_at
            FROM task_state
            WHERE cycle_id = ?
            """,
            (cycle_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_step_outputs(self, cycle_id: str) -> List[Dict[str, Any]]:
        """Get all step execution outputs"""
        cursor = self.conn.execute(
            """
            SELECT step_id, tool_name, tool_args_json, success, exit_code, 
                   output_preview, created_at 
            FROM step_outputs 
            WHERE cycle_id = ? 
            ORDER BY step_id
            """,
            (cycle_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def _format_json(self, json_str: Optional[str]) -> str:
        """Pretty-print JSON"""
        if not json_str:
            return "(empty)"
        try:
            obj = json.loads(json_str)
            return json.dumps(obj, indent=2)
        except:
            return json_str
    
    def _truncate(self, text: Optional[str], length: int = 100) -> str:
        """Truncate text for display"""
        if not text:
            return "(empty)"
        text = text.strip()
        if len(text) > length:
            return text[:length] + "..."
        return text
    
    def print_cycle_report(self, cycle_id: str):
        """Print comprehensive cycle report"""
        # 1. Metadata
        metadata = self.get_cycle_metadata(cycle_id)
        if not metadata:
            print(f"❌ Cycle not found: {cycle_id}")
            return False
        
        print("\n" + "="*70)
        print(f"CYCLE: {cycle_id}")
        print("="*70)
        
        if metadata.get('is_failure'):
            print(f"\n❌ CYCLE FAILED")
            print(f"  Error Type: {metadata.get('error_type')}")
            print(f"  Stage:      {metadata.get('stage')}")
            print(f"  Message:    {metadata.get('error_message')}")
            
            if metadata.get('facts_json'):
                try:
                    facts = json.loads(metadata['facts_json'])
                    print("\n💥 FAILURE FACTS:")
                    exec_result = (facts or {}).get('execution_result') if isinstance(facts, dict) else None
                    if exec_result:
                        steps = exec_result.get('step_results', [])
                        for step in steps:
                            print(f"  Step {step.get('step_id')}: {step.get('tool_name')}")
                            print(f"    Success: {step.get('success')}")
                            if step.get('error'):
                                print(f"    Error:   {step.get('error')}")
                    agent_response = (facts or {}).get('agent_response') if isinstance(facts, dict) else None
                    if agent_response:
                        print(f"\n  Agent Response Preview: {self._truncate(agent_response, 200)}")
                    if not isinstance(facts, dict):
                        print(json.dumps(facts, indent=2))
                except Exception as e:
                    print(f"  Facts parsing error: {e}")
        
        print(f"\n📋 METADATA:")
        print(f"  Route:      {metadata['route']}")
        print(f"  Confidence: {float(metadata['confidence']):.2f}")
        print(f"  Query:      {metadata['query_text']}")
        print(f"  Created:    {metadata['created_at']}")
        
        # 2. Agent Interactions
        # 2. Task State / Plan
        task_state = self.get_task_state(cycle_id)
        if task_state:
            print("\n🧭 PLAN STATE:")
            print(f"  Status:       {task_state['status']}")
            if task_state.get('current_step_id') is not None:
                print(f"  Current step: {task_state['current_step_id']}")
            if task_state.get('error_message'):
                print(f"  Error:        {task_state['error_message']}")
            print(f"  Updated at:   {task_state['updated_at']}")
            if task_state.get('plan_json'):
                print("  Plan JSON:")
                print(self._format_json(task_state['plan_json']))

        # 3. Agent Interactions
        interactions = self.get_agent_interactions(cycle_id)
        if interactions:
            print(f"\n🤖 AGENT INTERACTIONS ({len(interactions)} calls):")
            for i, inter in enumerate(interactions, 1):
                role_name = "A (Planner)" if inter['role'] == 'A' else "B (Engineer)"
                print(f"\n  [{i}] Agent {role_name}")
                print(f"      Latency: {inter.get('latency_ms', 'N/A')}ms")
                print(f"      Prompt:  {self._truncate(inter['prompt_preview'], 80)}")
                print(f"      Response:{self._truncate(inter['response_preview'], 80)}")
                
                if inter['token_usage_json']:
                    try:
                        tokens = json.loads(inter['token_usage_json'])
                        print(f"      Tokens:  {tokens.get('prompt_tokens', '?')} prompt, "
                              f"{tokens.get('completion_tokens', '?')} completion")
                    except:
                        pass
        
        # 4. Step Outputs
        outputs = self.get_step_outputs(cycle_id)
        if outputs:
            print(f"\n✅ STEP EXECUTION RESULTS ({len(outputs)} steps):")
            for output in outputs:
                status = "✓" if output['success'] else "✗"
                print(f"\n  [{output['step_id']}] {status} {output['tool_name']}")
                print(f"      Success: {output['success']}")
                if output['exit_code'] is not None:
                    print(f"      Exit Code: {output['exit_code']}")
                
                if output['output_preview']:
                    preview = self._truncate(output['output_preview'], 80)
                    print(f"      Output: {preview}")
        
        # 6. Summary
        print(f"\n📈 SUMMARY:")
        if interactions:
            agent_a_calls = sum(1 for i in interactions if i['role'] == 'A')
            agent_b_calls = sum(1 for i in interactions if i['role'] == 'B')
            repair_detected = agent_a_calls > 1
            print(f"  Agent A calls: {agent_a_calls} {'(repair loop detected!)' if repair_detected else ''}")
            print(f"  Agent B calls: {agent_b_calls}")
        
        if outputs:
            success_count = sum(1 for o in outputs if o['success'])
            failed_count = len(outputs) - success_count
            print(f"  Steps: {success_count} succeeded, {failed_count} failed")
        
        if task_state:
            print(f"  Plan status: {task_state['status']}")
        
        print("\n" + "="*70 + "\n")
        return True
    
    def print_not_found_help(self, prefix: str):
        """Print helpful message when cycle not found"""
        print(f"\n❌ Cycle not found: {prefix}")
        print("\nRecent cycles:")
        print("  (Cycle ID | Route | Query)")
        
        recent = self.get_recent_cycles(5)
        if recent:
            for cycle in recent:
                short_id = cycle['cycle_id'][:8]
                query = self._truncate(cycle['query_text'], 50)
                print(f"  {short_id}... | {cycle['route']:6s} | {query}")
        else:
            print("  (No cycles found in database)")
        
        print()


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print(f"Usage: python3 debug_cycle.py <cycle_id>")
        print(f"       python3 debug_cycle.py abc12345          # 8-char prefix")
        print(f"       python3 debug_cycle.py abc12345-xxxx...  # Full UUID")
        sys.exit(1)
    
    prefix = sys.argv[1]
    
    debugger = CycleDebugger()
    try:
        # Find full cycle_id from prefix
        cycle_id = debugger.find_cycle(prefix)
        
        if not cycle_id:
            debugger.print_not_found_help(prefix)
            sys.exit(1)
        
        # Print report
        success = debugger.print_cycle_report(cycle_id)
        sys.exit(0 if success else 1)
    
    finally:
        debugger.close()


if __name__ == "__main__":
    main()
