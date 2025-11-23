import sqlite3
import json

db_path = "logs/orchestrator.db"
target_cycle = "9d818152"
reference_cycle = "782a5280"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"--- Analyzing Cycle {target_cycle} ---")
    
    # Check cycle metrics to get basic info
    cursor.execute("SELECT cycle_id, latency_ms FROM cycle_metrics WHERE cycle_id LIKE ?", (f"{target_cycle}%",))
    row = cursor.fetchone()
    if row:
        print(f"Found in cycle_metrics: {row}")
        full_target_id = row[0]
    else:
        print("Not found in cycle_metrics.")
        full_target_id = None

    # Check chat_history
    if full_target_id:
        cursor.execute("SELECT session_id, timestamp, user_query FROM chat_history WHERE cycle_id = ?", (full_target_id,))
        chat_row = cursor.fetchone()
        if chat_row:
            print(f"Found in chat_history:")
            print(f"  Session ID: {chat_row[0]}")
            print(f"  Timestamp:  {chat_row[1]}")
            print(f"  Query:      {chat_row[2]}")
            target_session = chat_row[0]
            target_ts = chat_row[1]
        else:
            print("Not found in chat_history (maybe failed cycle?)")
            target_session = None
            target_ts = None
            
        # Check failures
        cursor.execute("SELECT created_at, error_message FROM cycle_failures WHERE cycle_id = ?", (full_target_id,))
        fail_row = cursor.fetchone()
        if fail_row:
            print(f"Found in cycle_failures:")
            print(f"  Timestamp: {fail_row[0]}")
            print(f"  Error:     {fail_row[1]}")
    
    print(f"\n--- Analyzing Reference Cycle {reference_cycle} ---")
    cursor.execute("SELECT session_id, timestamp FROM chat_history WHERE cycle_id LIKE ?", (f"{reference_cycle}%",))
    ref_row = cursor.fetchone()
    if ref_row:
        print(f"Found in chat_history:")
        print(f"  Session ID: {ref_row[0]}")
        print(f"  Timestamp:  {ref_row[1]}")
        ref_session = ref_row[0]
        ref_ts = ref_row[1]
        
        if target_session and ref_session:
            print("\n--- Comparison ---")
            if target_session != ref_session:
                print(f"DIFFERENT SESSIONS!")
                print(f"Target Session:    {target_session}")
                print(f"Reference Session: {ref_session}")
            else:
                print("SAME SESSION.")
                if target_ts and ref_ts:
                    print(f"Target Time:    {target_ts}")
                    print(f"Reference Time: {ref_ts}")
                    if target_ts > ref_ts:
                        print("Target happened AFTER Reference (normal to be missing from history).")
                    else:
                        print("Target happened BEFORE Reference (SHOULD be in history).")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
