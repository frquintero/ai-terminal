#!/usr/bin/env python3
"""
AI-Powered Linux Shell Terminal

A CLI interface that uses AI to interpret natural language commands and execute shell operations.
"""

import sys
import os
import subprocess
import argparse

# Check if running in virtual environment, if not, restart with venv
def ensure_venv():
    venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv')
    venv_python = os.path.join(venv_path, 'bin', 'python3')
    
    # Check if we're already in a venv or if venv python doesn't exist
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        # Already in a virtual environment
        return
    
    # Check if venv exists
    if os.path.exists(venv_python):
        # Restart with venv python
        os.execv(venv_python, [venv_python] + sys.argv)
    else:
        print(f"Warning: Virtual environment not found at {venv_path}")
        print("Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt")
        sys.exit(1)

# Metadata / CLI
VERSION = "1.2"

def _print_help():
    help_text = f"""
ai-terminal {VERSION}

Usage:
  python main.py [OPTIONS]

Options:
  -h, --help              Show this help message and exit
  --about                 Show a short about message and exit
  --version               Print version and exit

Runtime Configuration Overrides:
  --agent {{minimax,kimi2,custom}}
                          Override agent backend (default from .env)
  --max-tokens N          Override max tokens per response
  --temperature T         Override temperature (0.0-2.0)
  --max-steps N           Override max tool calling steps

Configuration Priority:
  CLI flags > Environment variables > .env file > Defaults

Examples:
  python main.py                                # Use .env config
  python main.py --agent kimi2                  # Switch to Kimi K2 temporarily
  python main.py --temperature 0.9 --max-tokens 2048
  AGENT_TYPE=kimi2 python main.py               # Environment variable override

When run without flags the program starts the interactive AI-powered shell.
"""
    print(help_text)

def _print_about():
    about = (
        "AI-Powered Linux Shell Terminal\n"
        "Combines an AI agent with shell integration to interpret natural language and run commands.\n"
        f"Version: {VERSION}\n"
    )
    print(about)

def parse_cli_args():
    """Parse command-line arguments for runtime configuration overrides"""
    parser = argparse.ArgumentParser(
        prog='ai-terminal',
        description='AI-Powered Linux Shell Terminal',
        add_help=False  # We handle --help manually
    )
    
    # Meta flags (handled separately for early exit)
    parser.add_argument('-h', '--help', action='store_true', help='Show this help message and exit')
    parser.add_argument('--about', action='store_true', help='Show about message and exit')
    parser.add_argument('--version', action='store_true', help='Print version and exit')
    
    # Runtime configuration overrides
    parser.add_argument('--agent', type=str, choices=['minimax', 'kimi2', 'custom'], 
                        help='Override agent backend (minimax, kimi2, custom)')
    parser.add_argument('--max-tokens', type=int, metavar='N',
                        help='Override max tokens per response')
    parser.add_argument('--temperature', type=float, metavar='T',
                        help='Override temperature (0.0-2.0)')
    parser.add_argument('--max-steps', type=int, metavar='N',
                        help='Override max tool calling steps')
    
    return parser.parse_args()

def handle_cli_flags(args):
    """Handle meta flags that exit immediately"""
    if args.help:
        _print_help()
        sys.exit(0)
    if args.about:
        _print_about()
        sys.exit(0)
    if args.version:
        print(VERSION)
        sys.exit(0)

# Parse CLI args early (before venv check to allow --help without venv)
cli_args = parse_cli_args()

# Allow quick inspection of help/about/version without activating venv
handle_cli_flags(cli_args)

# Ensure we're running in venv before importing dependencies
ensure_venv()

from agent import MiniAgent
from ui_formatter import ui, console
from rich.prompt import Prompt
from tools import WORKING_DIR_PREFIX

def apply_cli_overrides(args):
    """Apply CLI argument overrides to environment variables (takes precedence)"""
    if args.agent:
        os.environ['AGENT_TYPE'] = args.agent
    if args.max_tokens is not None:
        os.environ['MAX_TOKENS'] = str(args.max_tokens)
    if args.temperature is not None:
        os.environ['TEMPERATURE'] = str(args.temperature)
    if args.max_steps is not None:
        os.environ['MAX_STEPS'] = str(args.max_steps)

def main():
    # Apply CLI overrides before config loading
    apply_cli_overrides(cli_args)
    
    # Print banner
    ui.print_banner()
    
    # Ensure working directory exists (relative to app directory)
    try:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        working_dir_path = os.path.join(app_dir, WORKING_DIR_PREFIX)
        os.makedirs(working_dir_path, exist_ok=True)
    except Exception as e:
        ui.error(f"Failed to create working directory '{WORKING_DIR_PREFIX}': {e}")
        sys.exit(1)

    # Initialize components
    try:
        agent = MiniAgent()
        
        # Link AI shell to UI for dynamic prompt
        from tools import TOOLS, RunCommandTool
        run_command = TOOLS.get("run_command")
        # Narrow the type for Pylance by checking the concrete class
        if isinstance(run_command, RunCommandTool) and hasattr(run_command, "shell"):
            ui.set_ai_shell(run_command.shell)
    except Exception as e:
        ui.error(f"Error initializing: {e}")
        sys.exit(1)

    # Main REPL loop
    try:
        while True:
            try:
                # Display dynamic prompt and get input
                ui.print_prompt()
                user_input = input().strip()
                
                if not user_input:
                    continue

                # Check for exit commands
                if user_input.lower() in ['exit', 'quit', 'q']:
                    ui.print_goodbye()
                    break

                # Process input through AI agent
                result = agent.process_input(user_input)

                # Display response
                if result["error"]:
                    # Error was already displayed by agent
                    pass
                elif result["content"]:
                    ui.ai_response(result["content"], result.get("elapsed_time"))
                
                console.print()  # Empty line for readability

            except KeyboardInterrupt:
                ui.print_goodbye()
                break
            except EOFError:
                ui.print_goodbye()
                break
            except Exception as e:
                ui.error(f"Error processing input: {e}")
                console.print("[dim]Please try again.[/dim]\n")

    finally:
        # Cleanup - close the persistent shell in RunCommandTool
        try:
            from tools import TOOLS, RunCommandTool
            run_command = TOOLS.get("run_command")
            if isinstance(run_command, RunCommandTool) and hasattr(run_command, "shell"):
                # mypy/pylance-friendly check before accessing dynamic attribute
                run_command.shell.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
