import sqlite3
import json

db_path = "logs/orchestrator.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cycle_id_prefix = "040a8866"
    
    print(f"Checking cycle_failures for {cycle_id_prefix}...")
    cursor.execute("SELECT * FROM cycle_failures WHERE cycle_id LIKE ?", (f"{cycle_id_prefix}%",))
    rows = cursor.fetchall()
    
    if rows:
        for row in rows:
            print("\n--- Failure Record ---")
            # cycle_failures schema: id, cycle_id, error_type, error_message, payload_json, created_at
            print(f"ID: {row[0]}")
            print(f"Cycle ID: {row[1]}")
            print(f"Error Type: {row[2]}")
            print(f"Message: {row[3]}")
            print(f"Created At: {row[5]}")
            
            print("\nPayload:")
            try:
                payload = json.loads(row[4])
                print(json.dumps(payload, indent=2))
            except Exception as e:
                print(f"Could not parse payload: {e}")
                print(row[4])
    else:
        print("No records found in cycle_failures.")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
