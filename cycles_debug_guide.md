# Cycle Debugging Guide

## What is ai-terminal?

**ai-terminal** is an intelligent command-line assistant that uses multiple LLM agents working together to understand user queries and execute system commands. It combines strategic planning (Agent A), precise execution (Agent B), and conversational narration (Agent C) to deliver natural language interaction with the terminal.

For complete project details, setup instructions, and architecture overview, see **[README.md](README.md)**.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER QUERY                               │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  ROUTER: Classify query intent                                   │
│  Routes: SHELL (130+ patterns) | CACHED | CHAT | PLANNER        │
└─────────────────────────┬───────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┬──────────────────┐
        │                 │                 │                  │
        ▼                 ▼                 ▼                  ▼
    ┌───────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
    │ SHELL │      │  CACHED  │      │   CHAT   │      │ PLANNER  │
    │ Fast  │      │ FTS5 DB  │      │ Agent C  │      │  Multi-  │
    │ Exec  │      │  Lookup  │      │  Direct  │      │  Agent   │
    └───┬───┘      └────┬─────┘      └────┬─────┘      └────┬─────┘
        │               │                  │                 │
        │               │                  │                 ▼
        │               │                  │          ┌──────────────┐
        │               │                  │          │  AGENT A     │
        │               │                  │          │  (Planner)   │
        │               │                  │          │  Strategic   │
        │               │                  │          └──────┬───────┘
        │               │                  │                 │
        │               │                  │                 ▼
        │               │                  │          ┌──────────────┐
        │               │                  │          │  AGENT B     │
        │               │                  │          │  (Command    │
        │               │                  │          │   Engineer)  │
        │               │                  │          └──────┬───────┘
        │               │                  │                 │
        │               │                  │                 ▼
        │               │                  │          ┌──────────────┐
        │               │                  │          │  TOOLS       │
        │               │                  │          │  Execution   │
        │               │                  │          └──────┬───────┘
        │               │                  │                 │
        └───────────────┴──────────────────┴─────────────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │    AGENT C       │
                          │   (Narrator/     │
                          │   Chat/Summary)  │
                          └─────────┬────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │  USER RESPONSE   │
                          └──────────────────┘
```

### Key Components

1. **Router**: Classifies user queries into 4 routes
   - **SHELL**: Direct execution (130+ regex patterns)
   - **CACHED**: Previously executed commands (FTS5 lookup)
   - **CHAT**: Simple informational queries → Agent C directly
   - **PLANNER**: Complex multi-step tasks → Agent A → Agent B loop

2. **Agent A (Planner)**: Strategic task decomposer
   - Generates high-level execution plans
   - Three response types: execution plan, clarification request, delegation
   - Does NOT generate precise arguments (that's Agent B's job)

3. **Agent B (Command Engineer)**: Tactical executor
   - Converts Agent A's intent into precise tool arguments
   - Generates exact shell commands, file paths, parameters

4. **Agent C (Narrator/Chat/Summarizer)**: Universal narrator
   - **Chat mode**: Direct conversational responses (CHAT route)
   - **Narrator mode**: Translates tool outputs into natural language (PLANNER route)
   - **Summarizer mode**: Provides final summary of multi-step tasks

5. **Memory (SQLite Database)**: `logs/orchestrator.db`
   - Stores all cycles, agent interactions, step outputs
   - Enables context retrieval and intention caching
   - Powers FTS5 full-text search

## Database Schema

### Key Tables

1. **`router_decisions`**: Route classification per cycle
   - `cycle_id`: Unique identifier (UUID)
   - `route`: SHELL | CACHED | CHAT | PLANNER
   - `query_text`: User's original query
   - `confidence`: Router confidence score (0.0-1.0)

2. **`interactions`**: LLM agent calls (A, B, or C)
   - `cycle_id`: Links to router_decisions
   - `role`: 'A' | 'B' | 'C'
   - `prompt_preview`: First 500 chars of prompt
   - `response_preview`: First 500 chars of response
   - `token_usage_json`: Token counts
   - `latency_ms`: LLM call latency

3. **`step_outputs`**: Tool execution results (PLANNER route only)
   - `cycle_id`: Links to router_decisions
   - `step_id`: Step number in plan (0-indexed)
   - `tool_name`: Tool executed (e.g., "run_command")
   - `tool_args_json`: Precise arguments from Agent B
   - `success`: Boolean success flag
   - `output_preview`: Tool output (truncated to 10KB)

4. **`chat_history`**: Conversational exchanges (CHAT route)
   - `session_id`: Session identifier
   - `cycle_id`: Links to router_decisions
   - `user_query`: User's question
   - `agent_response`: Agent C's response

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

## Quick Reference Commands

```bash
# List recent cycles
sqlite3 logs/orchestrator.db "SELECT cycle_id, route, query_text, created_at FROM router_decisions ORDER BY created_at DESC LIMIT 10;"

# Count cycles by route
sqlite3 logs/orchestrator.db "SELECT route, COUNT(*) FROM router_decisions GROUP BY route;"

# Find cycles with specific query text
sqlite3 logs/orchestrator.db "SELECT cycle_id, route, query_text FROM router_decisions WHERE query_text LIKE '%search term%';"

# Get Agent C responses
sqlite3 logs/orchestrator.db "SELECT cycle_id, response_preview FROM interactions WHERE role = 'C' ORDER BY id DESC LIMIT 5;"

# Check for failed steps
sqlite3 logs/orchestrator.db "SELECT cycle_id, step_id, tool_name, exit_code FROM step_outputs WHERE success = 0;"
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
