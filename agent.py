from config import Config, load_config
from tools import get_tool_schemas, TOOLS
from ui_formatter import ui, console
from utils.system_info import get_system_info, format_system_info
import openai
import json
import re
from rich.live import Live

class MiniAgent:
    # Configuration for message history management
    MAX_HISTORY_MESSAGES = 40
    MAX_TOOL_OUTPUT_CHARS = 8000
    
    def __init__(self):
        self.config = load_config()
        self.client = openai.OpenAI(
            base_url="https://api.minimax.io/v1",
            api_key=self.config.api_key
        )
        
        # Gather system information
        system_info = get_system_info()
        system_context = format_system_info(system_info)
        
        self.message_history = [
            {
                "role": "system",
                "content": f"""You are an AI-powered Linux shell terminal assistant. You can execute shell commands, read and write files, process content, and engage in conversation.

{system_context}

Available tools:
- read_file: Read the contents of a file
- write_file: Create or overwrite a file with content
- run_command: Execute a shell command (for non-interactive commands ONLY)
- run_interactive: Execute interactive commands that need terminal control (vim, nano, top, htop, less, man, etc.)
- chat: Provide a conversational response
- process_content: Analyze and process text content

CRITICAL: Never use run_command for interactive programs (vim, nano, less, top, htop, man, ssh, mysql, python REPL, etc.) — it will hang or timeout. Always use run_interactive for those.

When users ask questions:
1. General knowledge questions (facts, trivia, explanations): Answer directly using your knowledge base. Do NOT deflect or suggest terminal-related alternatives.
2. Interactive apps (vim, nano, top, htop, less, man, ssh, etc.): Use run_interactive tool to give full terminal control
3. Non-interactive terminal tasks (ls, cat, grep, find, etc.): Use run_command tool
4. File operations (read/write): Use read_file or write_file tools
5. Content processing tasks (analyze files, generate summaries): Use process_content tool
6. Conversational queries about the terminal or seeking help: Use chat tool or respond directly

Examples:
- "What is the population of Paris?" → Answer directly with factual information
- "Open vim to edit config.py" → Use run_interactive tool with 'vim config.py'
- "Edit test.txt with nano" → Use run_interactive tool with 'nano test.txt'
- "Show me running processes" → Use run_interactive tool with 'top' or 'htop'
- "List files in current directory" → Use run_command tool with 'ls'
- "Read config.py" → Use read_file tool
- "What can you do?" → Use chat tool or respond directly

Always prioritize safety and helpfulness. Provide accurate, direct answers to knowledge questions."""
            }
        ]
    
    def _trim_history(self):
        """Trim message history to prevent memory/token exhaustion"""
        # Truncate large tool outputs in ALL messages first
        for msg in self.message_history:
            if msg.get("role") == "tool" and isinstance(msg.get("content"), str):
                if len(msg["content"]) > self.MAX_TOOL_OUTPUT_CHARS:
                    extra = len(msg["content"]) - self.MAX_TOOL_OUTPUT_CHARS
                    msg["content"] = (
                        msg["content"][:self.MAX_TOOL_OUTPUT_CHARS] + 
                        f"\n...[truncated {extra} chars for brevity]"
                    )
        
        # Then trim message count if needed
        if len(self.message_history) > self.MAX_HISTORY_MESSAGES:
            # Keep system message (first) + recent messages
            system_msg = self.message_history[:1]
            recent_msgs = self.message_history[1:][-( self.MAX_HISTORY_MESSAGES - 1):]
            self.message_history = system_msg + recent_msgs

    def process_input(self, user_input: str) -> dict:
        """Process user input and return response with metadata"""
        ui.start_timer()
        self.message_history.append({"role": "user", "content": user_input})
        
        # Trim history before API call to prevent token exhaustion
        self._trim_history()
        
        tools = get_tool_schemas()
        max_steps = 10  # Prevent infinite loops
        step_count = 0
        
        while step_count < max_steps:
            try:
                # Show thinking indicator
                with Live(ui.show_thinking(), console=console, refresh_per_second=10):
                    response = self.client.chat.completions.create(
                        model=self.config.model,
                        messages=self.message_history,
                        max_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                        tools=tools
                    )
                
                if response.choices is None:
                    if hasattr(response, 'base_resp'):
                        base_resp = response.base_resp
                        if isinstance(base_resp, dict) and 'status_msg' in base_resp:
                            ui.error(f"API Error: {base_resp['status_msg']}")
                            return {"content": None, "error": base_resp['status_msg'], "elapsed_time": ui.get_elapsed_time()}
                        else:
                            ui.error("API Error: Unknown error occurred.")
                            return {"content": None, "error": "Unknown error", "elapsed_time": ui.get_elapsed_time()}
                    else:
                        ui.error("API Error: No base_resp found.")
                        return {"content": None, "error": "No base_resp found", "elapsed_time": ui.get_elapsed_time()}
                
                assistant_message = response.choices[0].message
                
            except Exception as e:
                ui.error(f"API Error: {str(e)}")
                return {"content": None, "error": str(e), "elapsed_time": ui.get_elapsed_time()}
            
            if assistant_message.tool_calls:
                self.message_history.append(assistant_message)
                
                # Show step indicator for multi-step operations
                if len(assistant_message.tool_calls) > 1 or step_count > 0:
                    ui.step_indicator(step_count + 1, max_steps, "Processing tools")
                
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    
                    # Guard against unknown tools
                    tool = TOOLS.get(tool_name)
                    if not tool:
                        tool_message = {
                            "role": "tool",
                            "content": f"Error: Unknown tool '{tool_name}'",
                            "tool_call_id": tool_call.id
                        }
                        self.message_history.append(tool_message)
                        continue
                    
                    # Guard against malformed JSON arguments
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except Exception as e:
                        tool_message = {
                            "role": "tool",
                            "content": f"Error: Invalid tool arguments JSON: {e}",
                            "tool_call_id": tool_call.id
                        }
                        self.message_history.append(tool_message)
                        continue
                    
                    # Show tool execution indicator
                    details = ""
                    if tool_name in ["run_command", "run_interactive"] and "command" in args:
                        details = args["command"]
                    elif tool_name in ["read_file", "write_file"] and "file_path" in args:
                        details = args["file_path"]
                    
                    # Special handling for interactive commands - don't wrap in Live spinner
                    if tool_name == "run_interactive":
                        ui.info(f"Launching interactive: {details}")
                        try:
                            result = tool.execute(**args)
                        except Exception as e:
                            result = f"Tool '{tool_name}' raised error: {e}"
                    else:
                        try:
                            with Live(ui.show_tool_execution(tool_name, details), console=console, refresh_per_second=10):
                                result = tool.execute(**args)
                        except Exception as e:
                            result = f"Tool '{tool_name}' raised error: {e}"
                    
                    tool_message = {
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tool_call.id
                    }
                    self.message_history.append(tool_message)
                    
                    # Trim history after tool execution to manage large outputs
                    self._trim_history()
            else:
                self.message_history.append(assistant_message)
                break
            
            step_count += 1
            if step_count >= max_steps:
                error_message = {
                    "role": "assistant",
                    "content": "Maximum tool calling steps exceeded. Please simplify your request."
                }
                self.message_history.append(error_message)
                ui.warning(error_message["content"])
                return {"content": error_message["content"], "error": None, "elapsed_time": ui.get_elapsed_time()}
        
        content = assistant_message.content or ""
        if self.config.hide_thinking:
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        
        return {
            "content": content,
            "error": None,
            "elapsed_time": ui.get_elapsed_time(),
            "steps": step_count
        }
