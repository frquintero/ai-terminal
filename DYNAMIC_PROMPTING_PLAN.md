# Dynamic Prompting System - Implementation Plan
## MCP-Inspired Self-Directed Architecture

## 🎯 Core Philosophy
**Trust the agent. Give it good tools, clear discovery, and let it decide what guidance it needs.**

Principles:
- ✅ **Discoverability**: Tools expose usage patterns and guidance as metadata
- ✅ **Self-direction**: LLM plans its approach and selects needed templates  
- ✅ **Composability**: Minimal prompt templates, dynamically assembled
- ✅ **Trust over guards**: Well-designed tools + clear prompts, no defensive heuristics
- ✅ **Observability**: Log what was selected and why

## 📐 Architecture

### Current State
```
Static Monolithic Prompt → User Query → LLM → Tools → Response
```

### Target State
```
User Query
    ↓
[DISCOVERY] Tool catalog exposed (MCP-style)
    ↓
[PLANNING] LLM analyzes query → selects tools + prompt templates (JSON)
    ↓
[ASSEMBLY] Compose system prompt from selected templates
    ↓
[EXECUTION] LLM executes with self-selected guidance
```

---

## 📋 Implementation Tasks

### Phase 1: Tool Discovery (MCP-Style) [2h]

#### Task 1.1: Enhance BaseTool with Discovery Metadata ⏱️ 1h
**File**: `tools.py`

Add optional discovery properties to `BaseTool`:

```python
class BaseTool(ABC):
    # ... existing abstract methods ...
    
    @property
    def usage_examples(self) -> Optional[List[dict]]:
        """Optional: Return usage examples for discovery"""
        return None
    
    @property  
    def prompt_guidance(self) -> Optional[str]:
        """Optional: Return guidance for LLM on when/how to use this tool"""
        return None
```

**Success Criteria**:
- [ ] BaseTool has optional discovery properties
- [ ] No breaking changes to existing tools
- [ ] Properties return None by default

---

#### Task 1.2: Implement Discovery for RunPythonSandboxTool ⏱️ 45min
**File**: `tools.py` (RunPythonSandboxTool class)

```python
@property
def usage_examples(self) -> List[dict]:
    return [
        {
            "scenario": "Reading project data file",
            "code": "import os\nimport pandas as pd\ndf = pd.read_csv(os.path.join(os.environ['SANDBOX_PROJECT'], 'data.csv'))"
        },
        {
            "scenario": "Saving plot",
            "code": "import matplotlib.pyplot as plt\nplt.plot([1,2,3])\n# Automatically saved to artifacts/"
        },
        {
            "scenario": "File I/O pattern",
            "code": "project_dir = os.environ['SANDBOX_PROJECT']\nwith open(os.path.join(project_dir, 'file.txt')) as f:\n    data = f.read()"
        }
    ]

@property
def prompt_guidance(self) -> str:
    return "Sandboxed Python execution. Access project files via os.environ['SANDBOX_PROJECT']. Plots auto-save to artifacts."
```

**Success Criteria**:
- [ ] Clear file I/O examples using SANDBOX_PROJECT
- [ ] Guidance is descriptive, not prescriptive
- [ ] Examples are copy-pasteable patterns

---

#### Task 1.3: Implement Discovery for Other Tools ⏱️ 15min
**File**: `tools.py`

Add minimal `prompt_guidance` for key tools (1-2 sentences each):

```python
# RunCommandTool
@property
def prompt_guidance(self) -> str:
    return "Execute non-interactive shell commands. For vim/nano/top use run_interactive instead."

# RunInteractiveTool  
@property
def prompt_guidance(self) -> str:
    return "Launch interactive programs (vim, nano, htop, etc). Output streams to user automatically."

# WikipediaSearchTool
@property
def prompt_guidance(self) -> str:
    return "Search Wikipedia for factual information, definitions, and general knowledge."
```

**Success Criteria**:
- [ ] 4-6 tools have minimal guidance
- [ ] No defensive language (no "never/always")
- [ ] Descriptive only

---

### Phase 2: Prompt Template Library [1h]

#### Task 2.1: Define Minimal Prompt Templates ⏱️ 30min
**File**: `agent.py` (module level or class level)

```python
PROMPT_TEMPLATES = {
    "base": "Shell automation expert and conversational assistant. Use tools for file I/O, commands, and external info. Respond directly for conversation.",
    
    "python_sandbox": """Python sandbox available (run_python_sandbox):
- Isolated execution with resource limits
- Access project files: os.environ['SANDBOX_PROJECT']
- Plots auto-save to artifacts/""",
    
    "shell_ops": """Shell tools available:
- run_command: non-interactive commands
- run_interactive: vim, top, htop, etc.
- run_sudo_command: privileged operations""",
    
    "external_knowledge": "Wikipedia search available for factual queries",
}
```

**Success Criteria**:
- [ ] 3-4 minimal templates defined
- [ ] No guards, rules, or "never" statements
- [ ] Total <400 chars for all templates
- [ ] Descriptive, trust-based language

---

#### Task 2.2: Build Tool Catalog Generator ⏱️ 30min
**File**: `agent.py`

```python
def _build_tool_catalog(self) -> dict:
    """Generate MCP-style tool discovery catalog"""
    catalog = {"tools": []}
    
    for tool in TOOLS.values():
        tool_info = {
            "name": tool.name,
            "description": tool.description,
        }
        
        # Include discovery metadata if available
        examples = getattr(tool, "usage_examples", None)
        if examples:
            tool_info["examples"] = examples
            
        guidance = getattr(tool, "prompt_guidance", None)
        if guidance:
            tool_info["guidance"] = guidance
        
        catalog["tools"].append(tool_info)
    
    return catalog
```

**Success Criteria**:
- [ ] Catalog includes all tools
- [ ] Discovery metadata included when available  
- [ ] Clean JSON structure
- [ ] No errors if tools lack metadata

---

### Phase 3: Planning Phase [2.5h]

#### Task 3.1: Implement Planning Call ⏱️ 1.5h
**File**: `agent.py`

```python
def _plan_execution(self, user_query: str) -> dict:
    """LLM plans approach and selects needed prompt templates"""
    
    tool_catalog = self._build_tool_catalog()
    available_templates = list(PROMPT_TEMPLATES.keys())
    
    planning_prompt = f"""Analyze this query and plan your approach.

USER QUERY:
{user_query}

AVAILABLE TOOLS & GUIDANCE:
{json.dumps(tool_catalog, indent=2)}

AVAILABLE PROMPT TEMPLATES:
{available_templates}

Return JSON with your execution plan:
{{
  "approach": "brief description of how you'll solve this",
  "primary_tools": ["tool1", "tool2"],
  "needed_templates": ["template1", "template2"],
  "reasoning": "why you chose these tools/templates"
}}"""
    
    try:
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": "Task planner. Analyze queries and select appropriate tools and guidance templates. Return only valid JSON."},
                {"role": "user", "content": planning_prompt}
            ],
            temperature=0.1,  # Mostly deterministic
            max_tokens=300,
            response_format={"type": "json_object"}
        )
        
        plan = json.loads(response.choices[0].message.content)
        self._log("EXECUTION_PLAN", json.dumps(plan))
        return plan
        
    except Exception as e:
        # Fallback: use base template only
        self._log("PLANNING_ERROR", str(e))
        return {
            "approach": "fallback to base guidance",
            "primary_tools": [],
            "needed_templates": ["base"],
            "reasoning": f"planning failed: {e}"
        }
```

**Success Criteria**:
- [ ] Planning call returns valid JSON
- [ ] Includes approach, tools, templates, reasoning
- [ ] <500ms latency
- [ ] Graceful fallback on errors
- [ ] Logged for debugging

---

#### Task 3.2: Implement Prompt Assembly ⏱️ 30min
**File**: `agent.py`

```python
def _assemble_prompt(self, plan: dict) -> str:
    """Compose system prompt from plan-selected templates"""
    
    # Always include base
    needed = set(plan.get("needed_templates", []))
    needed.add("base")
    
    # Assemble in deterministic order
    parts = []
    template_order = ["base", "python_sandbox", "shell_ops", "external_knowledge"]
    
    for template_key in template_order:
        if template_key in needed and template_key in PROMPT_TEMPLATES:
            parts.append(PROMPT_TEMPLATES[template_key])
    
    # Add system context
    if hasattr(self, 'system_context'):
        parts.append(self.system_context)
    
    return "\n\n".join(parts)
```

**Success Criteria**:
- [ ] Composes prompt from selected templates
- [ ] Deterministic template ordering
- [ ] Always includes base
- [ ] Includes system_context
- [ ] Clean formatting

---

#### Task 3.3: Integration into Main Loop ⏱️ 30min
**File**: `agent.py` (process_input method)

```python
def process_input(self, user_input: str, max_steps: int = None):
    """Process user input with dynamic prompting"""
    
    ui.start_timer()
    self._current_step_tool_outputs = []
    
    # PLANNING PHASE: Let LLM plan its approach
    plan = self._plan_execution(user_input)
    
    # ASSEMBLY PHASE: Build prompt from plan
    dynamic_prompt = self._assemble_prompt(plan)
    
    # Update system message
    self.message_history[0]["content"] = dynamic_prompt
    
    # Log for observability
    self._log("DYNAMIC_PROMPT_META", json.dumps({
        "templates_used": plan.get("needed_templates", []),
        "prompt_length": len(dynamic_prompt),
        "approach": plan.get("approach", ""),
        "user_query_preview": user_input[:100]
    }))
    
    # Append user message
    self.message_history.append({"role": "user", "content": user_input})
    self._log("USER_INPUT", user_input)
    
    # Continue normal execution...
    # [rest of existing process_input logic]
```

**Success Criteria**:
- [ ] Planning happens before LLM call
- [ ] System prompt dynamically assembled
- [ ] Logged for debugging
- [ ] No breaking changes to execution flow

---

### Phase 4: Cleanup [30min]

#### Task 4.1: Remove Old Static Prompt Logic ⏱️ 30min
**File**: `agent.py`

- [ ] Remove `_format_tools_for_prompt()` method
- [ ] Simplify `_build_system_prompt()` to just store system_context
- [ ] Update `__init__` to store system_context on self
- [ ] Remove any tool-specific instructions from static prompt
- [ ] Clean up comments

**Success Criteria**:
- [ ] No dead code
- [ ] Initialization still works
- [ ] System context preserved

---

### Phase 5: Testing [3h]

#### Task 5.1: Unit Tests ⏱️ 1.5h
**File**: `tests/test_dynamic_prompting.py` (new)

```python
def test_tool_catalog_generation():
    """Test tool catalog includes discovery metadata"""
    
def test_planning_with_data_query():
    """Test: 'read CSV and plot' selects python_sandbox template"""
    
def test_planning_with_shell_query():
    """Test: 'grep logs' selects shell_ops template"""
    
def test_planning_with_conversation():
    """Test: 'hello' selects only base template"""
    
def test_planning_fallback_on_error():
    """Test graceful fallback when planning fails"""
    
def test_prompt_assembly():
    """Test prompt composition from plan"""
```

**Success Criteria**:
- [ ] All unit tests pass
- [ ] Planning tested for common scenarios
- [ ] Fallback behavior validated
- [ ] Catalog generation tested

---

#### Task 5.2: Integration Tests ⏱️ 1h
**File**: `tests/test_agent_integration.py`

**Critical regression tests**:
- [ ] Simple conversation works
- [ ] File read/write works
- [ ] Shell commands work
- [ ] Sandbox execution works
- [ ] Interactive tools work
- [ ] Multi-turn context preserved
- [ ] Tool calling loop completes

**New behavior tests**:
- [ ] Data analysis query includes sandbox guidance
- [ ] Simple query produces smaller prompt
- [ ] Planning logged correctly

**Success Criteria**:
- [ ] No regressions
- [ ] New dynamic behavior works
- [ ] All existing tests pass

---

#### Task 5.3: Manual Validation ⏱️ 30min

**Test scenarios**:

1. **Simple conversation**:
   - Input: "Hello, how are you?"
   - Verify: Only base template used, prompt <300 chars

2. **Data analysis** (critical):
   - Input: "Read data.csv and create a histogram"
   - Verify: Plan includes run_python_sandbox, python_sandbox template
   - Verify: Generated code uses `os.environ['SANDBOX_PROJECT']`

3. **Shell task**:
   - Input: "Find all .py files"
   - Verify: Plan includes run_command, shell_ops template

4. **Knowledge query**:
   - Input: "What is quantum computing?"
   - Verify: Plan includes wikipedia_search, external_knowledge template

**Success Criteria**:
- [ ] All scenarios behave correctly
- [ ] Prompts are contextually appropriate
- [ ] Sandbox file I/O patterns appear when needed

---

### Phase 6: Documentation [1h]

#### Task 6.1: Create Documentation ⏱️ 1h
**File**: `docs/dynamic_prompting.md` (new)

Document:
- Architecture overview (discovery → planning → assembly → execution)
- How to add discovery metadata to tools
- How to add new prompt templates
- How planning works
- Debugging guide (log entries to check)
- Troubleshooting

Update `README.md`:
- Mention MCP-inspired dynamic prompting
- Link to detailed docs

**Success Criteria**:
- [ ] Clear documentation for maintainers
- [ ] Examples of extending system
- [ ] Troubleshooting guide

---

## 📊 Success Metrics

### Quantitative
- **Prompt size**: 50-70% reduction for simple queries
- **Planning latency**: <500ms overhead
- **Template selection accuracy**: >85% appropriate for query type
- **Sandbox file I/O**: Used correctly when relevant

### Qualitative
- **Better sandbox usage**: Agent uses file I/O patterns from examples
- **Focused prompts**: Only relevant guidance included
- **Maintainability**: Easy to add tools and templates
- **Observability**: Clear logs of planning decisions

---

## 🧪 Regression Checklist

**Must not break**:
- [ ] Simple conversational queries
- [ ] File read/write operations
- [ ] Shell command execution
- [ ] Python sandbox execution
- [ ] Sudo command handling
- [ ] Interactive tool streaming
- [ ] Wikipedia search
- [ ] Multi-turn conversations
- [ ] Tool calling loop
- [ ] Message history trimming
- [ ] Secret handling
- [ ] Database logging
- [ ] Error handling/recovery
- [ ] All existing tests in `tests/`

---

## ⚠️ Risk Mitigation

**Risk**: Planning adds latency  
**Mitigation**: <500ms acceptable, can optimize later with caching

**Risk**: Planning LLM makes poor choices  
**Mitigation**: Fallback to base template, iterative tuning, observability

**Risk**: Breaking changes  
**Mitigation**: Comprehensive test suite, careful integration

**Risk**: Tool metadata maintenance burden  
**Mitigation**: Metadata is optional, only add where valuable

---

## 🔮 Future Enhancements

**v2: Caching**
- Cache plans for similar queries within session
- Reduce redundant planning calls

**v3: Full Self-Prompting**
- LLM generates custom prompt text (not just selects templates)
- More flexible, fully adaptive

**v4: Multi-Agent MCP**
- Expose this agent as MCP server
- Other agents can discover our tools
- Full MCP protocol implementation

---

## 📦 Deliverables

- [ ] Tool discovery metadata implemented
- [ ] Prompt template library defined
- [ ] Planning phase working
- [ ] Dynamic prompt assembly working
- [ ] All regression tests passing
- [ ] New tests for dynamic behavior
- [ ] Documentation complete
- [ ] Observability/logging in place
- [ ] Feature branch ready for review

---

## ✅ Approval Checklist

Before merging:
- [ ] All tasks completed
- [ ] All regression tests pass
- [ ] Manual validation passes
- [ ] Documentation complete
- [ ] Code reviewed
- [ ] No defensive guards added
- [ ] Trust-based design maintained
- [ ] Approved by: _______________

---

**Estimated Total Effort**: 10-12 hours  
**Risk Level**: Medium (architectural change, well-isolated)  
**Impact**: High (cleaner prompts, better sandbox usage, foundation for future evolution)  
**Philosophy**: Trust + discovery over guards + heuristics
