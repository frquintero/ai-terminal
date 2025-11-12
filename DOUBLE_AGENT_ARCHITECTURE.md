# Triple Agent Architecture with Intelligent Router and Python Orchestrator

## Problem

Current artificial intelligences fail at real-world tasks because they:
- Hallucinate data
- Don't know which tool to use or when
- Lose track in complex tasks
- Depend on memory instead of verified execution
- Waste resources on simple queries that don't need complex orchestration

The result is attractive but useless responses when action is required in the local environment, such as shell, files, internet, or databases. Additionally, routing all queries through complex multi-step pipelines creates unnecessary latency and cost.

## Solution

Build a four-part system with intelligent query routing:

1. **The Router (Tiny Bird)** - Intelligent classifier that routes queries to the appropriate execution path
2. **Agent A (Planner)** - Strategic planner that creates algorithmic plans for complex tasks
3. **Agent B (Command Engineer)** - Precise tool executor that translates plan steps into tool calls
4. **Agent C (Chat)** - Conversational responder for simple informational queries
5. **Python Orchestrator** - Deterministic controller that manages execution, memory, and coordinates all agents

**Critical Design Principle**: There is **ONE LLM** called by the orchestrator in **THREE DIFFERENT ROLES** (A, B, or C), each with a specialized system prompt and context. The Router determines which role to invoke.

The flow is based on **intelligent routing** followed by **linear stack execution** for complex tasks: plans execute sequentially, validated and advanced only if the previous step was successful. No improvisation or jumps.

## How It Works

### Architecture Overview

```
User Query
    ↓
[The Router (Tiny Bird)] ← Fast classification (100-200ms)
    ↓
    ├─→ [CHAT] → Agent C (conversational response) → Orchestrator (display) → User
    ├─→ [CACHED] → Execute tool → Agent C (narrativize) → Orchestrator (display) → User
    └─→ [PLANNER] → Agent A/B (execute plan) → Agent C (summarize) → Orchestrator (display) → User
```

**Key Insights**: 
1. The orchestrator calls the **same LLM** in **different roles** using specialized system prompts and contexts:
   - **Agent A role**: Strategic planner with planning-focused system prompt
   - **Agent B role**: Tool executor with execution-focused system prompt  
   - **Agent C role**: Conversational assistant with chat-focused system prompt

2. **Agent C is the universal narrator**: Every route ends with Agent C generating a conversational response (whether pure chat, narrating tool outputs, or summarizing execution results)

3. **Orchestrator is the universal presenter**: After Agent C generates the narrative, the orchestrator formats and displays it to the terminal (colors, formatting, progress indicators)

### Workflow

The user presents a query, which could be:
- Simple: "What is the capital of Japan?"
- Cached: "Show me my command history"
- Complex: "Show me the five newest .txt files in /docs and sort them by size"

Each query initiates a new orchestration cycle with a unique ID. This ID tracks the progress and state of the current cycle. All interactions are logged in a central SQLite database (the memory) for traceability, context management, and to provide memory without relying on the stateless nature of LLMs.

#### Phase 1: Intelligent Routing

The orchestrator receives the query and logs it in the SQLite database. All subsequent interactions related to this query ID are also logged.

**The Router (Tiny Bird)** - a lightweight, fast classifier - analyzes the query and classifies it into one of three routes:

1. **`[CHAT]`** - Simple informational queries
   - Examples: "capital of Japan", "explain recursion", "what is Docker?"
   - Decision: Query requires general knowledge, no tools needed
   - Action: Orchestrator calls LLM in **Agent C (Chat)** role with minimal context
   - Latency: ~500ms (single LLM call)
   - Cost: Minimal (only user query + chat system prompt tokens)

2. **`[CACHED]`** - Previously executed queries with stored solutions
   - Examples: "show command history", "list files in current directory"
   - Decision: Query matches a previous successful execution (intention caching)
   - Action: Orchestrator retrieves cached tool + arguments and executes directly
   - Latency: ~50ms (database lookup + tool execution, **zero LLM calls**)
   - Cost: Zero API cost

3. **`[PLANNER]`** - Complex multi-step tasks requiring orchestration
   - Examples: "analyze logs and fix the issue", "refactor this module"
   - Decision: Query requires planning, multiple tools, or complex logic
   - Action: Full orchestration with Agent A → Agent B loop
   - Latency: ~2-3s (multiple LLM calls in different roles)
   - Cost: Higher (multiple role invocations + full context)

**Router Implementation**: The Router uses a hybrid approach:
- **Fast rules first**: Regex patterns for obvious cases (e.g., "what is..." → CHAT)
- **Intention cache lookup**: Semantic similarity search against successful executions
- **ML classifier**: Lightweight model (DistilBERT) for ambiguous cases
- **Conservative fallback**: If confidence < 80%, default to PLANNER (safe)

#### Phase 2: Execution (Route-Specific)

**Route: [CHAT]**

The orchestrator calls the LLM in **Agent C (Chat) role** with:
- Chat system prompt: "You are a helpful conversational assistant..."
- User query
- Last 10 chat interactions from SQLite (conversational context)
- No tool schemas or complex execution state

Agent C generates a natural language response. The orchestrator then formats and displays this response to the terminal.

**Route: [CACHED]**

The orchestrator:
1. Retrieves the cached tool name and arguments from SQLite
2. Executes the tool directly (zero LLM calls at this stage)
3. Calls the LLM in **Agent C (Narrator) role** with:
   - Narrator system prompt: "You are a narrator that translates tool outputs into natural conversation..."
   - User's original query
   - Raw tool output
   - Task: "Present these results conversationally"
4. Agent C generates a narrative response
5. Orchestrator formats and displays the narrative to the terminal
6. Updates cache statistics and confidence scores

**Route: [PLANNER]**

The orchestrator calls the LLM in **Agent A (Planner) role** with: 

**Route: [PLANNER]**

The orchestrator calls the LLM in **Agent A (Planner) role** with:
- Planning-focused system prompt: "You are a strategic planner..."
- User query
- List of available tools (names only)
- System information (date, time, OS, etc.)
- Memory of previous interactions between Agent A and the orchestrator

Only one interaction between Agent A and the orchestrator is expected per user query. The orchestrator will not interact again with Agent A until the current plan is completed or an error occurs (e.g., certain tool is not available and Agent B could not complete the plan).

The Planner (LLM in Agent A role) generates a structured algorithmic plan in JSON/JSONL format, detailing one of three things:
1. The steps required to fulfill the user's request
2. A call to a web_search tool for additional information needed to complete the plan
3. Clarifying questions to be asked to the user if the request is ambiguous

The orchestrator validates the received JSON/JSONL format. If valid, it parses the plan and extracts the first step. It then builds the contextual prompt for the next phase.

For each step in the plan, the orchestrator calls the LLM in **Agent B (Command Engineer) role** with:
- Execution-focused system prompt: "You are a precise tool executor..."
- User query
- Complete plan (for strategic context)
- Current step to execute
- Outputs from previous steps
- Detailed tool schemas with usage examples

The LLM in Agent B role generates precise, executable instructions. The orchestrator executes these instructions, validates results, and saves outputs. This cycle continues until the entire plan is executed or an error occurs.

Once all steps are complete, the orchestrator calls the LLM in **Agent C (Summarizer) role** with:
- Summarizer system prompt: "You are a task summarizer that explains what actions were taken..."
- User's original query
- Complete plan that was executed
- Summary of all step outputs (not full raw data)
- Task: "Summarize what was accomplished conversationally"

Agent C generates a narrative summary of the execution. The orchestrator then formats and displays this summary to the terminal.

**Error Handling:**
- Invalid JSON from Agent A: Orchestrator asks Agent A (LLM in planner role) for valid JSON
- Invalid plan (unregistered tools): Orchestrator asks Agent A to clarify
- Execution failure: Orchestrator asks Agent B (LLM in executor role) to correct instructions, with retry limit

The orchestrator ensures transparency by logging all interactions, plans, steps, errors, and results in the SQLite database. Every completed step is communicated back to the user in real-time.

When Agent B receives the prompt from the orchestrator, it generates precise and executable instructions based on the current step from the algorithmic plan provided by Agent A. Agent B limits itself to the provided tools and generates verifiable commands. The orchestrator then executes these instructions, validates the results, saves the outputs, advances to the next step in the plan and generate the next prompt for Agent B. This cycle continues until the entire plan is executed or an error occurs.

The orchestrator honors transparency and traceability by logging all interactions, plans, steps, errors, and results in the central SQLite database. This ensures that every action taken can be audited and reviewed later. Additionally, every step in the process is communicated back to the user for transparency in real-time along with tool usage, even intentions caching.

### The Router (Tiny Bird): Intelligent Query Classifier

**Role:** The Router is a lightweight, fast classifier that analyzes incoming user queries and routes them to the appropriate execution path. It sits at the entry point of the system and makes intelligent decisions about which LLM role (if any) should handle the query.

**Input:**
- User query (raw text)
- Query embeddings (for semantic similarity matching)
- Historical execution patterns from SQLite

**Output:**
- Classification decision: `[CHAT]`, `[CACHED]`, or `[PLANNER]`
- Confidence score (0.0 to 1.0)
- For `[CACHED]`: Retrieved tool name and arguments

**Classification Logic:**

1. **Fast Rule Matching** (10-20ms)
   - Regex patterns for obvious cases:
     - "what is...", "explain...", "define..." → likely `[CHAT]`
     - "capital of...", "who is..." → likely `[CHAT]`
   - Simple command patterns:
     - "list files", "show history" → check cache first

2. **Intention Cache Lookup** (30-50ms)
   - Generate query embedding
   - Search SQLite for similar successful executions (cosine similarity > 0.85)
   - If match found → `[CACHED]` with tool + arguments
   - If no match → continue to classification

3. **ML Classification** (50-100ms)
   - Use lightweight DistilBERT model fine-tuned on query types
   - Features: query length, verb patterns, complexity indicators, tool keywords
   - Output probabilities for each route
   - If max probability > 0.80 → return classification
   - If max probability < 0.80 → default to `[PLANNER]` (safe fallback)

**Characteristics:**
- **Fast**: Total latency 100-200ms (acceptable overhead)
- **Conservative**: When uncertain, defaults to `[PLANNER]` to avoid incorrect simplification
- **Learning**: Improves over time as execution logs grow
- **Transparent**: Logs all classification decisions with confidence scores

### Agent A (Planner): Strategic Task Decomposer

**Role:** The Planner is the **same LLM** called by the orchestrator with a **planning-focused system prompt**. It understands the user's intent and generates an algorithmic plan based on available tools. It's invoked only for `[PLANNER]` route queries.

**Important**: Agent A is not a separate model or instance - it's the same LLM configured with the planner role via its system prompt.

**Core Principle: Computational Economy**

Agent A is **strictly bound to computational economy** - it must always prioritize:
- ⚡ **Speed**: Fastest execution path
- 🎯 **Efficiency**: Least number of steps/instructions
- 💾 **Resource Conservation**: Minimal CPU and memory usage

**Tool Selection Hierarchy (Most to Least Efficient):**

1. **Shell Commands with Pipelines** (PREFERRED for text manipulation and basic operations)
   - Examples:
     - Text processing: `grep | awk | sed | sort | uniq`
     - File operations: `find | xargs | wc`
     - Math calculations: `echo "scale=2; 5*3.14" | bc`
     - Data extraction: `cat file.txt | cut -d',' -f2 | tail -n 5`
   - **Why**: Native system tools, minimal overhead, built for efficiency
   - **When**: Text manipulation, filtering, sorting, basic math, file operations

2. **Filesystem Tools** (For direct file/directory operations)
   - Examples: list, read, write, move, copy
   - **Why**: Optimized for I/O operations
   - **When**: File management tasks

3. **Python Sandbox** (LAST RESORT - only when shell cannot accomplish the task)
   - Examples: Complex algorithms, data structures, advanced libraries
   - **Why**: Higher overhead (interpreter startup, memory allocation)
   - **When**: Complex logic, non-trivial calculations, data structures (JSON parsing, regex with capture groups, statistical analysis)

**Planning Constraints:**
- ❌ **AVOID**: Using Python sandbox for tasks shell can handle
- ❌ **AVOID**: Multiple steps when pipelines can do it in one
- ❌ **AVOID**: Storing intermediate results unless necessary
- ✅ **PREFER**: One-liner shell pipelines over multi-step plans
- ✅ **PREFER**: Built-in Unix tools over custom scripts
- ✅ **PREFER**: Streaming data through pipes over file I/O

**Example Scenarios:**

**Bad Plan (Inefficient):**
```json
{
  "steps": [
    {"action": "Read file", "tool": "filesystem"},
    {"action": "Parse data", "tool": "python_sandbox"},
    {"action": "Calculate sum", "tool": "python_sandbox"},
    {"action": "Sort results", "tool": "python_sandbox"}
  ]
}
```

**Good Plan (Efficient):**
```json
{
  "steps": [
    {"action": "Extract, sum, and sort data", "tool": "shell", "command": "cat data.txt | awk '{sum+=$2} END {print sum}' | sort -n"}
  ]
}
```

**Input:**
- User query
- Planner system prompt: "You are a strategic planner bound to computational economy..."
- Simple list of available tools (names only: shell, filesystem, curl, python_sandbox, etc.)
- System information (date, time, OS, etc.)
- Awareness of orchestrator and other agent roles
- Memory of previous planning interactions

**Output:**
Either one of the following is sent back to the orchestrator:
- Fixed structured JSON/JSONL (the algorithmic plan) including:
  - User intent
  - Sequence of high-level steps (minimized for efficiency). Each step includes:
    - Action to be taken
    - Tools to use (preferring shell for text/math operations)
    - Expected output
    - Rationale for tool choice (when not obvious)
- Request for web search (if additional information needed)
- Clarifying questions (if user query is ambiguous)

**Characteristics:**
- Executes nothing; only provides the strategic map
- Response is exclusively JSON/JSONL, no additional text
- One invocation per query (until plan completion or error)
- **Optimizes for minimal steps and maximal use of shell pipelines**
- **Considers resource efficiency as a primary planning constraint**

### Python Orchestrator: The Master Controller

**Role:** The orchestrator is the deterministic master controller that coordinates all system components. It owns the tools, manages memory, controls execution flow, and **invokes the same LLM in different roles** by changing system prompts and context.

**Key Insight**: The orchestrator doesn't have multiple separate LLM instances. It has **one LLM that it calls in three different roles**:
- **Agent A role**: Calls LLM with planning system prompt + tool list
- **Agent B role**: Calls LLM with execution system prompt + detailed tool schemas
- **Agent C role**: Calls LLM with chat system prompt + minimal context

**Responsibilities:**
1. Receive and log user query
2. Invoke The Router to classify query
3. Based on classification, execute route-specific workflow:
   - `[CHAT]`: Call Agent C (pure chat mode) → Format response → Display to user
   - `[CACHED]`: Retrieve and execute cached solution → Call Agent C (narrator mode) → Format response → Display to user
   - `[PLANNER]`: Call Agent A for plan → Loop: Call Agent B + execute tools → Call Agent C (summarizer mode) → Format response → Display to user
4. Validate all outputs (JSON format, tool availability, execution results)
5. Manage task stack and execution state
6. Handle errors with role-specific retry logic
7. Log all interactions, decisions, and results to SQLite
8. **Format and display all Agent C narratives to the terminal** (colors, progress indicators, layout)
9. Communicate progress to user in real-time during execution

**Critical Insight**: The orchestrator is both the **first touchpoint** (receives user query) and the **final touchpoint** (displays formatted output to terminal). Agent C always sits between execution and display as the conversational layer.

**Error Handling:**
- Invalid JSON from Agent A role: Re-invoke LLM in Agent A role with error feedback
- Invalid plan (unregistered tools): Re-invoke LLM in Agent A role to clarify
- Execution failure: Re-invoke LLM in Agent B role to correct, with retry limit
- Router misclassification: User can override route selection

**State Information - Extended Memory:**
- The orchestrator logs all interactions in a central SQLite database:
  - User queries and classifications
  - Router decisions and confidence scores
  - Plans, steps, tool calls, and results
  - Timestamps and execution state
  - Cache hits and intention patterns
- This is crucial for:
  - Debugging and auditing
  - Building context for each LLM role invocation
  - Intention caching and learning
  - Deterministic flow control 

### Agent B (Command Engineer): Precise Tool Executor

**Role:** The Command Engineer is the **same LLM** called by the orchestrator with an **execution-focused system prompt**. It generates precise and executable instructions for the orchestrator based on the current step from the algorithmic plan provided by Agent A. It's invoked repeatedly in the `[PLANNER]` route, once per plan step.

**Important**: Agent B is not a separate model or instance - it's the same LLM configured with the executor role via its system prompt.

**Input per turn:**
- User query (for context)
- Executor system prompt: "You are a precise tool executor that translates plan steps..."
- Complete algorithmic plan JSON/JSONL (to maintain strategic context)
- Current step/task to execute
- Outputs from previous steps (last 3 steps to avoid token overload)
- Detailed description of available tools with usage schemas
  - Example: `filesystem` with actions like 'list' and parameters like 'path', 'pattern'
- System information and awareness

**Output:**
- Natural and precise instruction in plain text
- Specifying exactly:
  - What tool/command to launch with parameters
  - In what order
  - What to capture and save

**Characteristics:**
- Doesn't invent; limits itself to provided tools
- Generates verifiable commands
- Multiple invocations per query (one per plan step)

### Agent C (Chat): Conversational Assistant and Universal Narrator

**Role:** Agent C is the **same LLM** called by the orchestrator with a **conversational system prompt**. It serves as the **universal narrator** for all routes - transforming raw data, execution results, or answering questions into natural conversational responses. **Every query cycle ends with Agent C** generating the narrative that the user will see.

**Important**: Agent C is not a separate model or instance - it's the same LLM configured with different conversational contexts via its system prompt depending on the route.

**Three Invocation Patterns:**

1. **Pure Chat Mode** (for `[CHAT]` route):
   - Handles simple informational queries that don't require tools
   - System prompt: "You are a helpful conversational assistant..."
   - Context: Last 10 chat interactions with timestamps
   - Output: Direct conversational response

2. **Narrator Mode** (for `[CACHED]` route):
   - Translates raw tool outputs into natural conversation
   - System prompt: "You are a narrator that translates tool outputs into natural conversation..."
   - Context: User's original query + raw tool output
   - Output: Narrative presentation of the results

3. **Summarizer Mode** (for `[PLANNER]` route):
   - Summarizes execution results from multi-step tasks
   - System prompt: "You are a task summarizer that explains what actions were taken..."
   - Context: User's original query + plan summary + execution results
   - Output: Conversational summary of what was accomplished

**Conversation Continuity:**

Agent C maintains conversational context through the orchestrator's memory management:
- **Last 10 chat interactions** are retrieved from SQLite and injected into the context
- **Each interaction includes timestamps**, allowing Agent C to infer:
  - If conversation was paused and for how long
  - Context awareness: "Welcome back! It's been 2 hours since we discussed Docker..."
  - Natural acknowledgment of time gaps between messages
- This enables natural multi-turn conversations
- Context persists **across work sessions** - if the user:
  1. Chats with Agent C
  2. Switches to complex tasks (Agent A/B)
  3. Returns to chat later
  - Agent C seamlessly continues the conversation with full memory of previous exchanges
- Conversation history is distinct from task execution history

**Input:**
- User query
- Chat system prompt: "You are a helpful conversational assistant..."
- **Last 10 chat interactions from `chat_history` table** (format: timestamp + user query → timestamp + agent response pairs)
- Minimal tool context (no tool schemas, no complex execution state)
- Basic system information (date, time) if relevant

**Output:**
- Natural language response
- Direct answer to user's question
- No tool calls or structured output
- Logged to `chat_history` table for future context

**Characteristics:**
- Fast and lightweight (minimal token usage in pure chat mode)
- No access to tools (conversational/narrative output only, no execution)
- **Universal narrator**: Invoked on ALL routes as the final step before orchestrator display
- Multiple invocation patterns depending on route (chat, narrator, summarizer)
- **Context-aware**: Remembers previous chat exchanges even after user works on tasks
- **Session-independent**: Chat context persists across terminal sessions

**Key Architectural Role:**
Agent C is the **mandatory conversational layer** between execution/data and the user. While the orchestrator controls the terminal interface and formatting, Agent C provides the conversational content that makes the terminal feel like a natural dialogue rather than raw command output.

**Examples of Chat-routed queries:**

**Single-turn:**
- "What is the capital of Japan?"
- "Explain recursion"
- "What does Docker do?"
- "How does HTTPS work?"
- "Define REST API"

**Multi-turn conversation:**
```
User: "What is Docker?"
Agent C: "Docker is a containerization platform..."

[User then executes shell tasks via Agent A/B for 30 minutes]

User: "How does it compare to VMs?"
Agent C: "Docker containers, which I explained earlier, differ from VMs in..."
          ↑ Remembers previous conversation about Docker
```


## Memory Management

### The Single Source of Truth

**Critical Principle**: This architecture has **ONE and ONLY ONE memory system** - the central SQLite database managed exclusively by the orchestrator. There are no separate memories, caches, or state stores. Everything flows through this single source of truth.

### Stateless LLM Problem

Large Language Models (LLMs) are **stateless**: each prompt is an isolated interaction with no inherent retention of previous state. 

**Critical Insight**: In this architecture, we use **one LLM in three different roles**. Each role invocation is stateless, which is why the orchestrator must reconstruct and inject appropriate context for each call from the **single unified memory**.

### Solution: Central SQLite Database / Orchestrator-Managed Memory

Memory doesn't reside in the LLM (regardless of role). The **orchestrator manages all persistence** through **ONE central SQLite database** - the sole source of truth for the entire system.

**Key Architectural Constraint**: 
- ✅ **ONE memory database** (SQLite)
- ✅ **ONE orchestrator** (owns and manages the memory)
- ✅ **ONE LLM** (called in different roles with context from the ONE memory)
- ❌ NO separate caches, logs, or state stores outside this database
- ❌ NO agent-specific memory systems
- ❌ NO distributed or fragmented state

#### Unified Table Structure

This **single database** contains all system state organized by operational concern (not by agent). The tables serve different purposes in the workflow:

**Orchestrator Tables (Flow Control & Routing):**
1. **`orchestrator_state`** - Current orchestration cycle state, active query ID, execution phase
2. **`router_decisions`** - Classification decisions, confidence scores, route taken per query

**Agent Role Interaction Tables:**
3. **`interactions`** - Universal log of ALL prompts and responses for **all three LLM roles** (A, B, C)
   - Includes: role used, system prompt, user query, LLM response, timestamps
   - Single table for all agents - no separate agent-specific tables

**Execution Context Tables (by Route Type):**
4. **`task_state`** - Algorithmic plans, execution stack, progress (for `[PLANNER]` route - Agent A/B workflows)
5. **`step_outputs`** - Detailed results per plan step (for `[PLANNER]` route - Agent B executions)
6. **`chat_history`** - Conversation exchanges with timestamps (for `[CHAT]` route - Agent C interactions)
7. **`intention_cache`** - Successful executions with query embeddings (for `[CACHED]` route - zero-LLM path)

**Key Design Insight**: 
- ❌ **NOT** organized as: "Agent A table", "Agent B table", "Agent C table"
- ✅ **IS** organized by: Orchestrator state, Universal interactions log, Route-specific contexts
- **Rationale**: Agents (A, B, C) are **roles of the same LLM**, not separate entities. They share the universal `interactions` table. Only their **operational contexts** differ (planning vs execution vs conversation), which is reflected in the route-specific tables.

**Important**: All tables reside in the **same SQLite database file**. This is not a collection of separate databases - it's **ONE unified memory** with different tables for different operational needs.

This unified structure allows the orchestrator to efficiently query and reconstruct context for each LLM role invocation without overwhelming the model with excessive data. Access patterns are optimized for quick retrieval of the most relevant information from the **single source of truth**.

#### Context Flow

**Before each LLM call (any role):**
1. Orchestrator determines which role to invoke (based on Router decision or execution state)
2. Orchestrator checks for **cross-route context handoff** needs:
   - If previous route was `[CHAT]` and current is `[PLANNER]` → Include recent chat context
   - If previous route was `[PLANNER]` and current is `[CHAT]` → Include task completion summary
   - This enables seamless conversational continuity across routes
3. Queries **the single SQLite database** to reconstruct role-specific context:
   - **Agent A (Planner)**: 
     - Tool list, previous planning attempts, user intent (from `interactions`, `task_state`)
     - **Cross-route context**: If transitioning from `[CHAT]`, include last 3 chat interactions for conversational continuity
   - **Agent B (Executor)**: 
     - Complete plan, current step, last 3 step outputs, detailed tool schemas (from `task_state`, `step_outputs`)
     - **Cross-route context**: If user query references chat context, include relevant chat history snippet
   - **Agent C (Chat)**: 
     - Last 10 chat interactions with timestamps (from `chat_history`)
     - **Cross-route context**: If previous route was `[PLANNER]`, include task summary for reference
4. Selects appropriate system prompt for the role
5. Injects context from **the unified memory** into the prompt (including cross-route context if applicable)
6. Calls the LLM with role-configured prompt

**Cross-Route Context Handoff Examples:**

**Example 1: Chat → Planner**
```
User: "What is the capital of Japan?"
Route: [CHAT] → Agent C responds: "Tokyo is the capital of Japan."

User: "What's the temperature there right now?"
Route: [PLANNER] (requires weather API)
Context for Agent A includes:
  - Last 3 chat interactions (including "What is the capital of Japan?" → "Tokyo...")
  - User query: "What's the temperature there right now?"
Agent A understands "there" = Tokyo from chat context
Plan: Use weather API for Tokyo temperature
```

**Example 2: Planner → Chat (Asking about execution results)**
```
User: "Analyze the logs and fix errors"
Route: [PLANNER] → Agent A/B execute task, fix 3 errors
Output: "Fixed 3 errors: null pointer exception in line 42, 
         connection timeout in db_connect(), parse error in config.json"

User: "Why did those errors happen?"
Route: [CHAT] (explanatory question, no tools needed)
Context for Agent C includes:
  - Last 10 chat interactions (if any)
  - Summary of most recent PLANNER execution:
    * Original query: "Analyze the logs and fix errors"
    * Plan executed: 4 steps
    * Results: "Fixed 3 errors: null pointer exception...(full details)"
    * Completion time: 2 minutes ago
Agent C can explain: "Those errors occurred because: 1) The null pointer 
exception happened when the code tried to access an uninitialized variable 
in line 42..."
```

**Example 3: Chat → Planner (Building on conversation context)**
```
User: "What's Docker?"
Route: [CHAT] → "Docker is a containerization platform..."

User: "What's the latest version?"
Route: [CHAT] → "Docker version 24.0 is the latest stable release..."

User: "Install it on my system"
Route: [PLANNER] (requires tools: package manager, system detection)
Context for Agent A includes:
  - Last 3 chat interactions about Docker
  - User query: "Install it on my system"
Agent A understands "it" = Docker from conversation
Plan: Detect OS → Check if Docker exists → Install Docker 24.0
Agent B response naturally references: "Installing Docker (which we 
discussed earlier)..."
```

**Important Design Decision**: 
- ❌ **NO need to modify Agent A/B/C system prompts** for cross-route context
- ✅ **Orchestrator handles context injection** transparently by:
  - Detecting route transitions in `router_decisions` table
  - Including relevant cross-route context in the prompt's context section
  - LLM naturally processes the additional context without prompt changes

**After each execution:**
1. Orchestrator logs the role invocation to **the single database**:
   - Which role was used (A, B, or C) → `interactions`
   - Input prompt and context (including any cross-route context) → `interactions`
   - LLM response → `interactions`
   - Execution results (if applicable) → `step_outputs`
   - Timestamps and latency metrics → across relevant tables
2. Updates relevant tables **in the same database**:
   - `task_state` if plan advanced
   - `intention_cache` if execution successful
   - `router_decisions` with outcome validation (including previous route)
   - `chat_history` with timestamped interaction
3. Maintains auditable and immutable trail **in the unified memory**

### Approach Advantages

- **Scalability**: SQLite is lightweight, local, and transactional
- **Speed**: Fast queries optimized for each route type from the **single database**
- **Recovery**: Possible in case of interruptions (entire state in **one place**)
- **Single Source of Truth**: All system state in **one database**, no synchronization issues
- **Role Clarity**: Single LLM but distinct roles with context from **unified memory**
- **Doesn't modify model**: Context from **the one memory** is the vehicle for "memory"
- **Total control**: Exclusively by the orchestrator over **the single database**
- **Learning**: Intention cache improves over time without model retraining
- **No state fragmentation**: Everything in **one place**, eliminating consistency issues

## Benefits and Performance Analysis

### Key Benefits

- **The Router**: Intelligently directs queries to the appropriate execution path, eliminating unnecessary overhead
- **Agent A (Planner role)**: Imposes order on complex tasks, avoiding disorganized executions
- **Agent B (Executor role)**: Prevents hallucinations by anchoring instructions in real tools
- **Agent C (Chat role)**: Provides fast, efficient responses for simple queries
- **Orchestrator**: Ensures safety, control, persistent memory, and coordinates all roles
- **Result**: Transforms ambiguous queries into verified actions while maintaining speed for simple queries

### Performance Impact

#### Query Distribution (estimated typical usage):
- **70-80% Simple queries** (`[CHAT]` route): "What is X?", "Explain Y"
- **10-15% Cached queries** (`[CACHED]` route): Repeated commands
- **10-15% Complex queries** (`[PLANNER]` route): Multi-step tasks

#### Latency Comparison

**Simple Query: "What is the capital of Japan?"**
- Without Router: Agent A (800ms) + Agent B (600ms) = 1400ms
- With Router: Router (100ms) + Agent C (500ms) + Display (negligible) = 600ms
- **Improvement: 57% faster**

**Cached Query: "Show command history"**
- Without Router: Agent A (800ms) + Agent B (600ms) = 1400ms
- With Router: Router (100ms) + Cache lookup (50ms) + Execute (200ms) + Agent C narrator (500ms) + Display (negligible) = 850ms
- **Improvement: 39% faster**
- **Note**: Agent C narration adds ~500ms but provides conversational UX

**Complex Query: "Analyze logs and fix issues"**
- Without Router: Agent A (800ms) + Agent B loop (3-5 calls × 600ms) = 2600-3800ms
- With Router: Router (100ms) + Agent A (800ms) + Agent B loop (3-5 calls × 600ms) + Agent C summarizer (500ms) + Display (negligible) = 3200-4300ms
- **Overhead: ~600ms total (Router + Agent C), adds conversational summary**

#### Cost Comparison

**Simple Query:**
- Without Router: 3500 tokens (Agent A + Agent B contexts)
- With Router: 200 tokens (Router + Agent C minimal context)
- **Savings: 94% token reduction**

**Cached Query:**
- Without Router: 3500 tokens
- With Router: 50 tokens (Router) + 300 tokens (Agent C narrator with raw output)
- **Savings: 90% token reduction**
- **Note**: Agent C narration adds minimal cost but provides conversational UX

**Complex Query:**
- Without Router: Agent A + Agent B loop (~4000-6000 tokens)
- With Router: Same token usage + ~50 tokens (Router) + ~400 tokens (Agent C summarizer)
- **Overhead: ~450 tokens (~8-11%), adds conversational summary**

#### Overall System Impact
Assuming 75% simple/cached, 25% complex queries:
- **Average latency reduction: 40-50%** (includes Agent C narration overhead)
- **Average cost reduction: 55-65%**
- **User experience: Dramatically improved** - all responses are conversational and natural, not raw data dumps
- **Trade-off**: Agent C narration adds 500ms and ~300-400 tokens per query, but transforms raw outputs into natural dialogue

## Summary: Architectural Principles

### Core Design Philosophy

1. **One LLM, Multiple Roles**
   - The system uses a **single LLM instance**
   - Different behaviors are achieved through **system prompts** and **context engineering**
   - No separate models or fine-tuning required

2. **Intelligent Routing First**
   - **The Router (Tiny Bird)** classifies every query before LLM invocation
   - Prevents unnecessary complexity for simple queries
   - Enables zero-LLM-call cached executions

3. **Role Specialization**
   - **Agent A (Planner)**: Strategic decomposition, algorithmic planning
   - **Agent B (Executor)**: Tactical execution, precise tool calling
   - **Agent C (Narrator)**: Universal conversational layer - transforms all outputs into natural dialogue
   - Each role has optimized prompts and context

4. **Orchestrator as Master Controller and Terminal Interface**
   - Owns all tools and execution capabilities
   - Manages all memory through SQLite
   - Coordinates all LLM invocations with appropriate roles
   - **Always invokes Agent C as the final step** to generate conversational responses
   - Formats and displays Agent C narratives to the terminal (colors, layout, progress)
   - Ensures deterministic, auditable behavior

5. **Performance Through Intelligence and Conversational UX**
   - 70-80% of queries avoid complex orchestration
   - Cached queries still require Agent C narration (~500ms) but gain conversational UX
   - Complex queries get full multi-agent treatment with conversational summaries
   - Result: 40-50% faster on average, 55-65% cheaper, and **100% conversational interface**

### Visual Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                         USER QUERY                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │  THE ROUTER (Tiny Bird)       │
         │  • Fast classification        │
         │  • Intention cache lookup     │
         │  • ML-based routing           │
         └──────────┬────────────────────┘
                    │
         ┌──────────┴──────────┬─────────────────┐
         │                     │                  │
         ▼                     ▼                  ▼
    [CHAT]               [CACHED]            [PLANNER]
         │                     │                  │
         ▼                     ▼                  ▼
┌─────────────────┐   ┌──────────────┐   ┌──────────────────┐
│ ORCHESTRATOR    │   │ ORCHESTRATOR │   │  ORCHESTRATOR    │
│ calls LLM in:   │   │ workflow:    │   │  workflow:       │
│                 │   │              │   │                  │
│ Agent C Role    │   │ Execute Tool │   │  Agent A Role    │
│ (Pure Chat)     │   │ (No LLM)     │   │  (Planner)       │
│                 │   │      ↓       │   │  ↓               │
│ ↓               │   │ Agent C Role │   │  Agent B Loop    │
│ Conversation    │   │ (Narrator)   │   │  (Executor)      │
│                 │   │      ↓       │   │  ↓               │
│                 │   │  Narrative   │   │  Agent C Role    │
│                 │   │              │   │  (Summarizer)    │
│                 │   │              │   │  ↓               │
│                 │   │              │   │  Summary         │
└────────┬────────┘   └──────┬───────┘   └────────┬─────────┘
         │                   │                     │
         └───────────────────┴─────────────────────┘
                             │
              ALL ROUTES END WITH AGENT C NARRATIVE
                             │
                             ▼
                  ┌─────────────────────┐
                  │   ORCHESTRATOR      │
                  │   Formats & Displays│
                  │   to Terminal       │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │    USER SEES        │
                  │  Conversational     │
                  │    Response         │
                  └─────────────────────┘
                             
                    ┌─────────────────┐
                    │  SQLite Memory  │
                    │  • Interactions │
                    │  • Router logs  │
                    │  • Task state   │
                    │  • Cache data   │
                    └─────────────────┘
```

### Key Takeaways

✅ **Single LLM Architecture**: One model, three roles via prompt engineering  
✅ **Smart Routing**: Eliminates unnecessary overhead for 70-80% of queries  
✅ **Agent C as Universal Narrator**: ALL routes end with conversational response generation  
✅ **Deterministic Control**: Python orchestrator ensures reliable execution  
✅ **Role-Based Context**: Each agent role receives optimized, focused context  
✅ **Persistent Memory**: SQLite database maintains all state and history  
✅ **Performance Gains**: 40-50% faster, 55-65% cheaper, with 100% conversational UX  
✅ **Orchestrator as Terminal Interface**: Formats and displays Agent C narratives to user

This architecture elegantly balances simplicity (one LLM) with sophistication (intelligent routing and role specialization) to achieve both high reliability for complex tasks and excellent performance for simple queries, **while maintaining a fully conversational user experience** where all outputs are natural language narratives rather than raw data.
