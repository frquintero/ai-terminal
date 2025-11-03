# MCP-Native Agent with Self-Prompting
## Focused Implementation: Tool Discovery + Self-Generated Prompts

---

## 📜 Executive Summary

### **What We're Building**

1. **MCP Server** - Expose our tools via Model Context Protocol with rich metadata
2. **Self-Prompting System** - LLM generates its own optimal execution prompt per query

### **Why**

**Core Problem**: Sandbox file I/O misuse (agents don't use `os.environ['SANDBOX_PROJECT']`)

**Root Cause**: Static prompts don't reference specific tool patterns when needed

**Solution**: 
- Tools expose usage examples as MCP resources
- LLM discovers available tools + examples
- LLM generates custom prompt referencing relevant patterns

### **How**

```
User Query: "Read data.csv and create histogram"
    ↓
Tool Catalog Discovery
  └─ run_python_sandbox
      └─ Example: pd.read_csv(os.path.join(os.environ['SANDBOX_PROJECT'], 'data.csv'))
    ↓
Self-Prompting (LLM generates):
  "You are a data analysis assistant. Use run_python_sandbox.
   Access project files via os.environ['SANDBOX_PROJECT'].
   Example: pd.read_csv(os.path.join(os.environ['SANDBOX_PROJECT'], 'data.csv'))"
    ↓
Execution with Custom Prompt
```

### **User Gains**

- 🚀 **Better sandbox usage**: Prompts include file I/O patterns when relevant
- 🧠 **Query-specific guidance**: Each query gets tailored instructions
- 📚 **Self-documenting tools**: Examples embedded in tool metadata
- 🎯 **Token efficiency**: Only relevant guidance included

---

## 🎯 Core Philosophy

**Trust + Discovery**: Give LLM access to rich tool catalog, let it decide what guidance it needs.

---

## 📋 Implementation Tasks

## PHASE 1: MCP Server with Rich Tool Metadata [6-8h]

### Task 1.1: Setup MCP SDK ⏱️ 30min

**Files**: `requirements.txt`, `mcp_server.py` (new)

```bash
pip install mcp
```

Create `mcp_server.py`:
```python
from mcp import Server
from mcp.server.stdio import stdio_server
from tools import TOOLS

server = Server("ai-terminal")
```

**Success Criteria**:
- [ ] MCP SDK installed
- [ ] Server module created

---

### Task 1.2: Add Rich Metadata to Tools ⏱️ 2h

**File**: `tools.py`

Add to `BaseTool`:
```python
class BaseTool(ABC):
    # ... existing methods ...
    
    @property
    def usage_examples(self) -> Optional[List[dict]]:
        """Usage examples for tool discovery"""
        return None
```

Implement for `RunPythonSandboxTool`:
```python
@property
def usage_examples(self) -> List[dict]:
    return [
        {
            "name": "Reading project CSV file",
            "code": """import os
import pandas as pd

# Access project files
project_dir = os.environ['SANDBOX_PROJECT']
df = pd.read_csv(os.path.join(project_dir, 'data.csv'))

print(df.head())"""
        },
        {
            "name": "Saving plot to artifacts",
            "code": """import matplotlib.pyplot as plt

# Create plot
plt.plot([1, 2, 3, 4])
plt.title('My Analysis')

# Automatically saved to artifacts/plot_1.png
# No need to call plt.savefig()"""
        },
        {
            "name": "Writing output file to project",
            "code": """import os

project_dir = os.environ['SANDBOX_PROJECT']
output_path = os.path.join(project_dir, 'results.txt')

with open(output_path, 'w') as f:
    f.write('Analysis results')"""
        }
    ]
```

Add minimal examples to other key tools:
- `run_command`: Common patterns (grep, find, etc.)
- `run_interactive`: How to launch vim, top, etc.
- `write_file`: File path patterns

**Success Criteria**:
- [ ] `usage_examples` property added to BaseTool
- [ ] RunPythonSandboxTool has 3+ file I/O examples
- [ ] 2-3 other tools have basic examples

---

### Task 1.3: Implement MCP Server Tool Discovery ⏱️ 2h

**File**: `mcp_server.py`

```python
from mcp import Server, Tool
from tools import TOOLS

server = Server("ai-terminal")

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Expose tools with metadata"""
    mcp_tools = []
    
    for tool in TOOLS.values():
        mcp_tools.append(Tool(
            name=tool.name,
            description=tool.description,
            inputSchema=tool.schema["function"]["parameters"]
        ))
    
    return mcp_tools

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Execute tool calls"""
    tool = TOOLS.get(name)
    if not tool:
        return [{"type": "text", "text": f"Error: Tool '{name}' not found"}]
    
    try:
        result = tool.execute(**arguments)
        return [{"type": "text", "text": result if isinstance(result, str) else str(result)}]
    except Exception as e:
        return [{"type": "text", "text": f"Error: {e}"}]
```

**Success Criteria**:
- [ ] Tool discovery works
- [ ] Tool execution works
- [ ] Error handling works

---

### Task 1.4: Expose Usage Examples as MCP Resources ⏱️ 1.5h

**File**: `mcp_server.py`

```python
@server.list_resources()
async def list_resources():
    """Expose tool usage examples as resources"""
    resources = []
    
    for tool in TOOLS.values():
        examples = tool.usage_examples
        if not examples:
            continue
        
        for idx, example in enumerate(examples):
            resources.append({
                "uri": f"example://{tool.name}/{idx}",
                "name": f"{tool.name}: {example['name']}",
                "description": f"Usage example for {tool.name}",
                "mimeType": "text/x-python" if "code" in example else "text/plain"
            })
    
    return resources

@server.read_resource()
async def read_resource(uri: str):
    """Return example code for a resource"""
    # Parse URI: example://tool_name/index
    parts = uri.replace("example://", "").split("/")
    tool_name, idx = parts[0], int(parts[1])
    
    tool = TOOLS.get(tool_name)
    if not tool or not tool.usage_examples:
        return {"contents": [{"uri": uri, "text": "Not found"}]}
    
    example = tool.usage_examples[idx]
    return {
        "contents": [{
            "uri": uri,
            "mimeType": "text/x-python",
            "text": example.get("code", "")
        }]
    }
```

**Success Criteria**:
- [ ] Resources expose usage examples
- [ ] Examples are readable as resources
- [ ] URI scheme works correctly

---

### Task 1.5: Implement stdio Transport ⏱️ 1h

**File**: `mcp_server.py`

```python
async def main():
    """Run MCP server via stdio"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

Create `run_mcp_server.py`:
```python
#!/usr/bin/env python3
"""MCP Server launcher for ai-terminal"""
from mcp_server import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
```

**Success Criteria**:
- [ ] Server starts via stdio
- [ ] Can be launched from command line
- [ ] No errors on startup

---

### Task 1.6: Testing MCP Server ⏱️ 1h

**File**: `tests/test_mcp_server.py` (new)

```python
import pytest
from mcp_server import list_tools, list_resources, call_tool

@pytest.mark.asyncio
async def test_tool_discovery():
    """Test tool listing"""
    tools = await list_tools()
    assert len(tools) > 0
    assert any(t.name == "run_python_sandbox" for t in tools)

@pytest.mark.asyncio
async def test_resource_discovery():
    """Test example resources"""
    resources = await list_resources()
    # Should have sandbox examples
    assert any("run_python_sandbox" in r["uri"] for r in resources)

@pytest.mark.asyncio
async def test_tool_execution():
    """Test running a tool"""
    result = await call_tool("run_command", {"command": "echo hello"})
    assert "hello" in result[0]["text"].lower()
```

**Success Criteria**:
- [ ] All tests pass
- [ ] Tools discoverable
- [ ] Resources discoverable
- [ ] Execution works

---

## PHASE 2: Self-Prompting System [4-6h]

### Task 2.1: Build Tool Catalog Generator ⏱️ 1h

**File**: `agent.py`

```python
def _build_tool_catalog(self) -> dict:
    """Build comprehensive tool catalog with examples"""
    catalog = {"tools": []}
    
    for tool in TOOLS.values():
        tool_info = {
            "name": tool.name,
            "description": tool.description,
            "schema": tool.schema["function"]["parameters"]
        }
        
        # Include usage examples if available
        if tool.usage_examples:
            tool_info["examples"] = tool.usage_examples
        
        catalog["tools"].append(tool_info)
    
    return catalog

def __init__(self):
    # ... existing init ...
    
    # Build tool catalog once per session
    self.tool_catalog = self._build_tool_catalog()
```

**Success Criteria**:
- [ ] Catalog includes all tools
- [ ] Examples included when available
- [ ] Built once per session (cached)

---

### Task 2.2: Implement Self-Prompting ⏱️ 2h

**File**: `agent.py`

```python
def _generate_execution_prompt(self, user_query: str) -> str:
    """LLM generates its own optimal execution prompt"""
    
    meta_prompt = f"""You are a meta-prompt generator for an AI terminal assistant.

USER QUERY:
{user_query}

AVAILABLE TOOLS (with usage examples):
{json.dumps(self.tool_catalog, indent=2)}

YOUR TASK:
Analyze the user query and generate the optimal system prompt for executing this task.

Include in your generated prompt:
1. Your role/identity for this specific task
2. Which tools are most relevant
3. Critical usage patterns (especially for data/file operations - reference the examples!)
4. Any constraints or guidelines

Keep the prompt under 400 words and focused on what's needed for THIS specific query.

Return JSON:
{{
  "system_prompt": "The complete system prompt you've generated",
  "key_tools": ["tool1", "tool2"],
  "reasoning": "Brief explanation of why this prompt is optimal"
}}"""
    
    try:
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": "Meta-prompt generator. Analyze queries and generate optimal execution prompts. Return only valid JSON."},
                {"role": "user", "content": meta_prompt}
            ],
            temperature=0.3,  # Some creativity, mostly deterministic
            max_tokens=600,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        self._log("GENERATED_PROMPT", json.dumps(result))
        
        return result["system_prompt"]
        
    except Exception as e:
        # Fallback to minimal base prompt
        self._log("PROMPT_GENERATION_ERROR", str(e))
        return "Shell automation expert and conversational assistant. Use tools for file I/O, commands, and external info."
```

**Success Criteria**:
- [ ] Generates valid system prompts
- [ ] Includes relevant tool examples
- [ ] <600ms overhead
- [ ] Graceful fallback on errors

---

### Task 2.3: Integrate Self-Prompting into Main Loop ⏱️ 1h

**File**: `agent.py`

```python
def process_input(self, user_input: str, max_steps: int = None):
    """Process user input with self-generated prompts"""
    
    ui.start_timer()
    self._current_step_tool_outputs = []
    
    # SELF-PROMPTING: LLM generates optimal prompt for this query
    custom_prompt = self._generate_execution_prompt(user_input)
    
    # Append system context
    if hasattr(self, 'system_context'):
        full_prompt = f"{custom_prompt}\n\n{self.system_context}"
    else:
        full_prompt = custom_prompt
    
    # Update system message
    self.message_history[0]["content"] = full_prompt
    
    # Log for observability
    self._log("DYNAMIC_PROMPT", json.dumps({
        "prompt_length": len(full_prompt),
        "user_query_preview": user_input[:100]
    }))
    
    # Append user message and continue normal flow
    self.message_history.append({"role": "user", "content": user_input})
    self._log("USER_INPUT", user_input)
    
    # ... rest of existing process_input logic ...
```

**Success Criteria**:
- [ ] Prompt generation happens before LLM call
- [ ] System message updated correctly
- [ ] No breaking changes to execution flow

---

### Task 2.4: Remove Old Static Prompt Logic ⏱️ 30min

**File**: `agent.py`

- [ ] Keep `_build_system_prompt` for system_context only
- [ ] Remove tool listing from static prompt
- [ ] Store `system_context` separately
- [ ] Update `__init__` to use new approach

**Success Criteria**:
- [ ] No dead code
- [ ] Clean initialization
- [ ] System context preserved

---

### Task 2.5: Testing Self-Prompting ⏱️ 1.5h

**File**: `tests/test_self_prompting.py` (new)

```python
def test_tool_catalog_generation():
    """Test catalog includes examples"""
    agent = MiniAgent()
    assert "tools" in agent.tool_catalog
    # Should have sandbox with examples
    sandbox_tool = next((t for t in agent.tool_catalog["tools"] if t["name"] == "run_python_sandbox"), None)
    assert sandbox_tool is not None
    assert "examples" in sandbox_tool

def test_prompt_generation_for_data_query():
    """Test: data query generates sandbox-focused prompt"""
    agent = MiniAgent()
    prompt = agent._generate_execution_prompt("Read data.csv and create histogram")
    
    # Prompt should reference sandbox or file I/O
    assert "sandbox" in prompt.lower() or "SANDBOX_PROJECT" in prompt

def test_prompt_generation_for_simple_query():
    """Test: simple query generates minimal prompt"""
    agent = MiniAgent()
    prompt = agent._generate_execution_prompt("Hello, how are you?")
    
    # Should be shorter, less tool-focused
    assert len(prompt) < 500

def test_fallback_on_error():
    """Test graceful fallback"""
    agent = MiniAgent()
    # Simulate error by breaking something temporarily
    original_client = agent.client
    agent.client = None
    
    prompt = agent._generate_execution_prompt("test query")
    
    # Should return fallback prompt
    assert len(prompt) > 0
    assert "error" not in prompt.lower()
    
    agent.client = original_client
```

Manual validation:
- [ ] "Read data.csv and plot" → prompt includes SANDBOX_PROJECT pattern
- [ ] "Hello" → short, conversational prompt
- [ ] "Find all .py files" → shell-focused prompt

**Success Criteria**:
- [ ] All unit tests pass
- [ ] Manual tests show appropriate prompt generation
- [ ] Sandbox file I/O patterns appear when relevant

---

## 🧪 Comprehensive Testing [2h]

### Regression Tests

**Must not break**:
- [ ] Simple conversational queries
- [ ] File read/write operations
- [ ] Shell command execution
- [ ] Python sandbox execution
- [ ] Sudo command handling
- [ ] Interactive tool streaming
- [ ] Wikipedia search
- [ ] Multi-turn conversations
- [ ] All existing tests in `tests/`

### New Behavior Validation

**Self-Prompting**:
- [ ] Data analysis queries include sandbox examples in prompt
- [ ] Simple queries get minimal prompts
- [ ] Prompts are query-specific
- [ ] Fallback works on errors

**MCP Server**:
- [ ] Tools discoverable via MCP protocol
- [ ] Resources expose usage examples
- [ ] Tool execution works via MCP

---

## 📚 Documentation [1h]

### Files to Create/Update

- [ ] `docs/mcp_server.md` - How MCP server works, how to run it
- [ ] `docs/self_prompting.md` - How self-prompting works
- [ ] Update `README.md` - Mention MCP compatibility and self-prompting
- [ ] Add usage examples

---

## 📊 Success Metrics

### Quantitative
- **Prompt relevance**: 80%+ of data queries include sandbox patterns in prompt
- **Token efficiency**: 30-50% smaller prompts for simple queries
- **Performance**: <600ms self-prompting overhead
- **MCP compatibility**: Tools discoverable via standard protocol

### Qualitative
- **Better sandbox usage**: LLM uses `os.environ['SANDBOX_PROJECT']` correctly
- **Query-appropriate prompts**: Different queries get different guidance
- **Self-documenting**: Examples accessible via tool metadata

---

## ⚠️ Risk Mitigation

**Risk**: Self-generated prompts are suboptimal  
**Mitigation**: Fallback to base prompt, logging for tuning, iterative improvement

**Risk**: Prompt generation adds latency  
**Mitigation**: <600ms target, acceptable for better quality

**Risk**: Breaking existing functionality  
**Mitigation**: Comprehensive regression suite

---

## 🚀 Rollout Plan

1. **Week 1**: Phase 1 (MCP Server + Tool Metadata)
2. **Week 2**: Phase 2 (Self-Prompting System)
3. **Week 3**: Testing + Documentation + Refinement

**Total: 3 weeks, 12-16 hours effort**

---

## ✅ Approval Checklist

- [ ] Both phases completed
- [ ] All regression tests pass
- [ ] Self-prompting works for common scenarios
- [ ] Sandbox file I/O patterns referenced in prompts
- [ ] MCP server functional
- [ ] Documentation complete
- [ ] Performance validated
- [ ] Approved by: _______________

---

**Philosophy**: Discovery + Self-Direction > Static Rules  
**Focus**: Our tools, our prompts, our agent  
**Goal**: Better sandbox usage through intelligent, query-specific prompting
