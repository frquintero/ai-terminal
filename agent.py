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
import uuid
from pathlib import Path
from rich.live import Live

class MiniAgent:
    # Configuration for message history management
    MAX_HISTORY_MESSAGES = 40
    MAX_TOOL_OUTPUT_CHARS = 8000
    MAX_REACT_LOOPS = 4
    
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

Tool decision gate:
- When choosing tools: (1) Shell-first for text/math/file ops (2) Python only for pandas/plots/ML (3) If shell can do it in <5 lines, never use sandbox.
- Before calling run_python_sandbox, whisper "Could awk/sed/jq/bc do this?" If yes -> use shell.
- Tool costs: run_command = fast/cheap, run_python_sandbox = heavy (slow startup, >50MB RAM). If you just used Python for CSV/regex/math, you probably chose the wrong tool - switch to shell.

Workflow priorities:
1. State first: Call get_context for SNAP moments (Start of task, Non-zero exit, All-state check, Pre-sandbox). It's faster than running pwd/ls/git status/env.
2. Shell-first: Use run_command with awk/sed/cut/sort/uniq/head/tail/find/xargs/jq/bc for text, math, and file tasks.
3. Sandbox sparingly: run_python_sandbox only when pandas/plots/ML or specific Python libs are required - bundle work into one script/run.

ReAct loop rules:
- Every reply must start with `Thought:` (brief plan). Follow with either `Action: {{\"tool\": \"name\", \"arguments\": {{...}}}}` or `Final Answer: ...`.
- Action JSON must match an available tool schema exactly; omit speculative actions.
- Wait for `Observation` messages (tool outputs) before issuing another Action. Keep loops under 4 iterations unless user insists.

Working directory rules:
- run_command auto-CDs into {WORKING_DIR_PREFIX}/; use relative paths (./file.py). Never write outside that directory (no ../ redirects).
- write_file paths are relative to {WORKING_DIR_PREFIX}/ (do not prefix it).
- read_file searches {WORKING_DIR_PREFIX}/ first, then the project root.

Key tools:
- run_command - primary executor; compose pipelines for efficient processing.
- get_context - cheap JSON snapshot (cwd, git branch, tool history, errors, sandbox limits). Use instead of manual environment probes.
- run_python_sandbox - isolated Python with data-science stack and write guards; only for workloads shell cannot handle.
- read_file / write_file - direct file access within the working directory.
- run_interactive - launch full-screen programs (vim, top); user must interact directly.

Example:
User: "What branch are we on and what failed last?" -> Call get_context, report branch, last exit code, recent errors, then continue.

Execution style:
- Plan before running tools; prefer single well-crafted commands/scripts over many small ones.
- Provide concise summaries; include raw command output only when requested or essential (show info commands in fenced blocks).
- Interactive tool output streams directly - do not echo it.

{tools_block}

{system_context}

{sandbox_info}"""

    @staticmethod
    def _extract_json_object(text: str) -> str | None:
        """Extract the first balanced JSON object from text (supports fences)."""
        if not text:
            return None
        stripped = text.strip()
        if stripped.startswith("```"):
            fence_end = stripped.find("```", 3)
            if fence_end != -1:
                stripped = stripped[3:fence_end].strip()
        start = stripped.find("{")
        if start == -1:
            return None
        depth = 0
        for idx in range(start, len(stripped)):
            char = stripped[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return stripped[start:idx + 1]
        return None

    @staticmethod
    def _parse_react_directives(content: str | None) -> dict:
        """Parse Thought/Action/Final Answer directives from assistant content."""
        parsed = {"thought": None, "action": None, "final_answer": None}
        if not content:
            return parsed

        text = content.strip()

        thought_match = re.search(
            r"Thought:\s*(.*?)(?:\n(?:Action|Final Answer):|$)",
            text,
            re.DOTALL
        )
        if thought_match:
            parsed["thought"] = thought_match.group(1).strip()

        action_idx = text.find("Action:")
        if action_idx != -1:
            action_block = text[action_idx + len("Action:") :]
            json_blob = MiniAgent._extract_json_object(action_block)
            if json_blob:
                try:
                    action_payload = json.loads(json_blob)
                    if isinstance(action_payload, dict) and "tool" in action_payload:
                        parsed["action"] = action_payload
                except json.JSONDecodeError:
                    pass

        final_idx = text.find("Final Answer:")
        if final_idx != -1:
            parsed["final_answer"] = text[final_idx + len("Final Answer:") :].strip()

        return parsed

    @classmethod
    def _format_observation_content(
        cls,
        tool_name: str,
        result: str,
        success: bool,
        exit_code: int | None,
        error_msg: str | None
    ) -> str:
        """Format observation payload for ReAct loop history."""
        preview = result
        if len(preview) > cls.MAX_TOOL_OUTPUT_CHARS:
            truncated = len(preview) - cls.MAX_TOOL_OUTPUT_CHARS
            preview = preview[: cls.MAX_TOOL_OUTPUT_CHARS] + f"\n...[truncated {truncated} chars]"

        observation = {
            "tool": tool_name,
            "success": success,
            "exit_code": exit_code,
            "error": error_msg,
            "output_preview": preview
        }
        return f"Observation:\n{json.dumps(observation, indent=2)}"

    @staticmethod
    def _summarize_action(tool_name: str, args: dict) -> str:
        """Generate a compact human-readable summary for a tool action."""
        if tool_name == "run_command":
            cmd = args.get("command")
            if cmd:
                return f"run_command: {cmd}"
        elif tool_name in ("read_file", "write_file"):
            path = args.get("file_path")
            if path:
                return f"{tool_name}: {path}"
        elif tool_name == "run_python_sandbox":
            entrypoint = args.get("entrypoint") or "script"
            return f"{tool_name}: {entrypoint}"
        return tool_name

    @staticmethod
    def _build_plan_reminder_text(
        thought: str | None,
        executed_actions: list[str]
    ) -> str | None:
        """Create reminder text tying next actions to the previous Thought."""
        if not thought:
            return None
        actions_label = "; ".join(executed_actions) if executed_actions else "none"
        reminder = (
            f"Plan reminder: Thought -> {thought}. "
            f"Actions executed -> {actions_label}. "
            "Only run another Action if it advances this plan; otherwise emit a new Thought first."
        )
        return reminder

    def _append_plan_reminder(
        self,
        thought: str | None,
        executed_actions: list[str]
    ):
        reminder = self._build_plan_reminder_text(thought, executed_actions)
        if reminder:
            self.message_history.append({"role": "system", "content": reminder})
    
    def _sanitize_history_tool_calls(self):
        """
        Normalize message history and gather tool-call state for diagnostics.
        Returns metadata describing assistant/tool relationships without mutating content.
        """
        normalized_messages = []
        assistant_tool_calls: list[dict[str, Any]] = []
        tool_messages: list[dict[str, Any]] = []
        
        for msg in self.message_history:
            if not isinstance(msg, dict):
                msg = self._to_dict_message(msg)
            normalized_messages.append(msg)
        
        self.message_history = normalized_messages
        
        for idx, msg in enumerate(self.message_history):
            role = msg.get("role")
            if role == "assistant" and msg.get("tool_calls"):
                normalized_calls = self._normalize_tool_calls(msg["tool_calls"])
                msg["tool_calls"] = normalized_calls
                for tc in normalized_calls:
                    assistant_tool_calls.append({
                        "index": idx,
                        "id": tc.get("id"),
                        "name": (tc.get("function") or {}).get("name")
                    })
            elif role == "tool":
                tool_messages.append({
                    "index": idx,
                    "tool_call_id": msg.get("tool_call_id"),
                    "preview": (msg.get("content") or "")[:160]
                })
        
        return {
            "assistant_tool_calls": assistant_tool_calls,
            "tool_messages": tool_messages
        }

    def _persist_openai_payload(self, trace_id: str):
        """Write the exact OpenAI payload to disk for later debugging."""
        try:
            trace_dir = Path("logs/openai_traces")
            trace_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "trace_id": trace_id,
                "messages": self.message_history
            }
            trace_path = trace_dir / f"{trace_id}.json"
            trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            self._log("TRACE_WARNING", f"Failed to persist OpenAI payload {trace_id}: {e}")

    def _log_openai_trace(self, trace_id: str, tool_state: dict):
        """Log summary of outgoing OpenAI payload with tool-call details."""
        try:
            summary = {
                "trace_id": trace_id,
                "message_count": len(self.message_history),
                "last_roles": [msg.get("role") for msg in self.message_history[-5:]],
                "assistant_tool_calls": tool_state.get("assistant_tool_calls", []),
                "tool_messages": tool_state.get("tool_messages", [])[-5:]
            }
            self._log("OPENAI_REQUEST", json.dumps(summary, ensure_ascii=False))
        except Exception as e:
            self._log("TRACE_WARNING", f"Failed to log OpenAI trace {trace_id}: {e}")

    @staticmethod
    def _normalize_tool_calls(tool_calls: list) -> list[dict]:
        """Normalize tool call payloads into plain dicts with stable IDs."""
        normalized: list[dict] = []
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            name = None
            arguments = "{}"
            if fn is not None:
                name = getattr(fn, "name", None)
                arguments = getattr(fn, "arguments", "{}")
            elif isinstance(tc, dict):
                fn = tc.get("function", {})
                name = fn.get("name")
                arguments = fn.get("arguments", "{}")
            if isinstance(arguments, bytes):
                arguments = arguments.decode("utf-8", errors="ignore")
            if not isinstance(arguments, str):
                try:
                    arguments = json.dumps(arguments)
                except Exception:
                    arguments = str(arguments)
            tc_id = getattr(tc, "id", None) if not isinstance(tc, dict) else tc.get("id")
            if not tc_id:
                tc_id = f"call-{uuid.uuid4().hex}"
            normalized.append({
                "id": tc_id,
                "type": getattr(tc, "type", "function") if not isinstance(tc, dict) else tc.get("type", "function"),
                "function": {
                    "name": name or "",
                    "arguments": arguments
                }
            })
        return normalized
    
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
            out["tool_calls"] = MiniAgent._normalize_tool_calls(tool_calls)
        
        return out
    
    def _trim_history(self):
        """
        Simple history trimming: keep last N messages (plus system), truncate long tool outputs.
        Ensures the most recent assistant message containing tool_calls is always retained so
        subsequent tool observations have a valid tool_call_id anchor.
        """
        if len(self.message_history) <= self.MAX_HISTORY_MESSAGES:
            return
        
        system_msg = self.message_history[0]
        messages = [self._to_dict_message(m) for m in self.message_history[1:]]
        max_other = max(self.MAX_HISTORY_MESSAGES - 1, 0)
        
        if not messages:
            self.message_history = [system_msg]
            return
        
        if len(messages) <= max_other:
            recent = messages
        else:
            start_idx = len(messages) - max_other if max_other > 0 else len(messages)
            
            # Protect the latest assistant tool_call message from being trimmed
            protected_idx = None
            for idx in range(len(messages) - 1, -1, -1):
                msg = messages[idx]
                if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("tool_calls"):
                    protected_idx = idx
                    break
            if protected_idx is not None and protected_idx < start_idx:
                start_idx = protected_idx
            
            recent = messages[start_idx:]
        
        # Drop any tool messages that lost their originating assistant call.
        # OpenAI rejects payloads that contain tool outputs without a preceding assistant/tool_call pair.
        pruned_recent = []
        seen_tool_calls: set[str] = set()
        dropped_orphans = 0
        for msg in recent:
            if not isinstance(msg, dict):
                msg = self._to_dict_message(msg)
            role = msg.get("role")
            if role == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tc_id = tc.get("id")
                    if tc_id:
                        seen_tool_calls.add(tc_id)
                pruned_recent.append(msg)
            elif role == "tool":
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id and tool_call_id in seen_tool_calls:
                    pruned_recent.append(msg)
                else:
                    dropped_orphans += 1
            else:
                pruned_recent.append(msg)
        if dropped_orphans:
            self._log(
                "HISTORY_TRIM_DROP",
                f"Dropped {dropped_orphans} orphan tool messages during trim"
            )
        recent = pruned_recent
        
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
        
        react_loop_count = 0
        react_limit_warning_sent = False
        while step_count < max_steps:
            tool_state = self._sanitize_history_tool_calls()
            trace_id = uuid.uuid4().hex[:8]
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
                self._persist_openai_payload(trace_id)
                self._log_openai_trace(trace_id, tool_state)
                error_info = {
                    "trace_id": trace_id,
                    "error": str(e)
                }
                self._log("OPENAI_ERROR", json.dumps(error_info, ensure_ascii=False))
                _SESSION_STATE.record_error("openai_api", str(e), error_info)
                ui.error(f"API Error: {str(e)} (trace {trace_id})")
                return {"content": None, "error": str(e), "elapsed_time": ui.get_elapsed_time()}
            
            react_parse = self._parse_react_directives(assistant_message.content)
            if react_parse.get("thought"):
                self._log("REACT_THOUGHT", react_parse["thought"])
            final_answer_override = react_parse.get("final_answer")
            
            raw_tool_calls = list(assistant_message.tool_calls or [])
            action_payload = react_parse.get("action")
            if not raw_tool_calls and action_payload:
                tool_name = action_payload.get("tool")
                args_field = action_payload.get("arguments", {})
                if isinstance(args_field, dict) and tool_name:
                    raw_tool_calls = [{
                        "id": f"react-{uuid.uuid4().hex}",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(args_field)
                        }
                    }]
            
            normalized_tool_calls = self._normalize_tool_calls(raw_tool_calls)
            
            if normalized_tool_calls:
                if not assistant_message.content:
                    if react_parse.get("thought"):
                        assistant_message.content = f"Thought: {react_parse['thought']}"
                    else:
                        assistant_message.content = "Action: issuing tool call."
                assistant_entry = self._to_dict_message(assistant_message)
                assistant_entry["tool_calls"] = normalized_tool_calls
                self.message_history.append(assistant_entry)
                
                # Show step indicator for multi-step operations
                if len(normalized_tool_calls) > 1 or step_count > 0:
                    ui.step_indicator(step_count + 1, max_steps, "Processing tools")
                
                executed_actions: list[str] = []
                for tool_call in normalized_tool_calls:
                    tool_name = (tool_call.get("function") or {}).get("name")
                    tool_call_id = tool_call.get("id")
                    if not tool_call_id:
                        self._log("TOOL_CALL_ERROR", f"Skipping tool call without id: {tool_call}")
                        continue
                    
                    # Guard against unknown tools
                    tool = TOOLS.get(tool_name)
                    if not tool:
                        tool_message = {
                            "role": "tool",
                            "content": f"Error: Unknown tool '{tool_name}'",
                            "tool_call_id": tool_call_id
                        }
                        self.message_history.append(tool_message)
                        continue
                    
                    # Guard against malformed JSON arguments
                    try:
                        args = json.loads((tool_call.get("function") or {}).get("arguments") or "{}")
                    except Exception as e:
                        tool_message = {
                            "role": "tool",
                            "content": f"Error: Invalid tool arguments JSON: {e}",
                            "tool_call_id": tool_call_id
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
                    
                    observation_content = self._format_observation_content(
                        tool_name=tool_name,
                        result=result_str,
                        success=success,
                        exit_code=exit_code,
                        error_msg=error_msg
                    )
                    
                    tool_message = {
                        "role": "tool",
                        "content": observation_content,
                        "tool_call_id": tool_call_id
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

                    executed_actions.append(self._summarize_action(tool_name, args))

                self._append_plan_reminder(
                    react_parse.get("thought"),
                    executed_actions
                )
            else:
                if final_answer_override:
                    assistant_message.content = final_answer_override
                self.message_history.append(self._to_dict_message(assistant_message))
                break
            
            react_loop_count += 1
            if (
                not react_limit_warning_sent
                and react_loop_count >= self.MAX_REACT_LOOPS
            ):
                limiter_message = {
                    "role": "system",
                    "content": (
                        "ReAct loop limit reached. Provide a Final Answer summarizing results "
                        "without requesting further tool calls."
                    )
                }
                self.message_history.append(limiter_message)
                react_limit_warning_sent = True
            
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
