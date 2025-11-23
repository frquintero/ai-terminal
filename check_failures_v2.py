import sqlite3
import json

db_path = "logs/orchestrator.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cycle_id_prefix = "040a8866"
    
    print(f"Checking cycle_failures for {cycle_id_prefix}...")
    cursor.execute("""
        SELECT cycle_id, query_text, process, stage, error_type, error_code,
               error_message, facts_json, created_at
        FROM cycle_failures
        WHERE cycle_id LIKE ?
    """, (f"{cycle_id_prefix}%",))
    rows = cursor.fetchall()
    
    if rows:
        for row in rows:
            print("\n--- Failure Record Corrected ---")
            print(f"Cycle ID: {row[0]}")
            print(f"Query: {row[1]}")
            print(f"Process: {row[2]}")
            print(f"Stage: {row[3]}")
            print(f"Error Type: {row[4]}")
            print(f"Error Code: {row[5]}")
            print(f"Error Message: {row[6]}")
            print(f"Created At: {row[8]}")
            
            print("\n--- Facts ---")
            facts_json = row[7]
            if facts_json:
                try:
                    facts = json.loads(facts_json)
                    print(json.dumps(facts, indent=2))
                except Exception as e:
                    print(f"JSON parse error: {e}")
                    print(facts_json[:500]) # print preview
            else:
                print("None")

    else:
        print("No records found.")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
