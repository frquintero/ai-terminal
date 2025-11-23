import sqlite3
import json

db_path = "logs/orchestrator.db"
cycle_id_prefix = "782a5280"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"--- Checking LLM Traces for {cycle_id_prefix} ---")
    cursor.execute("SELECT full_prompt FROM llm_traces WHERE cycle_id LIKE ? AND role = 'A'", (f"{cycle_id_prefix}%",))
    row = cursor.fetchone()
    if row:
        prompt_json = row[0]
        try:
            # The full_prompt is stored as a JSON list of messages
            messages = json.loads(prompt_json)
            # The user message is the last one
            last_msg = messages[-1]
            print(last_msg['content'])
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            print(prompt_json)
    else:
        print("No trace found.")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
