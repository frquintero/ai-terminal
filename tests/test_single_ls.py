"""Quick test for single ls command"""
from agent import MiniAgent

agent = MiniAgent()
result = agent.process_input("ls")
print("\n\n=== FINAL RESULT ===")
print(f"Steps: {result.get('steps', 0)}")
print(f"Content: {result.get('content', 'None')}")
