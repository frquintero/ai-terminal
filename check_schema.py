import sqlite3

db_path = "logs/orchestrator.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Schema for cycle_failures:")
    cursor.execute("PRAGMA table_info(cycle_failures)")
    columns = cursor.fetchall()
    for col in columns:
        print(col)

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
