#!/usr/bin/env python3
import sys
sys.path.insert(0, '/run/media/fratq/4593fc5e-12d7-4064-8a55-3ad61a661126/CODE/ai-terminal')

from memory.api import Memory
import json

mem = Memory()

# Find cycle ID
cycle_prefix = '350e7448'
# List all cycles first
print("Fetching LLM traces...")
all_traces = mem.get_llm_traces(limit=10000)
print(f"Total traces: {len(all_traces)}")
cycle_ids = set(t['cycle_id'] for t in all_traces if t['cycle_id'])
print(f"Unique cycle IDs: {sorted(cycle_ids)}")

if not any(cycle_prefix in cid for cid in cycle_ids):
    print(f"No cycle found with prefix {cycle_prefix}")
    sys.exit(1)

cycle_id = next(cid for cid in cycle_ids if cycle_prefix in cid)
print(f"Found cycle: {cycle_id}")

print(f"Full Cycle ID: {cycle_id}")

# Get router decision if exists
router_dec = mem.get_router_decision(cycle_id)
if router_dec:
    print("Router Decision:")
    print(json.dumps(router_dec, indent=2))

# Get task state (plan)
task_state = mem.get_task_state(cycle_id)
if task_state:
    print("Task State:")
    print(json.dumps(task_state, indent=2))

# Get step outputs
step_outputs = mem.get_step_outputs(cycle_id)
if step_outputs:
    print("Step Outputs:")
    for step in step_outputs:
        print(json.dumps(step, indent=2))

# Get LLM traces for this cycle
cycle_traces = [t for t in traces if t['cycle_id'] == cycle_id]
print("LLM Traces:")
for trace in cycle_traces:
    print(f"Role: {trace['role']}")
    print(f"Prompt: {trace['full_prompt'][:500]}...")
    print(f"Response: {trace['full_response'][:500]}...")
    print("---")

# Get chat history
chat_history = mem.get_chat_history(cycle_id=cycle_id)
if chat_history:
    print("Chat History:")
    for msg in chat_history:
        print(json.dumps(msg, indent=2))