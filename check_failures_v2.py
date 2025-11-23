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
            print("\n--- Failure Record Corrected ---")
            print(f"Cycle ID: {row[1]}")
            print(f"Query: {row[3]}")
            print(f"Stage: {row[5]}")
            print(f"Error Type: {row[6]}")
            print(f"Error Message: {row[7]}")
            
            print("\n--- Execution Result (row[10]) ---")
            exec_res_json = row[10]
            if exec_res_json:
                try:
                    exec_res = json.loads(exec_res_json)
                    print(json.dumps(exec_res, indent=2))
                except Exception as e:
                    print(f"JSON parse error: {e}")
                    print(exec_res_json[:500]) # print preview
            else:
                print("None")

    else:
        print("No records found.")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
