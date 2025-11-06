from config import Config, load_config
from tools import get_tool_schemas, TOOLS, WORKING_DIR_PREFIX, _SESSION_STATE
from ui_formatter import ui, console
from utils.system_info import get_system_info, format_system_info
from db_logger import DBLogger
import openai
import json
import re
import atexit
import os
from pathlib import Path
from rich.live import Live

class MiniAgent:
    # Configuration for message history management
    MAX_HISTORY_MESSAGES = 40
    MAX_TOOL_OUTPUT_CHARS = 8000
    
    def __init__(self):
        self.config = load_config()
        self.client = openai.OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key
        )
        
        # Gather system information
        system_info = get_system_info()
        system_context = format_system_info(system_info)
        
        # Setup database logging
        self.db_logger = DBLogger()
        self.session_id = self.db_logger.start_session(system_info)
        atexit.register(self.db_logger.close)
        
        # Initialize session state for context tracking
        _SESSION_STATE.reset(self.session_id)
        
        # Tool output collector for deterministic rendering
        self._current_step_tool_outputs = []
        
        # Build system prompt with available tools
        system_prompt = self._build_system_prompt(system_context)
        self.message_history = [{"role": "system", "content": system_prompt}]
    
    def _format_tools_for_prompt(self) -> str:
        """Generate a formatted list of available agent tools for the system prompt"""
        lines = ["Available agent tools:"]
        for name in sorted(TOOLS.keys()):
            desc = getattr(TOOLS[name], "description", "") or ""
            # Flatten whitespace and newlines to keep one line per tool
            desc = " ".join(desc.strip().split())
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)
    
    def _load_sandbox_manifest(self):
        """Load sandbox manifest if isolation is enabled"""
        if os.getenv("SANDBOX_ENABLE_ISOLATION") != "1":
            return None
        
        # Load manifest from extracted rootfs (not host /etc)
        try:
            from sandbox_rootfs import get_rootfs_sha256, extract_rootfs, load_manifest
            
            sha256 = get_rootfs_sha256()
            if not sha256:
                return None
            
            # Extract rootfs (cached, fast if already extracted)
            rootfs_path = extract_rootfs(sha256)
            
            # Load manifest from extracted rootfs
            return load_manifest(rootfs_path)
        except Exception:
            return None
    
    def _format_sandbox_info(self, manifest: dict) -> str:
        """Format sandbox information for system prompt"""
        if not manifest:
            return ""
        
        lines = ["\nSandbox Environment (Isolated):"]
        
        # Python info
        py_info = manifest.get("python", {})
        py_ver = py_info.get("version", "unknown")
        lines.append(f"- Python {py_ver} at {py_info.get('path', '/opt/venv/bin/python3')}")
        
        # Top packages
        packages = manifest.get("python_packages", {})
        if packages:
            pkg_list = ", ".join(f"{k} {v}" for k, v in list(packages.items())[:6])
            if len(packages) > 6:
                pkg_list += f", ... ({len(packages)} total)"
            lines.append(f"- Packages: {pkg_list}")
        
        # Shell commands
        shell_cmds = manifest.get("shell_commands", {})
        if "data_tools" in shell_cmds:
            tools = ", ".join(shell_cmds["data_tools"])
            lines.append(f"- Data tools: {tools}")
        
        # Command examples
        examples = manifest.get("command_examples", {})
        if examples:
            lines.append("\nKey command examples:")
            for cmd, info in list(examples.items())[:5]:
                if isinstance(info, dict) and "examples" in info:
                    example = info["examples"][0] if info["examples"] else ""
                    if example:
                        lines.append(f"  • {example}")
        
        lines.append("\nAll tools listed in /etc/sandbox_manifest.json")
        
        return "\n".join(lines)
    
    def _build_system_prompt(self, system_context: str) -> str:
        """Build the complete system prompt with tools, context, and guidelines"""
        tools_block = self._format_tools_for_prompt()
        
        # Load and format sandbox info if isolation enabled
        manifest = self._load_sandbox_manifest()
        sandbox_info = self._format_sandbox_info(manifest)
        
        return f"""Shell automation expert and conversational assistant. Execute commands, write scripts, manage files, and engage in helpful dialogue.

{tools_block}

{system_context}

{sandbox_info}

Working directory and path rules:
- run_command: Always executes from {WORKING_DIR_PREFIX}/ (auto cd each call). Use relative paths like ./file.py. To read project files, use ../path (e.g., cat ../agent.py). Never write outside working dir—no ../ in redirects.
- write_file: Paths are relative to {WORKING_DIR_PREFIX}/. Do NOT include the '{WORKING_DIR_PREFIX}/' prefix in file_path.
- read_file: Relative path; searches {WORKING_DIR_PREFIX}/ first, then project root.

Tool usage notes:
- Philosophy: Prefer shell commands (run_command) over Python/scripts. Shell is faster, more elegant, less compute. Use grep/sed/awk/cut/sort/uniq/tr/head/tail/find/xargs/jq/bc pipelines for text/data/math processing. Only use run_python_sandbox for: visualization, ML/data science, or when task explicitly requires Python libraries.
- get_context: Retrieve comprehensive session context: execution state (working_dir, shell_cwd, recent_writes), session history (tool calls, exit codes, errors), configuration (sandbox limits, isolation), repository state (branch, uncommitted changes), and available interpreters. Use for debugging or checking state. Prefer this over pwd/ls/git status/env when you just need state.
- run_python_sandbox: Prefer writing a single consolidated script and running once. Before running a Python file, validate with: python -m py_compile ./file.py
- run_interactive: Only for full-screen/interactive programs.

Execution strategy:
- Respond directly without tools unless task requires file access, commands, or computation
- Plan your tools: write scripts once, then run them. Avoid multiple run_python_sandbox calls for separate demos—combine in one script with functions and run once
- Prefer shell pipelines (grep, sed, awk, cut, sort) over multiple tool calls—combine operations efficiently
- Only run pwd/ls/git status/env when you need the actual listing/output
- Provide final answers after tool execution without redundant tool calls

Context inspection (get_context) triggers:
- When to call get_context (fast, read-only):
  • At the start of a task if session/repo/sandbox state is unclear
  • After any failure or non-zero exit (to inspect recent_errors, tool_history, exit codes)
  • When checking environment/project state (instead of pwd/ls/git status/env)
  • Before run_python_sandbox to confirm sandbox limits and available interpreters

Output and rendering:
- Output policy: summarize by default; paste command/file output only when it answers the user's request or is necessary to show results
- Interactive tools (run_interactive): Output is streamed to terminal automatically. Do not summarize or reprint.
- Non-interactive tools (run_command, read_file, etc.): Include relevant output directly in your response when the user asks to see something.
  * For info display commands (cal, date, ls, cat, etc.), paste the actual output in a code block.
  * For actions/modifications, confirm what was done and show relevant results.
  * Keep it natural - if showing a calendar, introduce it briefly then show it."""
    
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
    
    def _trim_history(self):
        """Simple history trimming: keep last N messages, truncate long tool outputs"""
        if len(self.message_history) <= self.MAX_HISTORY_MESSAGES:
            return
        
        # Keep system message + last MAX_HISTORY_MESSAGES
        system_msg = self.message_history[0]
        messages = [self._to_dict_message(m) for m in self.message_history[1:]]
        recent = messages[-(self.MAX_HISTORY_MESSAGES):]
        
        # Truncate only extremely long tool outputs
        for msg in recent:
            if isinstance(msg, dict) and msg.get("role") == "tool":
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > self.MAX_TOOL_OUTPUT_CHARS:
                    extra = len(content) - self.MAX_TOOL_OUTPUT_CHARS
                    msg["content"] = content[:self.MAX_TOOL_OUTPUT_CHARS] + f"\n...[truncated {extra} chars]"
        
        self.message_history = [system_msg] + recent

    def process_input(self, user_input: str) -> dict:
        """Process user input and return response with metadata"""
        ui.start_timer()
        
        # Track user interaction
        _SESSION_STATE.increment_interactions()
        
        # Clear tool output collector for new turn
        self._current_step_tool_outputs = []
        
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
                    
                    # Log tool call
                    args_str = json.dumps(args, indent=2)
                    tool_call_content = f"Tool: {tool_name}\nArguments:\n{args_str}"
                    self._log("TOOL_CALL", tool_call_content)
                    
                    # Show tool execution indicator
                    details = ""
                    if tool_name in ["run_command", "run_interactive"] and "command" in args:
                        details = args["command"]
                    elif tool_name in ["read_file", "write_file"] and "file_path" in args:
                        details = args["file_path"]
                    
                    # Special handling for interactive commands - don't wrap in Live spinner
                    success = True
                    error_msg = None
                    exit_code = None
                    
                    if tool_name == "run_interactive":
                        ui.info(f"Launching interactive: {details}")
                        try:
                            result = tool.execute(**args)
                        except Exception as e:
                            result = f"Tool '{tool_name}' raised error: {e}"
                            success = False
                            error_msg = str(e)
                            _SESSION_STATE.record_error(tool_name, str(e), args)
                    else:
                        try:
                            with Live(ui.show_tool_execution(tool_name, details), console=console, refresh_per_second=10):
                                result = tool.execute(**args)
                        except Exception as e:
                            result = f"Tool '{tool_name}' raised error: {e}"
                            success = False
                            error_msg = str(e)
                            _SESSION_STATE.record_error(tool_name, str(e), args)
                    
                    # Extract exit code from result if available
                    if tool_name == "run_command" and success:
                        # Exit code is already set in _SESSION_STATE by ShellIntegration
                        exit_code = _SESSION_STATE.last_exit_code
                    elif tool_name == "run_python_sandbox" and success:
                        # Parse exit code from result (if present in manifest)
                        # Will be enhanced when we parse sandbox manifest
                        pass
                    
                    # Record tool call in session state
                    _SESSION_STATE.record_tool_call(
                        tool_name=tool_name,
                        args=args,
                        success=success,
                        exit_code=exit_code,
                        error=error_msg
                    )
                    
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
                    
                    # Collect tool output for deterministic rendering
                    self._current_step_tool_outputs.append({
                        "tool": tool_name,
                        "args": args,
                        "result": result if isinstance(result, str) else str(result)
                    })
                    
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
        
        # Check if this turn only used run_interactive
        only_interactive = (
            self._current_step_tool_outputs and
            all(output["tool"] == "run_interactive" for output in self._current_step_tool_outputs)
        )
        
        if only_interactive:
            # For interactive tools, skip LLM commentary - just show tool results
            content = "\n\n".join(output["result"] for output in self._current_step_tool_outputs)
        else:
            content = assistant_message.content or ""
            if self.config.hide_thinking:
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            
            # Only inject raw outputs when SHOW_RAW_OUTPUT is explicitly enabled
            if self._current_step_tool_outputs and self.config.show_raw_output:
                raw_blocks = []
                for output in self._current_step_tool_outputs:
                    # Get result and truncate if needed
                    result = output["result"]
                    if len(result) > self.config.raw_output_max_chars:
                        truncated = len(result) - self.config.raw_output_max_chars
                        result = result[:self.config.raw_output_max_chars] + f"\n...[truncated {truncated} chars]"
                    
                    # Show command if it's a command tool
                    cmd = output["args"].get("command")
                    if cmd and output["tool"] == "run_command":
                        raw_blocks.append(f"$ {cmd}\n{result}")
                    else:
                        # For non-command tools, just show result
                        raw_blocks.append(result)
                
                raw_output = "\n\n".join(raw_blocks).rstrip()
                if raw_output:
                    content = f"```terminal\n{raw_output}\n```\n\n{content}"
        
        # Log final response
        self._log("ASSISTANT_RESPONSE", content)
        
        return {
            "content": content,
            "error": None,
            "elapsed_time": ui.get_elapsed_time(),
            "steps": step_count
        }
