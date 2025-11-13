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
from typing import Optional, Dict, Any, List, Tuple


class CycleDebugger:
    """Comprehensive cycle debugger for v3.0 Orchestrator"""
    
    DB_PATH = Path("logs/orchestrator.db")
    
    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None
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
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
    
    def find_cycle(self, prefix: str) -> Optional[str]:
        """Find full cycle_id from prefix"""
        cursor = self.conn.execute(
            "SELECT cycle_id FROM router_decisions WHERE cycle_id LIKE ? LIMIT 1",
            (f"{prefix}%",)
        )
        row = cursor.fetchone()
        return row[0] if row else None
    
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
        cursor = self.conn.execute(
            """
            SELECT cycle_id, route, query_text, confidence, created_at 
            FROM router_decisions 
            WHERE cycle_id = ?
            """,
            (cycle_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    
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
    
    def get_variable_bindings(self, cycle_id: str) -> List[Dict[str, Any]]:
        """Get all variable bindings for this cycle"""
        cursor = self.conn.execute(
            """
            SELECT step_id, var_name, var_value, extraction_method, 
                   extractor_spec, created_at 
            FROM variable_bindings 
            WHERE cycle_id = ? 
            ORDER BY step_id, var_name
            """,
            (cycle_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def get_step_commands(self, cycle_id: str) -> List[Dict[str, Any]]:
        """Get all step commands (resolved tool_args with audit trail)"""
        cursor = self.conn.execute(
            """
            SELECT step_id, tool_name, command_template, resolved_command, 
                   substitution_log, created_at 
            FROM step_commands 
            WHERE cycle_id = ? 
            ORDER BY step_id
            """,
            (cycle_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    
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
        
        print(f"\n📋 METADATA:")
        print(f"  Route:      {metadata['route']}")
        print(f"  Confidence: {metadata['confidence']:.2f}")
        print(f"  Query:      {metadata['query_text']}")
        print(f"  Created:    {metadata['created_at']}")
        
        # 2. Agent Interactions
        interactions = self.get_agent_interactions(cycle_id)
        if interactions:
            print(f"\n🤖 AGENT INTERACTIONS ({len(interactions)} calls):")
            for i, inter in enumerate(interactions, 1):
                role_name = "A (Planner)" if inter['role'] == 'A' else "B (Engineer)"
                print(f"\n  [{i}] Agent {role_name}")
                print(f"      Latency: {inter['latency_ms']}ms")
                print(f"      Prompt:  {self._truncate(inter['prompt_preview'], 80)}")
                print(f"      Response:{self._truncate(inter['response_preview'], 80)}")
                
                if inter['token_usage_json']:
                    try:
                        tokens = json.loads(inter['token_usage_json'])
                        print(f"      Tokens:  {tokens.get('prompt_tokens', '?')} prompt, "
                              f"{tokens.get('completion_tokens', '?')} completion")
                    except:
                        pass
        
        # 3. Variable Bindings
        variables = self.get_variable_bindings(cycle_id)
        if variables:
            print(f"\n📊 VARIABLES EXTRACTED ({len(variables)} total):")
            for var in variables:
                print(f"  [{var['step_id']}] {var['var_name']} = {var['var_value']}")
                print(f"      Method: {var['extraction_method']}")
                if var['extractor_spec']:
                    spec = json.loads(var['extractor_spec'])
                    if 'pattern' in spec:
                        print(f"      Pattern: {spec['pattern']}")
        
        # 4. Step Commands (resolved with substitution)
        commands = self.get_step_commands(cycle_id)
        if commands:
            print(f"\n⚙️  STEP COMMANDS (with variable substitution):")
            for cmd in commands:
                print(f"\n  [Step {cmd['step_id']}] {cmd['tool_name']}")
                print(f"      Intent: {cmd['command_template']}")
                
                if cmd['substitution_log']:
                    subs = json.loads(cmd['substitution_log'])
                    if subs:
                        print(f"      Substitutions:")
                        for var_name, var_value in subs.items():
                            print(f"        ${{{var_name}}} → {var_value}")
                
                if cmd['resolved_command']:
                    resolved = json.loads(cmd['resolved_command'])
                    if 'command' in resolved:
                        print(f"      Command: {self._truncate(resolved['command'], 100)}")
                    else:
                        print(f"      Args: {json.dumps(resolved, indent=14)}")
        
        # 5. Step Outputs
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
        
        if variables:
            print(f"  Variables extracted: {len(variables)}")
        
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
