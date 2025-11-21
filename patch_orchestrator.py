
import os

def patch_orchestrator():
    path = "orchestrator/orchestrator.py"
    with open(path, "r") as f:
        lines = f.readlines()

    new_lines = []
    in_loop = False
    loop_indent = "        " # 8 spaces
    
    # Find the start and end of the loop
    start_idx = -1
    end_idx = -1
    
    for i, line in enumerate(lines):
        if "for loop_idx in range(max_loops):" in line:
            start_idx = i
            break
    
    # Find where the loop ends. It ends before "Final narration pass" comment.
    for i, line in enumerate(lines):
        if "Final narration pass with tools DISABLED" in line:
            end_idx = i
            break
            
    if start_idx == -1 or end_idx == -1:
        print("Could not find loop boundaries")
        return

    # Add lines before the loop
    new_lines.extend(lines[:start_idx])
    
    # Add try block
    new_lines.append(loop_indent + "try:\n")
    
    # Add indented loop body
    for i in range(start_idx, end_idx):
        new_lines.append("    " + lines[i])
        
    # Add except block
    except_block = [
        loop_indent + "except Exception as e:\n",
        loop_indent + "    # CRASH LANDING: Capture partial progress\n",
        loop_indent + "    # If we don't catch here, the exception bubbles up, rolling back the DB transaction\n",
        loop_indent + "    # and erasing all traces of what Agent B actually did.\n",
        loop_indent + "    return {\n",
        loop_indent + "        \"steps_completed\": steps_completed,\n",
        loop_indent + "        \"steps_failed\": steps_failed + 1,\n",
        loop_indent + "        \"total_steps\": total_steps_attempted + 1,\n",
        loop_indent + "        \"step_results\": step_results,\n",
        loop_indent + "        \"success\": False,\n",
        loop_indent + "        \"final_response\": f\"Agent B crashed: {str(e)}\",\n",
        loop_indent + "        \"narration_template\": f\"Agent B crashed: {str(e)}\",\n",
        loop_indent + "        \"output_values\": output_values,\n",
        loop_indent + "        \"output_value_types\": output_value_types,\n",
        loop_indent + "        \"output_value_sources\": output_value_sources,\n",
        loop_indent + "        \"template_values\": template_values,\n",
        loop_indent + "        \"response_segments\": [{\"kind\": \"text\", \"text\": f\"Agent B crashed: {str(e)}\"}],\n",
        loop_indent + "        \"agent_b_final_raw\": str(e),\n",
        loop_indent + "        \"missing_segments\": False,\n",
        loop_indent + "        \"error\": str(e)\n",
        loop_indent + "    }\n",
        "\n"
    ]
    new_lines.extend(except_block)
    
    # Add the rest of the file
    new_lines.extend(lines[end_idx:])
    
    with open(path, "w") as f:
        f.writelines(new_lines)
    print("Successfully patched orchestrator/orchestrator.py")

if __name__ == "__main__":
    patch_orchestrator()
