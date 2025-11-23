import sqlite3
import json
import sys

db_path = "logs/orchestrator.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    print(tables)
    
    print("\n--- Searching for cycle like 040a8866% in ALL tables ---")
    tables_to_check = ['cycle_metrics', 'interactions', 'step_outputs', 'task_state', 'cycle_failures', 'chat_history', 'todo_tracking']
    
    found_cycle_id = None
    
    for table in tables_to_check:
        if table in tables:
            try:
                cursor.execute(f"SELECT cycle_id FROM {table} WHERE cycle_id LIKE ?", ("040a8866%",))
                rows = cursor.fetchall()
                if rows:
                    print(f"Found in {table}: {rows}")
                    found_cycle_id = rows[0][0]
            except Exception as e:
                print(f"Error querying {table}: {e}")

    if found_cycle_id:
        cycle_id = found_cycle_id
        print(f"\nFound cycle: {cycle_id}")
        
        print("\n--- Task State ---")
        cursor.execute("SELECT plan_json, status, error_message FROM task_state WHERE cycle_id = ?", (cycle_id,))
        row = cursor.fetchone()
        if row:
            print(f"Status: {row[1]}")
            print(f"Error: {row[2]}")
            try:
                plan = json.loads(row[0])
                print(json.dumps(plan, indent=2))
            except:
                print("Plan JSON invalid")
        else:
            print("No task state found")

        print("\n--- Step Outputs (Detailed) ---")
        cursor.execute("SELECT step_id, tool_name, tool_args_json, success, exit_code, stdout, stderr, output_preview FROM step_outputs WHERE cycle_id = ? ORDER BY step_id", (cycle_id,))
        rows = cursor.fetchall()
        for row in rows:
            print(f"\nStep {row[0]}: {row[1]} (Success: {row[3]})")
            print(f"Args: {row[2]}")
            print(f"Exit Code: {row[4]}")
            print(f"Preview: {row[7]}")
            if not row[3] or True: # Print stdout/stderr for all to see loop behavior
                 print(f"Stdout: {row[5]}")
                 print(f"Stderr: {row[6]}")
            print("-" * 20)

        print("\n--- TODO Tracking ---")
        cursor.execute("SELECT * FROM todo_tracking WHERE cycle_id = ?", (cycle_id,))
        rows = cursor.fetchall()
        for row in rows:
            print(row)
            
    else:
        print("\nCycle 040a8866 not found in any table.")
        
    print("\n--- Cycle Failures Table ---")
    if 'cycle_failures' in tables:
        cursor.execute("SELECT * FROM cycle_failures LIMIT 5")
        rows = cursor.fetchall()
        for row in rows:
            print(row)

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
