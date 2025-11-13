# Cycle Debugging Guide

## What is ai-terminal?

**ai-terminal** is an intelligent command-line assistant that uses multiple LLM agents working together to understand user queries and execute system commands. It combines strategic planning (Agent A), precise execution (Agent B), and conversational narration (Agent C) to deliver natural language interaction with the terminal.

For complete project details, setup instructions, and architecture overview, see **[README.md](README.md)**.

## Architecture Overview (v3.0)

**UPGRADED**: Router removed. Agent A is now the single decision-maker.

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER QUERY                               │
└─────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│               AGENT A: Decision-Maker                            │
│   Returns: direct_answer | clarify | steps (with template)      │
└──────────────┬───────────────────────────────┬───────────────────┘
               │                               │
          (answer)                        (execute)
               │                               │
               ▼                               ▼
        ┌────────────┐              ┌──────────────────┐
        │ Direct     │              │  AGENT B         │
        │ Answer     │              │  (Command        │
        │ (2-3 sen)  │              │   Engineer)      │
        └─────┬──────┘              │  Generates       │
              │                     │  tool_args       │
              │                     └──────┬───────────┘
              │                            │
              │                            ▼
              │                    ┌──────────────────┐
              │                    │  TOOLS           │
              │                    │  Execution +     │
              │                    │  Exports         │
              │                    └──────┬───────────┘
              │                            │
              │                            ▼
              │                    ┌──────────────────┐
              │                    │  Variables       │
              │                    │  Binding &       │
              │                    │  Placeholder     │
              │                    │  Substitution    │
              │                    └──────┬───────────┘
              │                            │
              └────────────┬───────────────┘
                           │
                           ▼
                  ┌─────────────────────┐
                  │  Final Response     │
                  │  (Template or       │
                  │   Summary)          │
                  └────────┬────────────┘
                           │
                           ▼
                  ┌─────────────────────┐
                  │  USER RESPONSE      │
                  └─────────────────────┘
```

### Key Components (v3.0)

1. **Agent A (Decision-Maker)**: Single entry point for all queries
   - Three response types:
     - `{"direct_answer": "..."}` — For no-tool questions
     - `{"clarify": "..."}` — For ambiguous queries
     - `{"steps": [...], "final_response_template": "..."}` — For execution plans
   - Replaces Router entirely

2. **Agent B (Command Engineer)**: Tactical executor
   - Converts Agent A's intent into precise tool arguments
   - Returns JSON: `{"tool_name": "...", "tool_args": {...}}`
   - Uses exported variables via `${var}` placeholders

3. **Exports & Placeholders**: Deterministic variable extraction
   - Step can export: `{"name": "count", "method": "regex", "pattern": "^(\\d+)\\s*$"}`
   - Later steps reference: `${count}` in tool_args
   - Final response uses: `{count}` in template
   - Stored in `variable_bindings` table for auditability

4. **Repair Loop**: On extract failure
   - Call Agent A with structured repair request
   - Agent A patches the step or suggests remediation
   - Max 1 repair per step; then fail with clarity

5. **Memory (SQLite Database)**: `logs/orchestrator.db`
   - Original tables: `router_decisions`, `step_outputs`, `chat_history`, `interactions`, `llm_traces`
   - New tables: `variable_bindings`, `step_commands`, `direct_answers` (cache)
   - Enables full audit trail of variable extraction and placeholder resolution

## Database Schema (v3.0)

### Original Tables (preserved for backward compatibility)

1. **`router_decisions`**: Cycle metadata
   - `cycle_id`: Unique identifier (UUID)
   - `route`: ANSWER | CLARIFY | EXECUTE (new); old: SHELL | CACHED | CHAT | PLANNER
   - `query_text`: User's original query
   - `confidence`: Agent A confidence score (0.0-1.0)

2. **`interactions`**: LLM agent calls (A or B; no more C)
   - `cycle_id`: Links to router_decisions
   - `role`: 'A' | 'B'
   - `prompt_preview`: First 500 chars of prompt
   - `response_preview`: First 500 chars of response
   - `token_usage_json`: Token counts
   - `latency_ms`: LLM call latency

3. **`step_outputs`**: Tool execution results
   - `cycle_id`: Links to router_decisions
   - `step_id`: Step number in plan (0-indexed)
   - `tool_name`: Tool executed (e.g., "run_command")
   - `tool_args_json`: Precise arguments from Agent B
   - `success`: Boolean success flag
   - `output_preview`: Tool output (truncated to 10KB)
   - `exit_code`: Exit code (for shell commands)

4. **`chat_history`**: Conversational exchanges (ANSWER route with interaction)
   - `session_id`: Session identifier
   - `cycle_id`: Links to router_decisions
   - `user_query`: User's question
   - `agent_response`: Agent A's answer

### New Tables (v3.0)

5. **`variable_bindings`**: Extracted variables from step outputs
   - `cycle_id`: Links to router_decisions
   - `step_id`: Which step exported this variable
   - `var_name`: Variable name (e.g., "py_count")
   - `var_value`: Extracted value (e.g., "42")
   - `extraction_method`: "regex" | "json" | "lines" | "all"
   - `extractor_spec`: Full ExportSpec as JSON (includes pattern, transform, etc.)
   - `created_at`: When extracted

6. **`step_commands`**: Resolved tool arguments (for audit trail)
   - `cycle_id`: Links to router_decisions
   - `step_id`: Which step
   - `tool_name`: Tool executed
   - `command_template`: Step description (original intent)
   - `resolved_command`: Fully resolved tool_args JSON (after ${var} substitution)
   - `substitution_log`: JSON log of {var_name: original_value} for audit
   - `created_at`: When executed

7. **`direct_answers`** (optional cache): Direct answers to exact queries
   - `normalized_query`: Lowercased, stripped query (unique key)
   - `answer`: Agent A's cached answer
   - `created_at`: When cached
   - `expires_at`: TTL for freshness

## How to Debug a Cycle

### Prerequisites

- Cycle ID (short prefix, e.g., `1219b8eb` or full UUID)
- Access to `logs/orchestrator.db`
- Python 3 with sqlite3

### Step 1: Use the Debug Tool

The repository includes `debug_cycle.py` - a comprehensive cycle analysis tool that provides detailed information about any cycle execution.

**Usage:**

```bash
# Analyze a specific cycle using the 8-character prefix
python3 debug_cycle.py 1219b8eb

# Or with the full UUID
python3 debug_cycle.py 1219b8eb-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**What it shows:**
- Router decision (route, query, confidence)
- Agent interactions (A, B, C calls with latency and token usage)
- Step execution details (tool, args, success, output)
- Chat exchanges (for CHAT route)
- Automatically deduplicates steps (handles known logging bug)

If the cycle isn't found, it displays the 5 most recent cycles to help you find the right ID.

### Step 2: Interpret Results

#### ✅ Successful Cycle Indicators

1. **Router Decision**: Appropriate route selected
2. **Agent Interactions**: 
   - CHAT: 1 Agent C call
   - SHELL: 0 agent calls (direct execution)
   - PLANNER: Agent A → Agent B → Agent C (3+ calls)
3. **Step Outputs**: success=True, reasonable exit codes
4. **Agent C Response**: Accurate, matches tool output

#### ❌ Problem Indicators

1. **Hallucination**: Agent C claims success but tool output doesn't support it
2. **High Latency**: >3s per agent call (investigate prompt size)
3. **Multiple Agent A Calls**: Validation failures, retry loop
4. **Missing Context**: Agent C lacks Agent A intent or Agent B args
5. **Duplicate Steps**: Same step_id appears multiple times (known bug)

## Common Debugging Scenarios

### Scenario 1: Agent C Hallucination

**Symptoms:**
- Tool executed successfully (exit code 0)
- Agent C claims feature exists/works
- But tool output doesn't prove the claim

**Example:**
- User: "did we implement X?"
- Agent A: Search for X
- Agent B: `grep -n 'X' file.py`
- Tool: Returns class definition (exit code 0)
- Agent C: "Yes, feature X is implemented!" ❌ WRONG

**Root Cause:**
- Agent C only sees: tool_name, tool_output, success flag
- Agent C MISSING: Agent A's intent ("search for X implementation")
- Agent C assumes: tool success = task success

**Fix (bd issue ai-terminal-mau2):**
- Pass Agent A step intent/description to Agent C
- Pass Agent B tool_args to Agent C
- Agent C can verify: Does output prove the intent?

### Scenario 2: Verbose Agent C Responses

**Symptoms:**
- Agent C generates long explanations (>5 sentences)
- User wanted quick answer

**Example:**
- User: "how many txt files"
- Agent C: "Found 18 text files in your current directory. I simply ran a quick count of every file ending in .txt by using the find command with maxdepth 1 to search only the current directory and wc to count the results..."

**Root Cause:**
- Agent C narrator prompt didn't enforce brevity

**Fix (uncommitted changes):**
- Updated `AGENT_C_NARRATOR_PROMPT` to require 2-3 sentences max
- Added good/bad examples
- Emphasized concise responses

### Scenario 3: Wrong Route Selection

**Symptoms:**
- Simple query routed to PLANNER (overkill)
- Complex task routed to CHAT (insufficient)

**Example:**
- User: "list files"
- Router: PLANNER (should be SHELL)
- Result: Slow execution (Agent A → Agent B → Tool → Agent C)

**Root Cause:**
- Router keyword matching insufficient
- Low confidence threshold

**Fix:**
- Improve router rules in `router/rules.py`
- Add more SHELL patterns
- Implement Agent A three-way response (clarify/delegate)

### Scenario 4: Agent A Forced Planning

**Symptoms:**
- Verification question ("did we implement X?") routed to PLANNER
- Agent A creates unnecessary grep plan
- Should have asked for clarification

**Example:**
- User: "did we implement X?"
- Agent A: Creates search plan (forced to plan)
- Better: Agent A asks "Check existence or implement it?"

**Root Cause:**
- Agent A only supports `{"steps": [...]}` response
- No clarification mechanism

**Fix (implemented in ai-terminal-vyt7):**
- Agent A now supports three response types:
  1. `{"steps": [...]}` - Execute
  2. `{"clarify": "..."}` - Ask user
  3. `{"delegate_to_chat": "..."}` - Route to Agent C

## Query Audit Examples (v3.0)

### Query 1: Trace variable extraction across a multi-step cycle

**Scenario**: User runs a multi-step task. Want to see what variables were extracted and how they were used.

```bash
# Find the cycle ID
CYCLE_ID="abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# 1. Show the plan and Agent A decision
sqlite3 logs/orchestrator.db "\
  SELECT cycle_id, route, query_text 
  FROM router_decisions 
  WHERE cycle_id LIKE '${CYCLE_ID}%';"

# 2. Show all variables extracted in this cycle
sqlite3 logs/orchestrator.db "\
  SELECT step_id, var_name, var_value, extraction_method 
  FROM variable_bindings 
  WHERE cycle_id LIKE '${CYCLE_ID}%' 
  ORDER BY step_id, var_name;"

# 3. Show how variables were used in tool_args (audit trail)
sqlite3 logs/orchestrator.db "\
  SELECT step_id, tool_name, resolved_command, substitution_log 
  FROM step_commands 
  WHERE cycle_id LIKE '${CYCLE_ID}%' 
  ORDER BY step_id;"

# 4. Show actual step execution results
sqlite3 logs/orchestrator.db "\
  SELECT step_id, tool_name, success, exit_code, output_preview 
  FROM step_outputs 
  WHERE cycle_id LIKE '${CYCLE_ID}%' 
  ORDER BY step_id;"
```

**Example output**:
```
step_id | var_name  | var_value | extraction_method
--------|-----------|-----------|------------------
0       | py_count  | 42        | regex
1       | lines_sum | 1523      | regex

step_id | tool_name  | resolved_command              | substitution_log
--------|------------|-------------------------------|------------------
0       | run_command| {"command":"ls -1 *.py..."} | {}
1       | run_command| {"command":"wc -l ${py_count}..."} | {"py_count": "42"}
```

### Query 2: Check for export failures and repair loop triggers

**Scenario**: A step's export failed. Did Agent A repair it?

```bash
# Find cycles with failed exports
sqlite3 logs/orchestrator.db "\
  SELECT DISTINCT rd.cycle_id, rd.query_text 
  FROM router_decisions rd 
  JOIN step_outputs so ON rd.cycle_id = so.cycle_id 
  WHERE so.success = 0 
  ORDER BY rd.created_at DESC 
  LIMIT 10;"

# For a specific cycle, check if repair loop was called
sqlite3 logs/orchestrator.db "\
  SELECT COUNT(*) as agent_a_calls 
  FROM interactions 
  WHERE cycle_id = 'abc12345...' AND role = 'A';"

# Expected: 2 Agent A calls (first plan + repair) or 1 (no repair needed)
```

### Query 3: Audit placeholder substitution in tool_args

**Scenario**: User suspects incorrect variable substitution. Verify what was actually executed.

```bash
# Show exact substitution before execution
sqlite3 logs/orchestrator.db "\
  SELECT 
    step_id, 
    tool_name, 
    resolved_command as actual_tool_args,
    json_extract(substitution_log, '$.py_count') as resolved_py_count_value
  FROM step_commands 
  WHERE cycle_id = 'abc12345...' 
  ORDER BY step_id;"

# Cross-check with variable_bindings
sqlite3 logs/orchestrator.db "\
  SELECT var_name, var_value 
  FROM variable_bindings 
  WHERE cycle_id = 'abc12345...' 
  ORDER BY step_id;"
```

### Query 4: Trace direct_answer caching

**Scenario**: A user asked the same question twice. Did we cache the answer?

```bash
# Find all ANSWER-type cycles
sqlite3 logs/orchestrator.db "\
  SELECT cycle_id, route, query_text, created_at 
  FROM router_decisions 
  WHERE route = 'ANSWER' 
  ORDER BY created_at DESC 
  LIMIT 20;"

# Check if an answer is cached
sqlite3 logs/orchestrator.db "\
  SELECT normalized_query, answer, expires_at 
  FROM direct_answers 
  WHERE normalized_query LIKE '%python%' 
  LIMIT 5;"

# See how many times a cached answer was used
sqlite3 logs/orchestrator.db "\
  SELECT 
    da.normalized_query, 
    COUNT(rd.cycle_id) as uses, 
    MAX(rd.created_at) as last_used
  FROM direct_answers da 
  LEFT JOIN router_decisions rd ON rd.query_text LIKE '%' || da.normalized_query || '%'
  GROUP BY da.normalized_query 
  ORDER BY uses DESC;"
```

### Query 5: Find steps that needed repair

**Scenario**: Which steps are fragile and require repair loop?

```bash
# Count how many cycles triggered repair logic
sqlite3 logs/orchestrator.db "\
  SELECT 
    SUBSTR(cycle_id, 1, 8) as cycle_prefix,
    COUNT(DISTINCT i.cycle_id) as total_agent_a_calls
  FROM interactions i 
  WHERE i.role = 'A' 
  GROUP BY cycle_prefix 
  HAVING COUNT(*) > 1
  ORDER BY total_agent_a_calls DESC;"

# For each repair, see what failed
sqlite3 logs/orchestrator.db "\
  SELECT 
    vb.cycle_id, 
    vb.step_id, 
    vb.var_name, 
    COUNT(*) as extract_attempts
  FROM variable_bindings vb 
  GROUP BY vb.cycle_id, vb.step_id, vb.var_name 
  HAVING COUNT(*) > 1;"
```

### Query 6: Full cycle audit (all-in-one)

**Scenario**: Get complete audit of a cycle for debugging.

```bash
# Use debug_cycle.py (see next section)
python3 debug_cycle.py abc12345

# Or manually query:
echo "=== Cycle Metadata ==="
sqlite3 logs/orchestrator.db "SELECT cycle_id, route, query_text, confidence, created_at FROM router_decisions WHERE cycle_id LIKE 'abc12345%';"

echo "=== Agent Calls ==="
sqlite3 logs/orchestrator.db "SELECT role, prompt_preview, response_preview, latency_ms FROM interactions WHERE cycle_id LIKE 'abc12345%';"

echo "=== Variable Bindings ==="
sqlite3 logs/orchestrator.db "SELECT step_id, var_name, var_value FROM variable_bindings WHERE cycle_id LIKE 'abc12345%';"

echo "=== Step Outputs ==="
sqlite3 logs/orchestrator.db "SELECT step_id, tool_name, success, exit_code FROM step_outputs WHERE cycle_id LIKE 'abc12345%';"
```

## Quick Reference Commands

```bash
# List recent cycles
sqlite3 logs/orchestrator.db "SELECT cycle_id, route, query_text, created_at FROM router_decisions ORDER BY created_at DESC LIMIT 10;"

# Count cycles by route (v3.0 routes)
sqlite3 logs/orchestrator.db "SELECT route, COUNT(*) FROM router_decisions GROUP BY route;"

# Find cycles with specific query text
sqlite3 logs/orchestrator.db "SELECT cycle_id, route, query_text FROM router_decisions WHERE query_text LIKE '%search term%';"

# Get Agent A responses (replaces Agent C)
sqlite3 logs/orchestrator.db "SELECT cycle_id, response_preview FROM interactions WHERE role = 'A' ORDER BY id DESC LIMIT 5;"

# Check for failed steps
sqlite3 logs/orchestrator.db "SELECT cycle_id, step_id, tool_name, exit_code FROM step_outputs WHERE success = 0;"

# Show all variables exported in a cycle
sqlite3 logs/orchestrator.db "SELECT step_id, var_name, var_value FROM variable_bindings WHERE cycle_id = '<cycle_id>';"

# List cycles that needed repair (>1 Agent A call)
sqlite3 logs/orchestrator.db "SELECT cycle_id, COUNT(*) as repairs FROM interactions WHERE role='A' GROUP BY cycle_id HAVING COUNT(*)>1;"
```

## Tips for Effective Debugging

1. **Start with Router Decision**: Understand which path was taken
2. **Check Agent Interactions**: Verify agent call sequence
3. **Compare Intent vs Output**: Does tool output match Agent A's intent?
4. **Look for Patterns**: Same type of failure across cycles?
5. **Check Timestamps**: High latency = investigate prompt size
6. **Use Full Context**: Read prompt_preview + response_preview + tool output together

## Known Issues

1. **Duplicate Steps**: Same step logged twice in step_outputs (cosmetic bug)
2. **Missing Agent Context**: Agent C doesn't receive Agent A intent (ai-terminal-mau2)
3. **Verbose Responses**: Agent C can be wordy (prompt update pending)
4. **Cycle ID Format**: Database uses full UUIDs, use prefix matching (`LIKE '1219b8eb%'`)

## Further Reading

- **[README.md](README.md)** - Project overview, setup guide, configuration, testing, and complete documentation index
- `DOUBLE_AGENT_ARCHITECTURE.md` - Complete architecture specification
- `AGENTS.md` - Agent system overview and bd issue tracking
- `orchestrator/prompts.py` - Agent system prompts

---

**Last Updated:** 2025-11-13  
**Version:** v2.0 (Context v2 + Institutional Memory)
