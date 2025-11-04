#!/usr/bin/env python3
"""
AI-Powered Linux Shell Terminal

A CLI interface that uses AI to interpret natural language commands and execute shell operations.
"""

import sys
import os
import subprocess

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
VERSION = "1.01"

def _print_help():
    help_text = f"""
ai-terminal {VERSION}

Usage:
  python main.py [--help] [--about] [--version]

Flags:
  -h, --help     Show this help message and exit
  --about        Show a short about message and exit
  --version      Print version and exit

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

def handle_cli_flags():
    # Inspect only top-level flags; if any known flag is present print and exit
    args = sys.argv[1:]
    if not args:
        return
    for a in args:
        if a in ("-h", "--help"):
            _print_help(); sys.exit(0)
        if a == "--about":
            _print_about(); sys.exit(0)
        if a == "--version":
            print(VERSION); sys.exit(0)

# Allow quick inspection of help/about/version without activating venv
handle_cli_flags()

# Ensure we're running in venv before importing dependencies
ensure_venv()

from agent import MiniAgent
from ui_formatter import ui, console
from rich.prompt import Prompt
import getpass
from tools import WORKING_DIR_PREFIX

def main():
    # Print banner
    ui.print_banner()
    
    # Ensure working directory exists
    try:
        os.makedirs(WORKING_DIR_PREFIX, exist_ok=True)
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
                
                # Handle user input requests (e.g., sudo password)
                if "request" in result and result["request"]:
                    req = result["request"]
                    if req.get("secret"):
                        # Use getpass for hidden input
                        value = getpass.getpass(req["prompt"] + ": ")
                    else:
                        # Regular visible input
                        value = input(req["prompt"] + ": ").strip()
                    
                    # Resume agent with provided secret
                    result = agent.provide_secret(req["id"], value)

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
