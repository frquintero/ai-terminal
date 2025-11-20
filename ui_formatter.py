"""
UI Formatting utilities for the AI-Powered Terminal

Provides color schemes, formatting, and visual feedback for enhanced user experience.
"""

import json
import os
import time
from pathlib import Path
from textwrap import shorten
from typing import Any, Dict, List, Optional, Set, Tuple

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

# Initialize Rich console
console = Console()

# Tool icons mapping
TOOL_ICONS = {
    'run_command': '🔧',
    'run_interactive': '🖥️',
    'read_file': '📄',
    'write_file': '✍️',
    'chat': '💬',
    'process_content': '🔄'
}

JSON_MAX_CHARS = 20000
MAX_PREVIEW_CHARS = 8000
MAX_PREVIEW_LINES = 400
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
CODE_SYNTAX_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".md": "markdown",
    ".sql": "sql",
    ".txt": None,
}


def try_pretty_json(text: Optional[str], max_chars: int = JSON_MAX_CHARS) -> Optional[str]:
    """Return prettified JSON if text is a reasonably sized JSON payload."""
    if not text:
        return None
    candidate = text.strip()
    if len(candidate) > max_chars:
        return None
    if not candidate or candidate[0] not in ("{", "["):
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, (dict, list)):
        return None
    return json.dumps(parsed, indent=2, ensure_ascii=False)


def truncate_text(text: str, max_chars: int = MAX_PREVIEW_CHARS, max_lines: int = MAX_PREVIEW_LINES) -> Tuple[str, bool]:
    """
    Truncate text to the requested char/line limits.

    Returns (truncated_text, was_truncated).
    """
    if not text:
        return "", False
    lines = text.splitlines()
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars]
        truncated = True
    return result, truncated


def infer_language_from_path(path: Optional[str]) -> Optional[str]:
    """Map filename extension to a Syntax language if we know it."""
    if not path:
        return None
    suffix = Path(path).suffix.lower()
    return CODE_SYNTAX_MAP.get(suffix)


def is_markdown_file(path: Optional[str]) -> bool:
    """Return True if the file extension is Markdown."""
    if not path:
        return False
    return Path(path).suffix.lower() in MARKDOWN_EXTENSIONS

class UIFormatter:
    """Handles all UI formatting and display logic"""
    
    def __init__(self):
        self.start_time = None
        self.ai_shell = None  # Reference to AI shell for tracking its cwd
        self.status_line = StatusLineManager(console)
        self._cycle_active = False
        
    def set_ai_shell(self, shell):
        """Set reference to AI shell for dynamic prompt tracking"""
        self.ai_shell = shell
        
    def get_prompt(self) -> str:
        """Generate dynamic prompt with user@host and AI shell's current directory"""
        username = os.getenv('USER', 'user')
        hostname = os.uname().nodename
        
        # Use AI shell's current directory if available, otherwise fall back to app's cwd
        if self.ai_shell:
            cwd = self.ai_shell.get_current_dir()
        else:
            cwd = os.getcwd()
        
        # Replace home directory with ~
        home = os.path.expanduser('~')
        if cwd.startswith(home):
            cwd = cwd.replace(home, '~', 1)
        
        # Create colored prompt
        prompt_text = Text()
        prompt_text.append(f"{username}@{hostname}", style="bold cyan")
        prompt_text.append("  ", style="white")
        prompt_text.append(cwd, style="bold blue")
        prompt_text.append(" ❯ ", style="bold green")
        
        return prompt_text
    
    def print_prompt(self):
        """Print the dynamic prompt"""
        console.print(self.get_prompt(), end="")
    
    def show_thinking(self, message: str = "Thinking..."):
        """Show AI thinking indicator with spinner"""
        return Spinner("dots", text=f"💭 {message}", style="cyan")
    
    def show_tool_execution(self, tool_name: str, details: str = "") -> Spinner:
        """Show tool execution indicator"""
        icon = TOOL_ICONS.get(tool_name, '⚙️')
        display_name = tool_name.replace('_', ' ').title()
        text = f"{icon} {display_name}"
        if details:
            text += f": {details}"
        return Spinner("dots", text=text, style="yellow")
    
    def success(self, message: str):
        """Print success message in green"""
        console.print(f"✓ {message}", style="bold green")
    
    def error(self, message: str):
        """Print error message in red"""
        console.print(f"✗ {message}", style="bold red")
    
    def warning(self, message: str):
        """Print warning message in yellow"""
        console.print(f"⚠ {message}", style="bold yellow")
    
    def info(self, message: str):
        """Print info message in blue"""
        console.print(f"ℹ {message}", style="bold blue")
    
    def _create_markdown(self, content: str) -> Markdown:
        """Create a Markdown object with consistent styling."""
        # Use monokai theme to ensure code blocks have a dark background
        # which prevents "scattered letters" on matching backgrounds.
        return Markdown(content, code_theme="monokai")

    def render_cycle(
        self,
        *,
        query: str,
        result: Any,
        elapsed_time: Optional[float] = None
    ) -> None:
        """Render the complete cycle (user query + narration + structured blocks)."""
        agent_response = getattr(result, "agent_response", "")
        segments = getattr(result, "response_segments", None) or [
            {"type": "text", "content": agent_response}
        ]
        execution_result = getattr(result, "execution_result", None) or {}

        renderables: List[Any] = []
        if query:
            renderables.append(Text("User Query:", style="bold cyan"))
            renderables.append(Text(query))
            renderables.append(Text(""))

        narration_renderable = self._render_narration_with_segments(
            segments=segments,
            execution_result=execution_result
        )
        if narration_renderable:
            renderables.append(Text("AI Response:", style="bold magenta"))
            renderables.append(Text(""))
            renderables.append(narration_renderable)
        elif agent_response:
            renderables.append(self._create_markdown(agent_response))

        content: Any = ""
        if renderables:
            content = Group(*renderables)

        title = "🤖 AI Assistant"
        if elapsed_time:
            title += f" ({elapsed_time:.2f}s)"

        cycle_id = getattr(result, "cycle_id", None)
        subtitle = None
        if cycle_id:
            short_id = cycle_id[:8] if len(cycle_id) > 8 else cycle_id
            subtitle = f"Cycle ID: {short_id}"

        panel = Panel(
            content,
            title=title,
            subtitle=subtitle,
            subtitle_align="right",
            border_style="red" if getattr(result, "error", None) else "cyan",
            box=box.ROUNDED,
            padding=(1, 2)
        )
        console.print(panel)

    def _render_narration_with_segments(
        self,
        *,
        segments: List[Dict[str, Any]],
        execution_result: Dict[str, Any]
    ) -> Optional[Any]:
        if not segments:
            return None

        renderables: List[Any] = []
        current_text_buffer: str = ""

        for segment in segments:
            kind = segment.get("kind") or segment.get("type")
            if kind in {"text", "inline_value"}:
                text_value = (
                    segment.get("text")
                    or segment.get("content")
                    or segment.get("value")
                    or ""
                )
                current_text_buffer += str(text_value)
            elif kind == "block":
                if current_text_buffer:
                    renderables.append(self._create_markdown(current_text_buffer))
                    current_text_buffer = ""
                fence = segment.get("fence") or segment.get("tag") or "output"
                body = segment.get("body") or segment.get("content") or ""
                title = segment.get("title")
                truncated_note = segment.get("truncated")
                if title:
                    renderables.append(Text(str(title), style="bold"))
                renderables.append(
                    self._create_markdown(
                        f"```{fence}\n{body}\n```"
                    )
                )
                if truncated_note:
                    renderables.append(Text(str(truncated_note), style="dim"))

        if current_text_buffer:
            renderables.append(self._create_markdown(current_text_buffer))

        if not renderables:
            return None
        return Group(*renderables)

    def _render_output_placeholder(
        self,
        *,
        key: Optional[str],
        execution_result: Dict[str, Any],
        rendered_blocks: Set[str]
    ) -> Tuple[Optional[str], List[Any]]:
        if not key:
            return "", []

        output_values = execution_result.get("output_values") or {}
        value_sources = execution_result.get("output_value_sources") or {}
        value_types = execution_result.get("output_value_types") or {}

        fmt = (value_types.get(key) or "").strip().lower()
        source = value_sources.get(key) or {}
        no_output_flag = bool(source.get("no_output"))
        value = output_values.get(key)
        value_text = str(value) if value is not None else None
        payload_text = self._select_payload_text(source, value_text)
        is_multiline_str = (
            fmt in {"str", ""}
            and payload_text is not None
            and "\n" in payload_text.rstrip("\n")
        )

        inline_value: Optional[str] = None
        if no_output_flag:
            inline_value = value_text if value_text is not None else ""
        elif fmt in {"int", "float"}:
            if value_text is not None:
                inline_value = value_text
        elif fmt in {"str", ""}:
            if not is_multiline_str and value_text is not None:
                inline_value = value_text
        elif value is None and key not in value_sources:
            inline_value = f"[missing:{key}]"

        block_renderables: List[Any] = []
        if key not in rendered_blocks and not no_output_flag:
            block_fmt = "raw" if is_multiline_str else fmt
            block_tag, block_payload = self._resolve_block_payload(
                fmt=block_fmt,
                output_value=value_text,
                source=source
            )
            if block_tag and block_payload:
                block_renderables.append(
                    self._build_fenced_block(block_tag, block_payload)
                )

            if block_renderables:
                rendered_blocks.add(key)

        return inline_value, block_renderables

    def _resolve_block_payload(
        self,
        *,
        fmt: str,
        output_value: Optional[str],
        source: Optional[Dict[str, Any]]
    ) -> Tuple[Optional[str], Optional[str]]:
        if fmt not in {"list", "raw", "table", "json"}:
            return None, None

        payload_source = self._select_payload_text(source, output_value)

        if payload_source is None:
            return None, None

        payload_text = str(payload_source)

        if fmt == "json":
            pretty = try_pretty_json(payload_text)
            candidate = pretty or payload_text
            trimmed, truncated = truncate_text(
                candidate,
                max_chars=JSON_MAX_CHARS,
                max_lines=MAX_PREVIEW_LINES
            )
            if truncated:
                trimmed = trimmed.rstrip() + "\n[output truncated]"
            return "json", trimmed

        block_tag = "output"
        if source and source.get("tool_name") == "read_file":
            tool_args = source.get("tool_args") or {}
            file_path = tool_args.get("file_path")
            language = infer_language_from_path(file_path)
            if language == "markdown":
                block_tag = "md"
            elif language:
                block_tag = language

        trimmed, truncated = truncate_text(payload_text)
        if truncated:
            trimmed = trimmed.rstrip() + "\n[output truncated]"
        return block_tag, trimmed

    def _select_payload_text(
        self,
        source: Optional[Dict[str, Any]],
        output_value: Optional[str]
    ) -> Optional[str]:
        """Pick the best available stdout text for rendering."""
        if source:
            raw_stdout = source.get("raw_stdout")
            if raw_stdout not in (None, ""):
                return str(raw_stdout)
            stdout = source.get("stdout")
            if stdout not in (None, ""):
                return str(stdout)
        return output_value

    def _build_fenced_block(self, tag: str, content: str) -> Markdown:
        normalized_tag = tag or "output"
        normalized_content = content.rstrip() if content else ""
        md_content = f"```{normalized_tag}\n{normalized_content}\n```"
        return self._create_markdown(md_content)
    
    def step_indicator(self, current: int, total: int, description: str = ""):
        """Display step progress indicator"""
        text = f"Step {current}/{total}"
        if description:
            text += f": {description}"
        console.print(f"  {text}", style="dim cyan")
    
    def start_timer(self):
        """Start timing an operation"""
        self.start_time = time.time()
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time since start_timer was called"""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time
    
    def clear_line(self):
        """Clear the current line"""
        console.print("\r" + " " * 100 + "\r", end="")
    
    def print_banner(self):
        """Print the application banner"""
        banner = """
[bold cyan]🤖 AI-Powered Linux Shell Terminal[/bold cyan]
[dim]Type your commands or questions naturally. Type 'exit' or 'quit' to exit.[/dim]
"""
        console.print(Panel(banner.strip(), border_style="cyan", box=box.DOUBLE))
        console.print()
    
    def print_goodbye(self):
        """Print goodbye message"""
        console.print("\n[bold cyan]Goodbye! 👋[/bold cyan]\n")
    
    def token_usage(self, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        """Display token usage statistics (optional)"""
        usage_text = f"📊 Tokens: {total_tokens} (prompt: {prompt_tokens}, completion: {completion_tokens})"
        console.print(usage_text, style="dim")

    def begin_cycle(self):
        """Mark the start of an orchestration cycle."""
        self._cycle_active = True
        self.status_line.begin()

    def end_cycle(self):
        """Clear status line at the end of a cycle."""
        self.status_line.finish()
        self._cycle_active = False

    def handle_orchestrator_event(self, event_type: str, payload: Optional[dict] = None):
        """Render orchestration events (status + tool output panels)."""
        if not self._cycle_active:
            return
        payload = payload or {}
        if event_type == "status":
            self.status_line.update(payload.get("phase"), payload)

    def update_status_line(self, phase: str, payload: Optional[dict] = None) -> None:
        """Compatibility shim if status updates are triggered externally."""
        self.status_line.update(phase, payload or {})


class StatusLineManager:
    """Single-line status indicator that updates in place."""

    PHASE_LABELS = {
        "planning": "Planning",
        "executing": "Executing commands",
        "preparing_response": "Preparing response"
    }

    def __init__(self, console: Console):
        self.console = console
        self._live: Optional[Live] = None
        self._current_phase: Optional[str] = None
        self._phase_start: Optional[float] = None
        self._active = False

    def begin(self) -> None:
        if self._active:
            return
        self._active = True
        self._current_phase = None
        self._phase_start = time.time()
        if not self._live:
            self._live = Live(
                "",
                console=self.console,
                refresh_per_second=6,
                transient=True
            )
            self._live.start()

    def finish(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None
        self._active = False
        self._current_phase = None
        self._phase_start = None

    def update(self, phase: Optional[str], payload: Optional[dict] = None) -> None:
        if not self._active or not phase:
            return
        payload = payload or {}
        if not self._live:
            self.begin()
        if phase != self._current_phase:
            self._current_phase = phase
            self._phase_start = time.time()
        elapsed = 0.0
        if self._phase_start:
            elapsed = max(0.0, time.time() - self._phase_start)
        label = self.PHASE_LABELS.get(phase, phase.replace("_", " ").title())
        text = Text()
        text.append(label, style="bold cyan")
        detail = self._format_detail(payload)
        if detail:
            text.append(f"  {detail}", style="white")
        text.append(f"  [{elapsed:.1f}s]", style="dim")
        if self._live:
            self._live.update(text)

    def _format_detail(self, payload: dict) -> str:
        parts = []
        step = payload.get("step")
        total = payload.get("total_steps")
        if step and total:
            parts.append(f"Step {int(step)}/{int(total)}")
        command = payload.get("command")
        if command:
            compact = shorten(str(command).strip().replace("\n", " "), width=60, placeholder="…")
            parts.append(f"`{compact}`")
        description = payload.get("description")
        if description and not command:
            parts.append(shorten(description.strip(), width=60, placeholder="…"))
        return "  |  ".join(parts)

# Global formatter instance
ui = UIFormatter()
