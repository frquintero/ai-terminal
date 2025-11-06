# Visual Guide: Enhanced get_context Architecture

## Current vs Proposed

```
CURRENT STATE
=============

Agent Decision Making
        ↓
    "What should I do?"
        ↓
    [ LIMITED CONTEXT ]
        ├─ working_dir: "..."
        ├─ shell_cwd: "..."
        └─ recent_writes: [...]
        ↓
    Decision based on partial info
    Result: Often fails or inefficient


PROPOSED STATE
==============

Agent Decision Making
        ↓
    "What can I do?"
        ↓
    [ RICH CONTEXT via get_context() ]
        ├─ Tools Available & Constraints
        │  ├─ Sandbox memory limit
        │  ├─ Timeout configuration
        │  └─ Isolation status
        ├─ Environment
        │  ├─ Python version
        │  ├─ Available interpreters
        │  └─ Package managers
        ├─ Repository
        │  ├─ Current branch
        │  ├─ Uncommitted changes
        │  └─ Repo status
        ├─ System Resources
        │  ├─ CPU cores
        │  ├─ Memory available
        │  └─ Disk space
        └─ Recent Activity
           ├─ Last command exit code
           ├─ Recent command history
           └─ Last error (if any)
        ↓
    Smart decision based on full context
    Result: Works efficiently and safely
```

---

## Information Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent.process_input()                  │
│                   (User asks a question)                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ├─ "I need to know what I can do"
                         │
                         ↓
    ┌────────────────────────────────────────────────────┐
    │  Agent calls: get_context()                        │
    │                                                    │
    │  Returns: {                                        │
    │    tools: { available, sandboxed, isolation },    │
    │    environment: { python, shell, locale },        │
    │    repository: { branch, changes, origin },       │
    │    system: { cpu, memory, disk },                 │
    │    activity: { last_code, history },             │
    │    capabilities: { interpreters, managers }       │
    │  }                                                │
    └────────────────────┬───────────────────────────────┘
                         │
                    Agent reads context
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ↓                ↓                ↓
    "I can use   "Memory is 512MB  "Python and
     these       so use chunks"    Node available"
     tools"                         - pick Python
        │                │                │
        └────────────────┼────────────────┘
                         │
                    Smart Decision
                         │
                    Execute Tool(s)
                         │
                    Return Result
```

---

## Data Flow from System to Agent

```
System Information Collection
==============================

┌──────────────────────────┐
│  System Boot             │
│  (utils/system_info.py)  │
└────────────┬─────────────┘
             │
    ┌────────┴────────┬──────────────┬──────────────┐
    │                 │              │              │
    ↓                 ↓              ↓              ↓
┌─────────────┐  ┌────────────┐  ┌──────────┐  ┌─────────┐
│ OS/Kernel   │  │ CPU/Memory │  │ Disk     │  │ Git     │
│ Platform    │  │ Resources  │  │ Status   │  │ Context │
│ Distro      │  │ Available  │  │ Usage    │  │ Branch  │
└─────────────┘  └────────────┘  └──────────┘  └─────────┘
    │                 │              │              │
    └────────────────┬┴──────────────┴──────────────┘
                     │
        Cached in memory for session
                     │
                     ↓
    ┌───────────────────────────────────┐
    │  Agent calls get_context()        │
    │  (tools.py > GetContextTool)      │
    └────────────┬──────────────────────┘
                 │
        ┌────────┴──────────┐
        │                   │
        ↓                   ↓
    Retrieve from      Gather real-time
    cache (fast)       data (git, tools)
        │                   │
        └────────────┬──────┘
                     │
        ┌────────────┴──────────────┐
        │  Format as JSON           │
        │  - tools.available        │
        │  - repository.*           │
        │  - system.*               │
        │  - capabilities.*         │
        └────────────┬──────────────┘
                     │
                     ↓
            Return to Agent
                     │
            Agent makes decision
                     │
                Execute tool(s)
```

---

## Context Decision Tree

```
Agent receives task
    │
    ├─ Call get_context() → Get rich environment info
    │
    ├─ Decision: "Use Python?"
    │  ├─ Check: capabilities.interpreters_available.python3?
    │  ├─ YES → Use Python
    │  └─ NO  → Use alternative or fail gracefully
    │
    ├─ Decision: "Run heavy computation?"
    │  ├─ Check: system.memory_available_mb >= 500?
    │  ├─ YES & sandbox.enabled?
    │  │  └─ Check: max_memory_mb >= needed?
    │  │     ├─ YES → Run in sandbox
    │  │     └─ NO  → Break into chunks
    │  └─ NO → Plan smaller batches
    │
    ├─ Decision: "Modify code?"
    │  ├─ Check: repository.in_git_repo?
    │  ├─ YES → Check: branch != "main"?
    │  │  ├─ YES → Safe to modify
    │  │  └─ NO  → Create feature branch first
    │  └─ NO  → Proceed safely
    │
    ├─ Decision: "Install package?"
    │  ├─ Check: capabilities.package_managers
    │  ├─ "pip" in list?
    │  │  ├─ YES → Use pip
    │  │  └─ NO  → Check apt, brew, etc.
    │  └─ None available? → Warn user
    │
    └─ Decision: "Was last command successful?"
       ├─ Check: activity.last_command_exit_code == 0?
       ├─ YES → Continue with next step
       └─ NO  → Investigate error, retry, or skip
```

---

## Tool Status Visualization

```
Current Tool State (from get_context)
=====================================

┌─────────────────────────────────────────────────┐
│ AVAILABLE TOOLS                                 │
├─────────────────────────────────────────────────┤
│                                                 │
│  ✅ read_file                                  │
│  ✅ write_file                                 │
│  ✅ run_command                                │
│  ✅ run_interactive                            │
│  ✅ run_python_sandbox                         │
│  ✅ get_context                                │
│  ⚠️  run_sudo_command  (sudo not available)    │
│                                                 │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ SANDBOX CONFIGURATION                           │
├─────────────────────────────────────────────────┤
│                                                 │
│  Enabled:           YES                         │
│  Timeout:           30 seconds                  │
│  Max Memory:        1024 MB                     │
│  Max CPU:           20 seconds                  │
│  Network Disabled:  YES                         │
│  Write Protected:   NO                          │
│                                                 │
│  ✅ Safe to run sandboxed code                 │
│  ⚠️  Network operations will fail               │
│  ⚠️  Use chunks for >1GB data                   │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## Resource Awareness

```
Agent Response to Resource Constraints
======================================

SCENARIO 1: Plenty of Memory
────────────────────────────
get_context.system.memory_available_mb = 8192

Agent: "I have 8GB available, can load large files"
Action: Load full dataset into memory
Result: ✅ Fast processing

SCENARIO 2: Limited Memory
──────────────────────────
get_context.tools.sandboxed.max_memory_mb = 512

Agent: "I only have 512MB in sandbox"
Action: Use chunked reading (chunk_size=10000)
Result: ✅ Works with appropriate strategy

SCENARIO 3: Timeout Constraint
───────────────────────────────
get_context.tools.sandboxed.timeout_seconds = 10

Agent: "Only 10 seconds available"
Action: Break into fast subtasks, avoid long loops
Result: ✅ Completes before timeout

SCENARIO 4: No Constraints
──────────────────────────
Agent: "Full system available"
Action: Optimal algorithm without limits
Result: ✅ Best performance
```

---

## Agent Intelligence Progression

```
Without get_context
===================

Agent Strategy: Guess and Hope
   │
   ├─ Try to load entire file
   ├─ → OutOfMemoryError
   ├─ Try again with same approach
   ├─ → OutOfMemoryError again
   └─ Give up or retry endlessly

Result: ❌ FAILURE


With get_context
================

Agent Strategy: Check First, Then Act
   │
   ├─ Check memory available via get_context()
   ├─ See: max_memory_mb = 512
   ├─ Plan: Use chunked processing
   ├─ Load data in 50K-row chunks
   ├─ Process iteratively
   └─ Complete successfully

Result: ✅ SUCCESS with appropriate strategy
```

---

## Context Refresh Timeline

```
Session Lifecycle
=================

┌──────────────┐
│ Agent Start  │
└──────┬───────┘
       │
       ├─ Call get_context() → Gather all context
       │  (cpu_info, memory, git status, tools)
       │
       ├─ Cache result (reuse for 5-10 min)
       │
       └─ Make first decision
          └─ Check: tools.available
             └─ Check: repository.branch
                └─ Check: system.memory_available_mb
                   └─ Make smart decision ✅
                      └─ Execute
                         │
                         ├─ Each command:
                         │  └─ ShellIntegration tracks exit_code
                         │
                         ├─ User asks again?
                         │  └─ Call get_context()
                         │     └─ Get latest: exit_code, git status
                         │        └─ Understand previous outcome
                         │           └─ Make informed next decision ✅
                         │
                         └─ Session end
```

---

## Information Hierarchy

```
get_context() JSON Structure
=============================

HIGH PRIORITY (Agent checks first)
──────────────────────────────────
├─ tools.available          ← Can I use this?
├─ tools.sandboxed          ← What are the limits?
├─ activity.last_command_exit_code  ← Did it work?
└─ capabilities.interpreters_available ← What language?

MEDIUM PRIORITY (Agent checks for decisions)
─────────────────────────────────────────────
├─ repository.branch        ← Safe to modify?
├─ system.memory_available_mb ← How to size work?
└─ capabilities.package_managers ← How to install?

LOW PRIORITY (Agent uses for context/logging)
──────────────────────────────────────────────
├─ system.os, kernel        ← For debugging
├─ activity.recent_writes   ← What did I create?
└─ tools.isolation.enabled  ← Reproducibility?
```

---

## Example Agent Dialogue with Context

```
USER: "Analyze this 2GB CSV file"

AGENT THINKS:
1. Call get_context() → Get current state
2. See: memory_available_mb = 512, sandbox.enabled = true
3. Think: "I can't load 2GB into 512MB memory"
4. Check: capabilities.interpreters_available
5. See: python3 available
6. Plan: "Use pandas.read_csv(chunksize=50000)"
7. Execute: run_python_sandbox(script_with_chunking)
8. Check: activity.last_command_exit_code = 0 ✅
9. Report: "Analysis complete, saved results"

RESULT: ✅ SUCCESS

---

USER: "What interpreters do I have?"

AGENT THINKS:
1. Call get_context() → Get capabilities
2. Read: interpreters_available
3. See: python3, node, bash available; ruby unavailable
4. Report: "You have Python 3, Node.js, Bash. No Ruby."

RESULT: ✅ USEFUL INFO

---

USER: "Push my changes to main"

AGENT THINKS:
1. Call get_context() → Get repository state
2. Read: branch = "feature/kimi2-agent-support"
3. Think: "Not on main, that's good"
4. Check: uncommitted_changes_count = 0
5. Think: "No uncommitted changes, safe to switch"
6. Suggest: "Create pull request to main" (not direct push)

RESULT: ✅ SAFETY PRESERVED
```

---

## Integration Points

```
Where get_context() Feeds Into Agent
====================================

System Prompt
    ↓
    ├─ "Here's what tools are available"
    │  └─ from get_context.tools.available
    │
    ├─ "Here's the resource limits"
    │  └─ from get_context.tools.sandboxed
    │
    └─ "Here's what you should know"
       └─ from get_context.*

Agent Decision Loop
    ├─ Start: User input
    ├─ Check: get_context() for current state
    ├─ Plan: Use context to decide tools/approach
    ├─ Execute: Run tools
    ├─ Track: Update activity in ShellIntegration
    ├─ Loop: Each iteration calls get_context()
    └─ End: Return result

Tool Execution
    ├─ Before: Check capability in get_context()
    ├─ During: Tool runs (shellIntegration.run_command)
    ├─ After: Exit code tracked automatically
    └─ Next call: get_context() sees new exit_code
```

---

## Success Indicators

```
Agent with Enhanced get_context
================================

✅ Avoids resource errors
   └─ Checks memory before loading data
   └─ Respects timeouts
   └─ Sizes work appropriately

✅ Makes context-aware decisions
   └─ Knows git branch before modifying
   └─ Picks right language interpreter
   └─ Knows which tools available

✅ Understands results
   └─ Checks exit codes
   └─ Understands what just happened
   └─ Debugs failures intelligently

✅ Works reliably
   └─ Fewer OutOfMemoryErrors
   └─ Fewer timeout failures
   └─ Faster recovery from errors

✅ Gives better feedback
   └─ "Using Python (Node not available)"
   └─ "Processing in chunks (limited memory)"
   └─ "Last command failed, trying alternative"
```

---

**These diagrams show how enhanced context transforms agent capabilities from "guess and hope" to "plan and execute intelligently".**
