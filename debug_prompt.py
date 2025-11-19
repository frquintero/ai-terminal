from orchestrator.prompts import get_agent_b_prompt

plan = {
    "steps": [
        {
            "tool_name": "run_command",
            "intent": "List directory contents",
            "description": "List all files",
            "output_keys": ["directory_contents"]
        }
    ]
}

prompt = get_agent_b_prompt(
    plan=plan,
    current_step_id=0,
    previous_outputs=[],
    tool_schemas=[{"name": "run_command", "schema": {}}]
)

print(prompt)
