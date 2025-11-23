import sqlite3

db_path = "logs/orchestrator.db"
cycle_id_lookup = "0636cf57-a4bc-44d4-974b-21a3e6001aff"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get session_id
    cursor.execute("SELECT session_id FROM chat_history WHERE cycle_id = ?", (cycle_id_lookup,))
    row = cursor.fetchone()
    
    if row:
        session_id = row[0]
        print(f"Session ID: {session_id}")
        
        # Count total chat history for this session
        cursor.execute("SELECT count(*) FROM chat_history WHERE session_id = ?", (session_id,))
        count = cursor.fetchone()[0]
        print(f"Total chat history entries for session: {count}")
        
        # List them all
        cursor.execute("SELECT cycle_id, user_query, timestamp FROM chat_history WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
        rows = cursor.fetchall()
        print("\nAll Chat History:")
        for r in rows:
            print(f"- {r[2]}: {r[1]} (Cycle {r[0]})")
            
    else:
        print("Could not find session_id for the given cycle.")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
