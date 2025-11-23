import sqlite3

db_path = "logs/orchestrator.db"
cycle_id = "9d818152"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"--- Searching for {cycle_id} in all tables ---")
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    
    found = False
    for table in tables:
        try:
            cursor.execute(f"SELECT * FROM {table} WHERE cycle_id LIKE ?", (f"{cycle_id}%",))
            rows = cursor.fetchall()
            if rows:
                print(f"Found in table '{table}':")
                for row in rows:
                    print(row)
                found = True
                
                # If in sessions table (unlikely for cycle_id), or has session_id column
                # Let's check if we can extract session_id from the row if possible
                # (Naive check)
        except Exception:
            pass
            
    if not found:
        print("Cycle completely missing from DB.")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
