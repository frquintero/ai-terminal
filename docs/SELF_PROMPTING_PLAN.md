# Self-Prompting Agent
## LLM Generates Its Own Optimal Execution Prompt

---

## 📜 What We're Building

**One Thing**: Agent generates custom execution prompt for each query

**How**: LLM analyzes query + tool examples → writes its own prompt

**Why**: Fix sandbox file I/O misuse by including relevant patterns in prompts

---

## 🎯 The Problem

```python
# CURRENT (Static Prompt)
system_prompt = "Shell automation expert. Use tools for file I/O..."

User: "Read data.csv and create histogram"
Agent: df = pd.read_csv('data.csv')  # ❌ WRONG - file not found!
```

**Why it fails**: Static prompt doesn't mention `SANDBOX_PROJECT` pattern

---

## ✅ The Solution

```python
# NEW (Self-Generated Prompt)
User: "Read data.csv and create histogram"
    ↓
Agent discovers tool examples:
  run_python_sandbox.examples = [
    "pd.read_csv(os.path.join(os.environ['SANDBOX_PROJECT'], 'data.csv'))"
  ]
    ↓
Agent generates custom prompt:
  "Data analyst. Use run_python_sandbox.
   Access files via: os.environ['SANDBOX_PROJECT']
   Example: pd.read_csv(os.path.join(os.environ['SANDBOX_PROJECT'], 'data.csv'))"
    ↓
Agent executes with self-generated prompt:
  df = pd.read_csv(os.path.join(os.environ['SANDBOX_PROJECT'], 'data.csv'))
  # ✅ WORKS!
```

---

## 📊 User Gains

- 🚀 **Better sandbox usage**: Correct file I/O patterns
- 🧠 **Query-specific guidance**: Each query gets tailored prompt
- 📚 **Self-documenting**: Examples embedded in tool metadata
- 🎯 **Focused prompts**: Only relevant guidance included

---

## 🔄 How It Works

### Simple Chat
```
"Hello" → Short prompt: "Conversational assistant"
         → Quick response, no tool examples needed
```

### Shell Command
```
"List files" → Prompt: "Shell assistant. Use run_command for shell operations"
              → Focused on shell tools
```

### Data Analysis (The Critical Case)
```
"Plot data.csv" → Discovers sandbox has file I/O examples
                → Generates: "Data analyst. Use run_python_sandbox.
                              Access: os.environ['SANDBOX_PROJECT']
                              Example: pd.read_csv(os.path.join(...))"
                → Agent sees pattern, uses it correctly ✅
```

---

## 📋 Implementation Plan

## Phase 1: Add Tool Examples [2-3h]

### Task 1.1: Add Examples to Tools ⏱️ 2h

**File**: `tools.py`

Add to `BaseTool`:
```python
class BaseTool(ABC):
    # ... existing methods ...
    
    @property
    def usage_examples(self) -> Optional[List[str]]:
        """Usage examples for this tool"""
        return None
```

Implement for `RunPythonSandboxTool`:
```python
@property
def usage_examples(self) -> List[str]:
    return [
        """# Reading project CSV
import os
import pandas as pd
project_dir = os.environ['SANDBOX_PROJECT']
df = pd.read_csv(os.path.join(project_dir, 'data.csv'))""",
        
        """# Creating plot (auto-saves)
import matplotlib.pyplot as plt
plt.plot([1, 2, 3])
# Automatically saved to artifacts/plot_1.png""",
        
        """# Writing results to project
import os
project_dir = os.environ['SANDBOX_PROJECT']
with open(os.path.join(project_dir, 'output.txt'), 'w') as f:
    f.write('Results')"""
    ]
```

Add minimal examples to:
- `run_command`: Common patterns (ls, grep, find)
- `run_interactive`: Launching vim, top, etc.
- `write_file`: File path examples

**Success Criteria**:
- [ ] `usage_examples` property added to BaseTool
- [ ] RunPythonSandboxTool has 3 file I/O examples
- [ ] 2-3 other tools have basic examples

---

### Task 1.2: Build Tool Catalog ⏱️ 30min

**File**: `agent.py`

```python
def _build_tool_catalog(self) -> dict:
    """Build tool catalog with examples"""
    catalog = []
    
    for tool in TOOLS.values():
        tool_info = {
            "name": tool.name,
            "description": tool.description
        }
        
        # Include examples if available
        if tool.usage_examples:
            tool_info["examples"] = tool.usage_examples
        
        catalog.append(tool_info)
    
    return {"tools": catalog}

def __init__(self):
    # ... existing init ...
    
    # Build catalog once per session
    self.tool_catalog = self._build_tool_catalog()
```

**Success Criteria**:
- [ ] Catalog built once on init
- [ ] Includes all tools with examples
- [ ] JSON-serializable

---

## Phase 2: Self-Prompting System [3-4h]

### Task 2.1: Implement Prompt Generator ⏱️ 2h

**File**: `agent.py`

```python
def _generate_execution_prompt(self, user_query: str) -> str:
    """LLM generates optimal execution prompt for this query"""
    
    # Truncate examples if catalog is too large
    catalog_str = json.dumps(self.tool_catalog, indent=2)
    if len(catalog_str) > 4000:
        # Simplified catalog without examples for meta-prompt
        simple_catalog = {
            "tools": [
                {"name": t.name, "description": t.description}
                for t in TOOLS.values()
            ]
        }
        catalog_str = json.dumps(simple_catalog, indent=2)
    
    meta_prompt = f"""You are a meta-prompt generator for an AI assistant.

USER QUERY:
{user_query}

AVAILABLE TOOLS (with usage examples):
{catalog_str}

YOUR TASK:
Analyze the query and generate the optimal system prompt for executing it effectively.

You decide:
- What role/identity is best for this task
- Which tools (if any) to reference
- What patterns or examples to include
- How detailed or concise the prompt should be

Trust your judgment. Generate whatever prompt will produce the best result. Just be as concise as possible while still being clear and effective.

Return JSON:
{{
  "system_prompt": "Your complete generated prompt"
}}"""
    
    try:
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": "Meta-prompt generator. Return only JSON."},
                {"role": "user", "content": meta_prompt}
            ],
            temperature=0.2,  # Low creativity, focused
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        self._log("GENERATED_PROMPT", json.dumps(result))
        
        return result["system_prompt"]
        
    except Exception as e:
        # Fallback to minimal prompt
        self._log("PROMPT_GEN_ERROR", str(e))
        return "Shell automation expert and conversational assistant."
```

**Success Criteria**:
- [ ] Returns valid JSON with "system_prompt" field
- [ ] <500ms overhead
- [ ] Fallback works on errors (returns base prompt)
- [ ] Generated prompts lead to successful task execution

---

### Task 2.2: Integrate into Main Loop ⏱️ 1h

**File**: `agent.py`

```python
def process_input(self, user_input: str, max_steps: int = None):
    """Process with self-generated prompts"""
    
    ui.start_timer()
    self._current_step_tool_outputs = []
    
    # SELF-PROMPTING: Generate optimal prompt for this query
    custom_prompt = self._generate_execution_prompt(user_input)
    
    # Append system context if available
    if hasattr(self, 'system_context'):
        full_prompt = f"{custom_prompt}\n\n{self.system_context}"
    else:
        full_prompt = custom_prompt
    
    # Update system message
    self.message_history[0]["content"] = full_prompt
    
    # Log
    self._log("DYNAMIC_PROMPT", json.dumps({
        "length": len(full_prompt),
        "query_preview": user_input[:100]
    }))
    
    # Continue normal flow
    self.message_history.append({"role": "user", "content": user_input})
    self._log("USER_INPUT", user_input)
    
    # ... rest of existing process_input logic unchanged ...
```

**Success Criteria**:
- [ ] Prompt generated before each LLM call
- [ ] No breaking changes
- [ ] Logging works
- [ ] Fallback on errors

---

### Task 2.3: Cleanup Static Prompt ⏱️ 30min

**File**: `agent.py`

```python
def _build_system_prompt(self, system_context: str) -> str:
    """Simplified - just store context, prompt will be generated per query"""
    # Store context for later appending
    return system_context  # No tool lists, no static instructions

def __init__(self):
    # ... existing ...
    
    system_info = get_system_info()
    system_context = format_system_info(system_info)
    
    # Store context separately
    self.system_context = system_context
    
    # Build tool catalog
    self.tool_catalog = self._build_tool_catalog()
    
    # Minimal initial system message (will be replaced per query)
    self.message_history = [
        {"role": "system", "content": "AI assistant."}
    ]
```

**Success Criteria**:
- [ ] Static prompt simplified
- [ ] System context preserved
- [ ] Tool catalog built on init

---

## Phase 3: Testing [2h]

### Task 3.1: Unit Tests ⏱️ 1h

**File**: `tests/test_self_prompting.py` (new)

```python
def test_tool_catalog_has_examples():
    """Verify catalog includes examples"""
    agent = MiniAgent()
    sandbox = next(t for t in agent.tool_catalog["tools"] if t["name"] == "run_python_sandbox")
    assert "examples" in sandbox
    assert any("SANDBOX_PROJECT" in ex for ex in sandbox["examples"])

def test_data_query_prompt():
    """Data query should include sandbox pattern"""
    agent = MiniAgent()
    prompt = agent._generate_execution_prompt("Read data.csv and plot")
    assert "SANDBOX_PROJECT" in prompt or "sandbox" in prompt.lower()

def test_simple_query_prompt():
    """Simple query should get minimal prompt"""
    agent = MiniAgent()
    prompt = agent._generate_execution_prompt("Hello")
    assert len(prompt) < 500

def test_fallback_on_error():
    """Graceful fallback if prompt generation fails"""
    agent = MiniAgent()
    agent.client = None  # Break it
    prompt = agent._generate_execution_prompt("test")
    assert len(prompt) > 0  # Should return fallback
```

**Success Criteria**:
- [ ] All tests pass
- [ ] Sandbox examples present in catalog
- [ ] Prompts appropriate for query type

---

### Task 3.2: Regression Testing ⏱️ 30min

**Must not break**:
- [ ] Simple conversational queries
- [ ] File read/write
- [ ] Shell commands
- [ ] Sandbox execution
- [ ] Interactive tools
- [ ] Multi-turn conversations
- [ ] All existing tests pass

---

### Task 3.3: Manual Validation ⏱️ 30min

**Test scenarios**:

1. **Sandbox usage (critical)**:
   - Query: "Read test.csv and create a histogram"
   - Verify: Generated prompt includes SANDBOX_PROJECT pattern
   - Verify: Agent uses correct file I/O in generated code

2. **Simple chat**:
   - Query: "Hello, how are you?"
   - Verify: Short, simple prompt
   - Verify: Quick response

3. **Shell operation**:
   - Query: "Find all Python files"
   - Verify: Prompt mentions shell tools
   - Verify: Correct command execution

**Success Criteria**:
- [ ] Sandbox queries include file I/O patterns
- [ ] Simple queries get minimal prompts
- [ ] No regressions in functionality

---

## 📚 Documentation [30min]

### Task 4.1: Document Feature

**Files**:
- [ ] `docs/self_prompting.md` - How it works, examples
- [ ] Update `README.md` - Mention self-prompting feature
- [ ] Add to `AGENTS.md` if exists

**Content**:
- Architecture overview
- How tool examples work
- Example generated prompts
- Troubleshooting

---

## 📊 Success Metrics

### Quantitative
- **Sandbox accuracy**: 90%+ data queries use SANDBOX_PROJECT correctly
- **Prompt size**: 30-50% smaller for simple queries
- **Performance**: <500ms prompt generation overhead
- **No regressions**: All existing tests pass

### Qualitative
- **Better sandbox usage**: File I/O patterns used correctly
- **Query-appropriate**: Different prompts for different query types
- **Self-documenting**: Examples accessible in tool metadata

---

## ⚠️ Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Prompt generation fails | Work with the team to debug and improve |
| Generated prompts suboptimal | Logging for analysis, iterative tuning |
| Performance overhead | <500ms target, async potential |
| Breaking changes | Comprehensive regression suite |

---

## 🚀 Rollout Plan

**Week 1**: Phase 1 (Tool examples + catalog)  
**Week 2**: Phase 2 (Self-prompting system)  
**Week 3**: Phase 3 (Testing + docs)

**Total: 7-9 hours over 3 weeks**

---

## ✅ Approval Checklist

- [ ] All phases completed
- [ ] All tests pass
- [ ] Sandbox file I/O works correctly
- [ ] Performance acceptable (<500ms overhead)
- [ ] Documentation complete
- [ ] No regressions
- [ ] Approved by: _______________

---

## 💰 Cost/Benefit Analysis

**Costs**:
- ~400-600 tokens per request (prompt generation call)
- ~300-500ms latency per request
- 7-9 hours development effort

**Benefits**:
- Correct sandbox file I/O usage ✅
- Query-specific guidance ✅
- Cleaner, more maintainable prompts ✅
- Foundation for future improvements ✅

**Worth it?** YES - Fixes core sandbox problem with minimal complexity

---

**Philosophy**: Simple, focused, effective  
**Goal**: Fix sandbox usage through smart, query-specific prompting  
**Scope**: Just self-prompting - no MCP server, no external integrations
