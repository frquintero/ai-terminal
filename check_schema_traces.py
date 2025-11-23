import sqlite3

db_path = "logs/orchestrator.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- Schema: llm_traces ---")
    cursor.execute("PRAGMA table_info(llm_traces)")
    for col in cursor.fetchall():
        print(col)
        
    print("\n--- Schema: chat_history ---")
    cursor.execute("PRAGMA table_info(chat_history)")
    for col in cursor.fetchall():
        print(col)

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
