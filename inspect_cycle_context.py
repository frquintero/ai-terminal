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
    cursor.execute("SELECT context_json FROM cycle_failures WHERE cycle_id LIKE ?", (f"{cycle_id_prefix}%",))
    row = cursor.fetchone()
    if row and row[0]:
        print("\n--- Cycle Failure Context ---")
        try:
            ctx = json.loads(row[0])
            print(json.dumps(ctx, indent=2))
        except:
            print("Could not parse context JSON")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
