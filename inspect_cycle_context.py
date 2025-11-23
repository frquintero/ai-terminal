import sqlite3
import json

db_path = "logs/orchestrator.db"
cycle_id_prefix = "782a5280"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check interaction logs for Agent A
    # The context message is typically embedded in the prompt sent to Agent A
    print(f"Searching for interactions with cycle_id starting with {cycle_id_prefix}...")
    
    cursor.execute("""
        SELECT role, prompt_preview, created_at 
        FROM interactions 
        WHERE cycle_id LIKE ? AND role = 'A'
        ORDER BY created_at DESC
    """, (f"{cycle_id_prefix}%",))
    
    rows = cursor.fetchall()
    
    if rows:
        for row in rows:
            print(f"\n--- Interaction (Role: {row[0]}) ---")
            print(f"Time: {row[2]}")
            print("Prompt Preview:")
            print(row[1])
            
            # If we have full logs stored elsewhere (e.g. llm_traces), we might check there too
            # But interactions table usually stores previews. 
            # Let's check llm_traces if it exists.
    else:
        print("No interactions found for this cycle.")

    # Also check cycle_failures just in case
    cursor.execute("""
        SELECT process, stage, error_type, error_code, error_message, facts_json
        FROM cycle_failures
        WHERE cycle_id LIKE ?
    """, (f"{cycle_id_prefix}%",))
    row = cursor.fetchone()
    if row:
        print("\n--- Cycle Failure Telemetry ---")
        print(f"Process: {row[0]}")
        print(f"Stage: {row[1]}")
        print(f"Error Type: {row[2]}")
        print(f"Error Code: {row[3]}")
        print(f"Error Message: {row[4]}")
        facts_json = row[5]
        if facts_json:
            try:
                facts = json.loads(facts_json)
                print("Facts:")
                print(json.dumps(facts, indent=2))
            except Exception:
                print("Could not parse facts JSON")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
