"""
UI Formatting utilities for the AI-Powered Terminal

Provides color schemes, formatting, and visual feedback for enhanced user experience.
"""

import os
import time
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich import box

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

class UIFormatter:
    """Handles all UI formatting and display logic"""
    
    def __init__(self):
        self.start_time = None
        
    def get_prompt(self) -> str:
        """Generate dynamic prompt with user@host and current directory"""
        username = os.getenv('USER', 'user')
        hostname = os.uname().nodename
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
    
    def ai_response(self, message: str, elapsed_time: Optional[float] = None):
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
        
        panel = Panel(
            content,
            title=title,
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

# Global formatter instance
ui = UIFormatter()
