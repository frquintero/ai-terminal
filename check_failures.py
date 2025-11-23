import sqlite3
import json

db_path = "logs/orchestrator.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cycle_id_prefix = "040a8866"
    
    print(f"Checking cycle_failures for {cycle_id_prefix}...")
    cursor.execute("""
        SELECT cycle_id, session_id, process, stage, route, error_type, error_code,
               error_message, facts_json, created_at
        FROM cycle_failures
        WHERE cycle_id LIKE ?
    """, (f"{cycle_id_prefix}%",))
    rows = cursor.fetchall()
    
    if rows:
        for row in rows:
            print("\n--- Failure Record ---")
            print(f"Cycle ID: {row[0]}")
            print(f"Session ID: {row[1]}")
            print(f"Process: {row[2]}")
            print(f"Stage: {row[3]}")
            print(f"Route: {row[4]}")
            print(f"Error Type: {row[5]}")
            print(f"Error Code: {row[6]}")
            print(f"Message: {row[7]}")
            print(f"Created At: {row[9]}")
            
            print("\nFacts:")
            try:
                facts = json.loads(row[8]) if row[8] else {}
                print(json.dumps(facts, indent=2))
            except Exception as e:
                print(f"Could not parse facts: {e}")
                print(row[8])
    else:
        print("No records found in cycle_failures.")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
