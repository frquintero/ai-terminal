#!/usr/bin/env python3
"""
AI-Powered Linux Shell Terminal

A CLI interface that uses AI to interpret natural language commands and execute shell operations.
"""

import sys
from agent import MiniAgent
from shell_integration import ShellIntegration

def main():
    print("🤖 AI-Powered Linux Shell Terminal")
    print("Type 'exit', 'quit', or press Ctrl+C to exit.")
    print("-" * 50)

    # Initialize components
    try:
        agent = MiniAgent()
        shell = ShellIntegration()  # For cleanup, though agent manages its own
    except Exception as e:
        print(f"Error initializing: {e}")
        sys.exit(1)

    # Main REPL loop
    try:
        while True:
            try:
                user_input = input("❯ ").strip()
                if not user_input:
                    continue

                # Check for exit commands
                if user_input.lower() in ['exit', 'quit', 'q']:
                    print("Goodbye! 👋")
                    break

                # Process input through AI agent
                response = agent.process_input(user_input)

                # Display response
                if response:
                    print(response)
                print()  # Empty line for readability

            except KeyboardInterrupt:
                print("\nGoodbye! 👋")
                break
            except EOFError:
                print("\nGoodbye! 👋")
                break
            except Exception as e:
                print(f"Error processing input: {e}")
                print("Please try again.\n")

    finally:
        # Cleanup
        try:
            shell.close()
        except:
            pass

if __name__ == "__main__":
    main()
