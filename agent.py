from config import Config, load_config
from tools import get_tool_schemas, TOOLS
from ui_formatter import ui, console
from utils.system_info import get_system_info, format_system_info
from db_logger import DBLogger
import openai
import json
import re
import atexit
import uuid
import os
from typing import Dict, Optional
from rich.live import Live

class MiniAgent:
    # Configuration for message history management
    MAX_HISTORY_MESSAGES = 40
    MAX_TOOL_OUTPUT_CHARS = 8000
    
    # New: Advanced trimming configuration
    MAX_RECENT_MESSAGES = 10  # Keep full detail for last 10 messages
    SUMMARIZE_THRESHOLD = 20  # Summarize messages older than this
    OLD_TOOL_OUTPUT_CHARS = 2000  # More aggressive truncation for old messages
    APPROXIMATE_TOKEN_BUDGET = 6000  # Rough token limit for history (excluding system)
    
    def __init__(self):
        self.config = load_config()
        self.client = openai.OpenAI(
            base_url="https://api.minimax.io/v1",
            api_key=self.config.api_key
        )
        
        # Gather system information
        system_info = get_system_info()
        system_context = format_system_info(system_info)
        
        # Setup database logging
        self.db_logger = DBLogger()
        self.session_id = self.db_logger.start_session(system_info)
        atexit.register(self.db_logger.close)
        
        # Secret store for session (never logged/persisted)
        self.secrets: Dict[str, str] = {}
        self.pending_request: Optional[dict] = None
        self.pending_state: Optional[dict] = None
        atexit.register(self._clear_secrets)
        
        # Minimal system prompt: only essential information
        self.message_history = [
            {
                "role": "system",
                "content": f"""Linux shell assistant with file management, command execution, and content processing.

{system_context}

Tools: read_file, write_file, run_command, run_sudo_command, run_interactive, chat, process_content
- Use run_sudo_command for commands requiring root privileges (omit 'sudo' prefix, password will be requested)
- Use run_interactive (not run_command) for vim, nano, less, top, htop, man, ssh, mysql, python REPL

CRITICAL: ALWAYS show command output verbatim in a code block first, then provide interpretation."""
            }
        ]
    
    def _clear_secrets(self):
        """Clear all secrets from memory"""
        self.secrets.clear()
    
    def _mask_args(self, tool_name: str, args: dict) -> dict:
        """Mask sensitive arguments for logging"""
        if tool_name == "run_sudo_command" and "password" in args:
            return {**args, "password": "***"}
        return args
    
    def _log(self, log_type: str, content: str):
        """Safe logging wrapper that prevents DB failures from crashing flows"""
        try:
            self.db_logger.log_entry(self.session_id, log_type, content)
        except Exception as e:
            ui.warning(f"Logging failed: {e}")

    def _to_dict_message(self, msg) -> dict:
        """Convert ChatCompletionMessage or dict to plain dict for storage"""
        if isinstance(msg, dict):
            d = dict(msg)
            # Normalize content to string
            if "content" in d and d["content"] is not None and not isinstance(d["content"], str):
                d["content"] = str(d["content"])
            return d
        
        # ChatCompletionMessage -> dict
        role = getattr(msg, "role", "")
        content = getattr(msg, "content", "") or ""
        out = {"role": role, "content": content}
        
        # Optional fields for tool/assistant messages
        for attr in ("name", "tool_call_id"):
            val = getattr(msg, attr, None)
            if val:
                out[attr] = val
        
        # Handle tool_calls (convert to dict and ensure arguments is JSON string)
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            tc_list = []
            for tc in tool_calls:
                fn = getattr(tc, "function", None)
                args = getattr(fn, "arguments", "{}") if fn else "{}"
                if not isinstance(args, str):
                    try:
                        args = json.dumps(args)
                    except Exception:
                        args = str(args)
                tc_list.append({
                    "id": getattr(tc, "id", None),
                    "type": getattr(tc, "type", "function") or "function",
                    "function": {"name": getattr(fn, "name", ""), "arguments": args}
                })
            out["tool_calls"] = tc_list
        
        return out
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation: ~4 chars per token for English"""
        if not text:
            return 0
        return len(text) // 4
    
    def _get_role(self, msg) -> str:
        """Safely get role from either dict or ChatCompletionMessage"""
        if isinstance(msg, dict):
            return msg.get("role", "")
        return getattr(msg, "role", "")
    
    def _summarize_message_pair(self, user_msg: dict, assistant_msg: dict) -> dict:
        """Summarize a user-assistant message exchange into a compact form"""
        user_content = user_msg.get("content", "")
        
        # Handle assistant message - could be dict or ChatCompletionMessage
        if isinstance(assistant_msg, dict):
            assistant_content = assistant_msg.get("content", "")
            tool_calls = assistant_msg.get("tool_calls", [])
        else:
            assistant_content = getattr(assistant_msg, "content", "") or ""
            tool_calls = getattr(assistant_msg, "tool_calls", [])
        
        # Create summary
        summary_parts = []
        
        # Summarize user request
        user_summary = user_content[:200] if len(user_content) > 200 else user_content
        summary_parts.append(f"User: {user_summary}")
        
        # Summarize tool usage
        if tool_calls:
            tool_names = [tc.function.name if hasattr(tc, 'function') else tc.get('function', {}).get('name', 'unknown') for tc in tool_calls]
            summary_parts.append(f"Tools used: {', '.join(tool_names)}")
        
        # Summarize response
        if assistant_content:
            response_summary = assistant_content[:200] if len(assistant_content) > 200 else assistant_content
            summary_parts.append(f"Response: {response_summary}")
        
        return {
            "role": "user",
            "content": f"[SUMMARY] {' | '.join(summary_parts)}"
        }
    
    def _trim_history(self):
        """Advanced message history trimming with summarization and token budgeting"""
        if len(self.message_history) <= 1:
            return
        
        # Keep system message separate
        system_msg = self.message_history[0]
        messages = self.message_history[1:]
        
        # Normalize all messages to dicts to prevent serialization issues
        messages = [self._to_dict_message(m) for m in messages]
        
        # Step 1: Truncate tool outputs based on age
        for i, msg in enumerate(messages):
            if isinstance(msg, dict) and msg.get("role") == "tool":
                content = msg.get("content", "")
                if isinstance(content, str):
                    # Recent messages: keep more content
                    if i >= len(messages) - self.MAX_RECENT_MESSAGES:
                        max_chars = self.MAX_TOOL_OUTPUT_CHARS
                    else:
                        max_chars = self.OLD_TOOL_OUTPUT_CHARS
                    
                    if len(content) > max_chars:
                        extra = len(content) - max_chars
                        msg["content"] = (
                            content[:max_chars] + 
                            f"\n...[truncated {extra} chars]"
                        )
        
        # Step 2: Summarize old conversation pairs
        if len(messages) > self.SUMMARIZE_THRESHOLD:
            messages_to_keep = messages[-(self.SUMMARIZE_THRESHOLD):]
            messages_to_summarize = messages[:-(self.SUMMARIZE_THRESHOLD)]
            
            summarized = []
            i = 0
            while i < len(messages_to_summarize):
                msg = messages_to_summarize[i]
                
                # Try to pair user message with next assistant message
                if self._get_role(msg) == "user" and i + 1 < len(messages_to_summarize):
                    next_msg = messages_to_summarize[i + 1]
                    if self._get_role(next_msg) == "assistant":
                        # Summarize the pair
                        summary = self._summarize_message_pair(msg, next_msg)
                        summarized.append(summary)
                        i += 2
                        # Skip associated tool messages
                        while i < len(messages_to_summarize) and self._get_role(messages_to_summarize[i]) == "tool":
                            i += 1
                        continue
                
                # If can't pair, keep as-is but truncate if needed
                if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                    if len(msg["content"]) > 500:
                        msg["content"] = msg["content"][:500] + "...[truncated]"
                summarized.append(msg)
                i += 1
            
            messages = summarized + messages_to_keep
        
        # Step 3: Enforce message count limit
        if len(messages) > self.MAX_HISTORY_MESSAGES:
            messages = messages[-(self.MAX_HISTORY_MESSAGES):]
        
        # Step 4: Token budget enforcement (approximate)
        estimated_tokens = sum(self._estimate_tokens(
            msg.get("content", "") if isinstance(msg, dict) else str(msg)
        ) for msg in messages)
        
        # If still over budget, drop oldest non-summary messages
        while estimated_tokens > self.APPROXIMATE_TOKEN_BUDGET and len(messages) > 5:
            # Remove oldest message
            removed = messages.pop(0)
            removed_content = removed.get("content", "") if isinstance(removed, dict) else str(removed)
            estimated_tokens -= self._estimate_tokens(removed_content)
        
        self.message_history = [system_msg] + messages

    def process_input(self, user_input: str) -> dict:
        """Process user input and return response with metadata"""
        ui.start_timer()
        
        # Log incoming user query
        self._log("USER_QUERY", user_input)
        
        self.message_history.append({"role": "user", "content": user_input})
        
        # Trim history before API call to prevent token exhaustion
        self._trim_history()
        
        tools = get_tool_schemas()
        max_steps = self.config.max_steps  # Configurable via .env (default: 15)
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
                self.message_history.append(self._to_dict_message(assistant_message))
                
                # Show step indicator for multi-step operations
                if len(assistant_message.tool_calls) > 1 or step_count > 0:
                    ui.step_indicator(step_count + 1, max_steps, "Processing tools")
                
                for tc_idx, tool_call in enumerate(assistant_message.tool_calls):
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
                    
                    # Handle sudo password injection or request
                    if tool_name == "run_sudo_command" and not args.get("password"):
                        cached = self.secrets.get("sudo_password")
                        if cached:
                            # Auto-inject cached password
                            args["password"] = cached
                        else:
                            # Need to request password from user
                            try:
                                username = os.getlogin()
                            except:
                                username = "user"
                            
                            req_id = str(uuid.uuid4())
                            request = {
                                "id": req_id,
                                "type": "sudo_password",
                                "prompt": f"Enter sudo password for {username}",
                                "cache_key": "sudo_password",
                                "secret": True
                            }
                            
                            # Save state to resume after password provided
                            self.pending_request = request
                            self.pending_state = {
                                "assistant_message": self._to_dict_message(assistant_message),
                                "tc_idx": tc_idx,
                                "step_count": step_count,
                                "args": args,
                                "tool_name": tool_name,
                                "tool_call_id": tool_call.id
                            }
                            
                            # Return request to main
                            return {
                                "content": None,
                                "error": None,
                                "elapsed_time": ui.get_elapsed_time(),
                                "request": request
                            }
                    
                    # Log tool call (with password masked)
                    redacted_args = self._mask_args(tool_name, args)
                    args_str = json.dumps(redacted_args, indent=2)
                    tool_call_content = f"Tool: {tool_name}\nArguments:\n{args_str}"
                    self._log("TOOL_CALL", tool_call_content)
                    
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
                    
                    # Log tool result (with truncation for large outputs)
                    result_str = result if isinstance(result, str) else str(result)
                    if len(result_str) > 32768:
                        extra = len(result_str) - 32768
                        result_str = result_str[:32768] + f"\n...[truncated {extra} chars]"
                    self._log("TOOL_RESULT", result_str)
                    
                    tool_message = {
                        "role": "tool",
                        "content": result if isinstance(result, str) else str(result),
                        "tool_call_id": tool_call.id
                    }
                    self.message_history.append(tool_message)
                    
                    # Trim history after tool execution to manage large outputs
                    self._trim_history()
            else:
                self.message_history.append(self._to_dict_message(assistant_message))
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
        
        # Safety check: if we exit the loop without breaking, return error
        if step_count >= max_steps:
            return {
                "content": "Maximum processing steps reached without a final answer.",
                "error": "max_steps_exceeded",
                "elapsed_time": ui.get_elapsed_time()
            }
        
        content = assistant_message.content or ""
        if self.config.hide_thinking:
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        
        # Log final response
        self._log("ASSISTANT_RESPONSE", content)
        
        return {
            "content": content,
            "error": None,
            "elapsed_time": ui.get_elapsed_time(),
            "steps": step_count
        }
    
    def provide_secret(self, request_id: str, value: str) -> dict:
        """Resume execution after user provides a secret (e.g., sudo password)"""
        # Validate pending request
        if not self.pending_request or self.pending_request.get("id") != request_id:
            return {
                "content": None,
                "error": "No pending request or mismatched request ID",
                "elapsed_time": ui.get_elapsed_time()
            }
        
        # Cache the secret for session
        cache_key = self.pending_request.get("cache_key")
        if cache_key:
            self.secrets[cache_key] = value
        
        # Restore saved state
        state = self.pending_state
        args = state["args"].copy()
        args["password"] = value  # Inject the password
        tool_name = state["tool_name"]
        tool_call_id = state["tool_call_id"]
        tc_idx = state["tc_idx"]
        step_count = state["step_count"]
        assistant_message = state["assistant_message"]
        
        # Clear pending state
        self.pending_request = None
        self.pending_state = None
        
        # Execute the pending tool
        tool = TOOLS.get(tool_name)
        if not tool:
            return {
                "content": None,
                "error": f"Tool '{tool_name}' not found",
                "elapsed_time": ui.get_elapsed_time()
            }
        
        # Show tool execution
        details = args.get("command", "") if tool_name == "run_sudo_command" else ""
        try:
            with Live(ui.show_tool_execution(tool_name, details), console=console, refresh_per_second=10):
                result = tool.execute(**args)
        except Exception as e:
            result = f"Tool '{tool_name}' raised error: {e}"
        
        # Log tool result (with truncation)
        result_str = result if isinstance(result, str) else str(result)
        if len(result_str) > 32768:
            extra = len(result_str) - 32768
            result_str = result_str[:32768] + f"\n...[truncated {extra} chars]"
        self._log("TOOL_RESULT", result_str)
        
        # Append tool result to history
        tool_message = {
            "role": "tool",
            "content": result if isinstance(result, str) else str(result),
            "tool_call_id": tool_call_id
        }
        self.message_history.append(tool_message)
        self._trim_history()
        
        # Continue processing remaining tool calls for this assistant turn
        if "tool_calls" in assistant_message:
            tool_calls = assistant_message["tool_calls"]
            for i in range(tc_idx + 1, len(tool_calls)):
                tc = tool_calls[i]
                remaining_tool_name = tc["function"]["name"]
                remaining_tool = TOOLS.get(remaining_tool_name)
                
                if not remaining_tool:
                    self.message_history.append({
                        "role": "tool",
                        "content": f"Error: Unknown tool '{remaining_tool_name}'",
                        "tool_call_id": tc["id"]
                    })
                    continue
                
                try:
                    remaining_args = json.loads(tc["function"]["arguments"] or "{}")
                except Exception as e:
                    self.message_history.append({
                        "role": "tool",
                        "content": f"Error: Invalid tool arguments JSON: {e}",
                        "tool_call_id": tc["id"]
                    })
                    continue
                
                # Auto-inject sudo password if needed
                if remaining_tool_name == "run_sudo_command" and not remaining_args.get("password"):
                    cached = self.secrets.get("sudo_password")
                    if cached:
                        remaining_args["password"] = cached
                
                # Execute remaining tool
                try:
                    remaining_details = remaining_args.get("command", "") if remaining_tool_name == "run_sudo_command" else ""
                    with Live(ui.show_tool_execution(remaining_tool_name, remaining_details), console=console, refresh_per_second=10):
                        remaining_result = remaining_tool.execute(**remaining_args)
                except Exception as e:
                    remaining_result = f"Tool '{remaining_tool_name}' raised error: {e}"
                
                # Log and append result
                remaining_result_str = remaining_result if isinstance(remaining_result, str) else str(remaining_result)
                if len(remaining_result_str) > 32768:
                    extra = len(remaining_result_str) - 32768
                    remaining_result_str = remaining_result_str[:32768] + f"\n...[truncated {extra} chars]"
                self._log("TOOL_RESULT", remaining_result_str)
                
                self.message_history.append({
                    "role": "tool",
                    "content": remaining_result if isinstance(remaining_result, str) else str(remaining_result),
                    "tool_call_id": tc["id"]
                })
                self._trim_history()
        
        # Now continue the normal LLM loop to get final response
        tools = get_tool_schemas()
        max_steps = self.config.max_steps
        
        while step_count < max_steps:
            try:
                with Live(ui.show_thinking(), console=console, refresh_per_second=10):
                    response = self.client.chat.completions.create(
                        model=self.config.model,
                        messages=self.message_history,
                        max_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                        tools=tools
                    )
                
                if response.choices is None:
                    return {
                        "content": None,
                        "error": "API error after resume",
                        "elapsed_time": ui.get_elapsed_time()
                    }
                
                next_message = response.choices[0].message
            except Exception as e:
                ui.error(f"API Error: {str(e)}")
                return {
                    "content": None,
                    "error": str(e),
                    "elapsed_time": ui.get_elapsed_time()
                }
            
            if next_message.tool_calls:
                # Continue tool calling loop (similar to process_input)
                self.message_history.append(self._to_dict_message(next_message))
                
                for tool_call in next_message.tool_calls:
                    # Process tool calls (shortened version - reuse logic)
                    tool_name = tool_call.function.name
                    tool = TOOLS.get(tool_name)
                    
                    if not tool:
                        self.message_history.append({
                            "role": "tool",
                            "content": f"Error: Unknown tool '{tool_name}'",
                            "tool_call_id": tool_call.id
                        })
                        continue
                    
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except Exception as e:
                        self.message_history.append({
                            "role": "tool",
                            "content": f"Error: Invalid tool arguments JSON: {e}",
                            "tool_call_id": tool_call.id
                        })
                        continue
                    
                    # Auto-inject password if needed
                    if tool_name == "run_sudo_command" and not args.get("password"):
                        cached = self.secrets.get("sudo_password")
                        if cached:
                            args["password"] = cached
                    
                    # Execute tool
                    try:
                        result = tool.execute(**args)
                    except Exception as e:
                        result = f"Tool '{tool_name}' raised error: {e}"
                    
                    self.message_history.append({
                        "role": "tool",
                        "content": result if isinstance(result, str) else str(result),
                        "tool_call_id": tool_call.id
                    })
                    self._trim_history()
                
                step_count += 1
            else:
                # Got final answer
                self.message_history.append(self._to_dict_message(next_message))
                content = next_message.content or ""
                if self.config.hide_thinking:
                    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                
                self._log("ASSISTANT_RESPONSE", content)
                
                return {
                    "content": content,
                    "error": None,
                    "elapsed_time": ui.get_elapsed_time(),
                    "steps": step_count
                }
        
        return {
            "content": "Maximum processing steps reached after resume.",
            "error": "max_steps_exceeded",
            "elapsed_time": ui.get_elapsed_time()
        }
