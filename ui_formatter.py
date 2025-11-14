"""
UI Formatting utilities for the AI-Powered Terminal

Provides color schemes, formatting, and visual feedback for enhanced user experience.
"""

import json
import os
import time
from pathlib import Path
from textwrap import shorten
from typing import Any, Dict, Optional, Tuple

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax
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
    
    def ai_response(self, message: str, elapsed_time: Optional[float] = None, cycle_id: Optional[str] = None):
        """Display AI response in a formatted panel"""
        # Render markdown if message contains markdown syntax
        if any(marker in message for marker in ['```', '**', '#', '-', '*', '`']):
            content = Markdown(message)
        else:
            content = message
        
        # Add timing info if available
        title = "🤖 AI Assistant"
        if elapsed_time:
            title += f" ({elapsed_time:.2f}s)"
        
        # Add cycle ID as subtitle (bottom right of panel) if available
        subtitle = None
        if cycle_id:
            short_id = cycle_id[:8] if len(cycle_id) > 8 else cycle_id
            subtitle = f"Cycle: {short_id}"
        
        panel = Panel(
            content,
            title=title,
            subtitle=subtitle,
            subtitle_align="right",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2)
        )
        console.print(panel)
    
    def command_output(self, output: str, command: str = "", elapsed_time: Optional[float] = None):
        """Display command output in a formatted panel"""
        title = "📟 Output"
        if command:
            title = f"📟 Output: {command}"
        if elapsed_time:
            title += f" ({elapsed_time:.2f}s)"
        
        panel = Panel(
            output.strip() if output else "[No output]",
            title=title,
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2)
        )
        console.print(panel)
    
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
        elif event_type == "tool_output":
            self._render_tool_output(payload)

    def _render_tool_output(self, payload: dict) -> None:
        """Render tool output as ANSI-styled panels."""
        tool_name = payload.get("tool_name")
        if not tool_name:
            return

        command = payload.get("command")
        if not command:
            tool_args = payload.get("tool_args") or {}
            command = tool_args.get("command") or tool_args.get("file_path")

        stdout = payload.get("stdout") or ""
        stderr = payload.get("stderr") or ""
        raw_stdout = payload.get("raw_stdout") or stdout
        raw_stderr = payload.get("raw_stderr") or stderr

        if not any((command, stdout.strip(), stderr.strip(), raw_stdout.strip(), raw_stderr.strip())):
            return
        total_steps = payload.get("total_steps")
        step_id = payload.get("step_id")
        subtitle = None
        if total_steps and step_id is not None:
            subtitle = f"Step {step_id + 1}/{total_steps}"
        description = payload.get("description")
        self.render_command_panel(
            tool_name=tool_name,
            command=command,
            stdout=stdout,
            raw_stdout=raw_stdout,
            stderr=stderr,
            raw_stderr=raw_stderr,
            success=payload.get("success", False),
            subtitle=subtitle,
            description=description,
            tool_args=payload.get("tool_args") or {}
        )

    def render_command_panel(
        self,
        *,
        tool_name: Optional[str],
        command: Optional[str],
        stdout: Optional[str],
        raw_stdout: Optional[str],
        stderr: Optional[str],
        raw_stderr: Optional[str],
        success: bool,
        subtitle: Optional[str] = None,
        description: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None
    ) -> None:
        """Render a dedicated panel for tool output."""
        display_command = command or description or (tool_name or "Tool output")
        title = f"🛠 {shorten(str(display_command).strip(), width=80, placeholder='…')}"
        panel_style = "green" if success else "red"

        sections = []
        if description and description.strip() and description.strip() not in display_command:
            meta = Text(description.strip(), style="dim")
            sections.append(meta)

        stdout_section = self._build_stdout_section(
            tool_name=tool_name,
            tool_args=tool_args or {},
            stdout=stdout,
            raw_stdout=raw_stdout
        )
        if stdout_section:
            sections.append(stdout_section)

        stderr_section = self._build_stderr_section(stderr=stderr, raw_stderr=raw_stderr)
        if stderr_section:
            sections.append(stderr_section)

        if not sections:
            sections.append(Text("[No output]", style="dim"))

        body = Group(*sections) if len(sections) > 1 else sections[0]
        panel = Panel(
            body,
            title=title,
            subtitle=subtitle,
            subtitle_align="right",
            border_style=panel_style,
            box=box.SQUARE,
            padding=(1, 2)
        )
        console.print(panel)

    def _build_stdout_section(
        self,
        *,
        tool_name: Optional[str],
        tool_args: Dict[str, Any],
        stdout: Optional[str],
        raw_stdout: Optional[str]
    ) -> Optional[Group]:
        text = raw_stdout if raw_stdout not in (None, "") else stdout
        if not text or not text.strip():
            return None
        specialized = self._build_specialized_stdout_renderable(
            tool_name=tool_name,
            tool_args=tool_args,
            text=text
        )
        label = Text("stdout:\n", style="bold green")
        if specialized:
            return Group(label, specialized)
        fallback = Text.from_ansi(text.rstrip())
        return Group(label, fallback)

    def _build_specialized_stdout_renderable(
        self,
        *,
        tool_name: Optional[str],
        tool_args: Dict[str, Any],
        text: str
    ) -> Optional[Any]:
        if tool_name == "read_file":
            return self._render_file_preview(
                file_path=tool_args.get("file_path"),
                text=text
            )
        pretty_json = try_pretty_json(text)
        if pretty_json:
            return Syntax(pretty_json, "json", theme="monokai", word_wrap=True)
        return None

    def _render_file_preview(self, *, file_path: Optional[str], text: str) -> Optional[Any]:
        preview, truncated = truncate_text(text)
        if not preview:
            return None
        if is_markdown_file(file_path):
            rendered = Markdown(preview)
        else:
            language = infer_language_from_path(file_path)
            if language == "markdown":
                rendered = Markdown(preview)
            elif language:
                rendered = Syntax(preview, language, theme="monokai", word_wrap=False)
            else:
                rendered = Text.from_ansi(preview)
        if truncated:
            notice = Text("[truncated preview]", style="dim")
            return Group(rendered, notice)
        return rendered

    def _build_stderr_section(
        self,
        *,
        stderr: Optional[str],
        raw_stderr: Optional[str]
    ) -> Optional[Group]:
        text = raw_stderr if raw_stderr not in (None, "") else stderr
        if not text or not text.strip():
            return None
        label = Text("stderr:\n", style="bold red")
        body = Text.from_ansi(text.rstrip())
        return Group(label, body)

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
