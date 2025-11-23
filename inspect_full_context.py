import sqlite3
import json

db_path = "logs/orchestrator.db"
cycle_id_prefix = "782a5280"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Get session_id for this cycle
    # We can look up the cycle in cycle_metrics or cycle_failures or interactions to find a session_id link 
    # effectively, usually we have to look at where cycle was created. 
    # But 'interactions' table usually doesn't have session_id column directly in v2 schema seen earlier (it had cycle_id).
    # Let's look at 'sessions' or just assume we can find it via the cycle.
    
    # Actually, let's find the session_id from the chat_history if this cycle produced one? 
    # Or query cycle_metrics if it has it?
    # Let's try to find the session_id by looking at chat_history entries *around* this time or just list all recent chat history.
    
    # Let's look at llm_traces first, it might contain the full prompt.
    print(f"--- Checking LLM Traces for {cycle_id_prefix} ---")
    cursor.execute("SELECT messages_json FROM llm_traces WHERE cycle_id LIKE ? AND role = 'A'", (f"{cycle_id_prefix}%",))
    row = cursor.fetchone()
    if row:
        try:
            messages = json.loads(row[0])
            # The last message is usually the user message with the context
            last_msg = messages[-1]
            print("Full Content of Last Message:")
            print(last_msg['content'])
        except Exception as e:
            print(f"Error parsing LLM trace: {e}")
    else:
        print("No LLM trace found.")
        
    # 2. Let's check the actual chat history count for the session
    # First we need the session ID. Let's get it from chat_history where cycle_id matches, if it exists there.
    cursor.execute("SELECT session_id FROM chat_history WHERE cycle_id LIKE ?", (f"{cycle_id_prefix}%",))
    row = cursor.fetchone()
    if row:
        session_id = row[0]
        print(f"\nSession ID: {session_id}")
        
        print("\n--- Full Chat History for Session ---")
        cursor.execute("SELECT cycle_id, user_query, agent_response, timestamp FROM chat_history WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
        rows = cursor.fetchall()
        for idx, r in enumerate(rows, 1):
            print(f"{idx}. Cycle {r[0]} ({r[3]}): {r[1]}")
    else:
        # Maybe this cycle didn't produce a chat history entry (failed?). 
        # Let's try to find session_id from 'interactions' joined with something? 
        # Or just list all chat history and see which ones look like the ones in the prompt we saw earlier.
        print("\nCould not find session_id directly from chat_history for this cycle.")
        print("Listing recent chat history to match the preview seen earlier...")
        
        cursor.execute("SELECT session_id, cycle_id, user_query, timestamp FROM chat_history ORDER BY timestamp DESC LIMIT 20")
        rows = cursor.fetchall()
        for r in rows:
            print(f"Session {r[0]} | Cycle {r[1]} | {r[3]} | {r[2]}")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
