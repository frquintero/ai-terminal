#!/usr/bin/env python3
"""
Debug cycle tool for ai-terminal

Analyzes a specific cycle from the orchestrator database.
Provides comprehensive information about router decision, agent interactions,
and step execution for debugging purposes.

Usage: python3 debug_cycle.py <cycle_id_prefix>
Example: python3 debug_cycle.py 1219b8eb
"""
import sqlite3
import json
import sys

def analyze_cycle(cycle_prefix):
    """Analyze a cycle and display comprehensive debug information"""
    conn = sqlite3.connect('logs/orchestrator.db')
    conn.row_factory = sqlite3.Row
    
    print("=" * 70)
    print(f"CYCLE DEBUG: {cycle_prefix}")
    print("=" * 70)
    
    # Get router decision
    cycle = conn.execute(
        'SELECT * FROM router_decisions WHERE cycle_id LIKE ?',
        (f'{cycle_prefix}%',)
    ).fetchone()
    
    if not cycle:
        print(f'❌ Cycle not found: {cycle_prefix}')
        print('\nRecent cycles:')
        recent = conn.execute(
            'SELECT cycle_id, route, query_text, created_at FROM router_decisions ORDER BY created_at DESC LIMIT 5'
        ).fetchall()
        for r in recent:
            print(f"  {r['cycle_id'][:8]} | {r['route']:8} | {r['query_text'][:50]}")
        conn.close()
        return
    
    print(f"\n🔀 ROUTER DECISION")
    print(f"   Cycle ID:    {cycle['cycle_id']}")
    print(f"   Route:       {cycle['route']}")
    print(f"   Query:       '{cycle['query_text']}'")
    print(f"   Confidence:  {cycle['confidence']}")
    print(f"   Created:     {cycle['created_at']}")
    
    # Get agent interactions
    print(f"\n🤖 AGENT INTERACTIONS")
    inters = conn.execute(
        '''SELECT role, latency_ms, token_usage_json, 
                  prompt_preview, response_preview 
           FROM interactions 
           WHERE cycle_id = ? 
           ORDER BY id''',
        (cycle['cycle_id'],)
    ).fetchall()
    
    if inters:
        for i, inter in enumerate(inters, 1):
            print(f"\n   Agent {inter['role']} (Call #{i})")
            print(f"   ├─ Latency: {inter['latency_ms']}ms")
            
            if inter['token_usage_json']:
                tokens = json.loads(inter['token_usage_json'])
                print(f"   ├─ Tokens: {tokens.get('total_tokens', 'N/A')}")
            
            if inter['prompt_preview']:
                print(f"   ├─ Prompt: {inter['prompt_preview'][:80]}...")
            
            if inter['response_preview']:
                print(f"   └─ Response: {inter['response_preview'][:120]}...")
    else:
        print("   ⚠️  No agent interactions found")
    
    # Get step outputs (PLANNER route only)
    if cycle['route'] == 'PLANNER':
        print(f"\n🔧 STEP EXECUTION")
        steps = conn.execute(
            '''SELECT step_id, tool_name, tool_args_json, 
                      success, exit_code, output_preview 
               FROM step_outputs 
               WHERE cycle_id = ? 
               ORDER BY step_id''',
            (cycle['cycle_id'],)
        ).fetchall()
        
        if steps:
            # Deduplicate steps (known logging bug)
            seen = set()
            unique_steps = []
            for step in steps:
                key = (step['step_id'], step['tool_name'], step['output_preview'])
                if key not in seen:
                    seen.add(key)
                    unique_steps.append(step)
            
            for step in unique_steps:
                print(f"\n   Step {step['step_id']}: {step['tool_name']}")
                
                if step['tool_args_json']:
                    args = json.loads(step['tool_args_json'])
                    print(f"   ├─ Args: {json.dumps(args, indent=6)[6:]}")  # Remove first indent
                
                print(f"   ├─ Success: {bool(step['success'])}")
                if step['exit_code'] is not None:
                    print(f"   ├─ Exit Code: {step['exit_code']}")
                
                if step['output_preview']:
                    output = step['output_preview']
                    if len(output) > 200:
                        print(f"   └─ Output: {output[:200]}...")
                    else:
                        print(f"   └─ Output: {output}")
        else:
            print("   ⚠️  No step outputs found")
    
    # Get chat history (CHAT route only)
    if cycle['route'] == 'CHAT':
        print(f"\n💬 CHAT EXCHANGE")
        chat = conn.execute(
            'SELECT user_query, agent_response FROM chat_history WHERE cycle_id = ?',
            (cycle['cycle_id'],)
        ).fetchone()
        
        if chat:
            print(f"   User: {chat['user_query']}")
            print(f"   Agent: {chat['agent_response'][:200]}...")
        else:
            print("   ⚠️  No chat history found")
    
    print("\n" + "=" * 70)
    print("✅ Analysis complete")
    print("=" * 70)
    
    conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 debug_cycle.py <cycle_id_prefix>")
        print("Example: python3 debug_cycle.py 1219b8eb")
        sys.exit(1)
    
    analyze_cycle(sys.argv[1])
