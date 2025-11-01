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

# Ensure we're running in venv before importing dependencies
ensure_venv()

from agent import MiniAgent
from ui_formatter import ui, console
from rich.prompt import Prompt

def main():
    # Print banner
    ui.print_banner()

    # Initialize components
    try:
        agent = MiniAgent()
        
        # Link AI shell to UI for dynamic prompt
        from tools import TOOLS
        run_command = TOOLS.get("run_command")
        if run_command and hasattr(run_command, "shell"):
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
            from tools import TOOLS
            run_command = TOOLS.get("run_command")
            if run_command and hasattr(run_command, "shell"):
                run_command.shell.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
