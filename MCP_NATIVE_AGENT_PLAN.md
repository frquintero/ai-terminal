# MCP-Native Agent Implementation Plan
## From Isolated Terminal to Universal AI Tool Ecosystem

---

## 📜 Executive Summary

### **What We Plan to Do**

Transform this AI terminal from a standalone agent into a **Model Context Protocol (MCP) native system** that can:

1. **Expose our tools as an MCP server** → Other AI agents (Claude Desktop, Cursor, etc.) can use our shell/sandbox/file tools
2. **Consume external MCP tools** → Our agent gains access to thousands of existing MCP tools (databases, APIs, multimodal capabilities)
3. **Implement dynamic prompting** → Internal optimization for better tool usage and sandbox operation

### **Why We Plan to Do It**

**Current Problems**:
- ❌ Tool schemas sent every API request (unavoidable overhead with current approach)
- ❌ Can only use tools we manually implement
- ❌ Sandbox file I/O misuse (original motivation: improve sandbox usage)
- ❌ Isolated from growing MCP ecosystem
- ❌ Other agents can't leverage our powerful shell/sandbox tools

**MCP Solution**:
- ✅ **Standard protocol** for tool sharing across AI systems
- ✅ **Persistent tool registration** for MCP clients (no per-request schemas for external agents using our tools)
- ✅ **Tool marketplace**: Access thousands of pre-built MCP servers
- ✅ **Interoperability**: Work seamlessly with Claude, Cursor, VSCode, etc.
- ✅ **Future-proof**: Align with emerging AI agent standards

### **How We Plan to Do It**

**Three-Phase Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                    Phase 1: MCP Server                      │
│         (Expose Our Tools to External Agents)               │
│                                                             │
│  Claude Desktop ───┐                                        │
│  Cursor ───────────┼──→ [MCP Server] ─→ Our Tools          │
│  Other Agents ─────┘     (stdio/SSE)      - run_command    │
│                                            - run_sandbox    │
│                                            - read/write     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   Phase 2: MCP Client                       │
│        (Consume External Tools in Our Agent)                │
│                                                             │
│  Our Agent ──→ [MCP Client] ─┬─→ MiniMax MCP (video/audio) │
│                              ├─→ Database MCP               │
│                              ├─→ Browser MCP                │
│                              └─→ Any MCP Server             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              Phase 3: Dynamic Prompting                     │
│         (Internal Optimization & Planning)                  │
│                                                             │
│  User Query → Planning → Template Selection → Execution    │
│              (self-directed guidance for better results)    │
└─────────────────────────────────────────────────────────────┘
```

**Implementation Strategy**:
1. Use official MCP Python SDK (`pip install mcp`)
2. Wrap existing tools in MCP protocol
3. Implement stdio transport first (simplest), then SSE
4. Add MCP client to discover and call external tools
5. Layer dynamic prompting on top for internal optimization

### **What Users Gain**

**For Terminal Users**:
- 🎨 **Multimodal capabilities**: Generate videos, audio, music (via MiniMax MCP)
- 🌐 **Database access**: Query databases without manual integration
- 🔧 **Tool marketplace**: Install any MCP server, instant capabilities
- 🚀 **Better sandbox**: Dynamic prompting ensures correct file I/O patterns

**For Other AI Users (Claude, Cursor, etc.)**:
- 💻 **Shell automation**: Run commands via our MCP server
- 🐍 **Python sandbox**: Safe code execution with project access
- 📁 **File operations**: Read/write files through our tools
- 🔒 **Secure execution**: Resource-limited, isolated sandbox

**For Developers**:
- 🔌 **Standard protocol**: One interface for all AI tools
- 🏗️ **Composability**: Mix and match MCP servers
- 📦 **Reusability**: Tools written once, used by all agents
- 🌍 **Ecosystem**: Join the growing MCP community

---

## 🎯 Core Philosophy

**Universal Tool Access Through Open Standards**

Principles:
- ✅ **Interoperability**: Tools work across all MCP-compatible agents
- ✅ **Discoverability**: Tools self-describe capabilities and usage
- ✅ **Composability**: Combine tools from multiple MCP servers
- ✅ **Trust over guards**: Well-designed protocols, clear contracts
- ✅ **Community-driven**: Leverage existing MCP ecosystem

## 📐 Architecture Evolution

### Current State
```
[Isolated Agent]
User Query → Static Prompt → LLM → Internal Tools Only → Response
                                    (tool schemas sent every call)
```

### Target State (MCP-Native)
```
[MCP Server Mode]
External Agents (Claude/Cursor) → Our MCP Server → Our Tools
                                  (persistent registration)

[MCP Client Mode]  
User Query → Planning → Our Agent → MCP Clients → External MCP Servers
                                                   (video, DB, browser...)
[Internal Optimization]
Dynamic Prompting → Template Selection → Focused Execution
```

### Design Principles
1. **MCP-first**: Native protocol support, not adapters
2. **Bidirectional**: Both server and client capabilities
3. **Progressive enhancement**: Works standalone, better with MCP ecosystem
4. **Self-directed**: LLM plans tool usage, selects guidance templates
5. **Observable**: Clear logging of MCP interactions and planning decisions

---

## 📋 Implementation Tasks

## PHASE 1: MCP Server Implementation [8-10h]

Expose our tools to external MCP clients (Claude Desktop, Cursor, etc.)

### Task 1.1: Setup MCP SDK ⏱️ 30min
**File**: `requirements.txt`, `mcp_server.py` (new)

- [ ] Add `mcp` to requirements: `pip install mcp`
- [ ] Create `mcp_server.py` module for MCP server implementation
- [ ] Import MCP server components:
  ```python
  from mcp import Server, Tool
  from mcp.server.stdio import stdio_server
  ```
- [ ] Create basic server skeleton

**Success Criteria**:
- [ ] MCP SDK installed
- [ ] Server module created
- [ ] Imports successful

---

### Task 1.2: Wrap Tools in MCP Protocol ⏱️ 3h
**File**: `mcp_server.py`

Convert existing tools to MCP tool format:

```python
from mcp import Server, Tool
from tools import TOOLS

server = Server("ai-terminal")

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Expose our tools to MCP clients"""
    mcp_tools = []
    
    for tool in TOOLS.values():
        mcp_tools.append(Tool(
            name=tool.name,
            description=tool.description,
            inputSchema=tool.schema["function"]["parameters"]
        ))
    
    return mcp_tools

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> str:
    """Execute tool calls from MCP clients"""
    tool = TOOLS.get(name)
    if not tool:
        return f"Error: Tool '{name}' not found"
    
    try:
        result = tool.execute(**arguments)
        return result if isinstance(result, str) else str(result)
    except Exception as e:
        return f"Error executing {name}: {e}"
```

Tools to expose:
- [ ] `read_file` - File reading
- [ ] `write_file` - File writing
- [ ] `run_command` - Shell command execution
- [ ] `run_interactive` - Interactive programs (vim, top, etc.)
- [ ] `run_sudo_command` - Privileged operations
- [ ] `run_python_sandbox` - Sandboxed Python execution
- [ ] `wikipedia_search` - External knowledge

**Success Criteria**:
- [ ] All tools wrapped in MCP protocol
- [ ] Tool discovery works (`list_tools`)
- [ ] Tool execution works (`call_tool`)
- [ ] Errors handled gracefully

---

### Task 1.3: Implement stdio Transport ⏱️ 2h
**File**: `mcp_server.py`, `run_mcp_server.py` (new)

Implement stdio transport (simplest, works with Claude Desktop/Cursor):

```python
# mcp_server.py
from mcp.server.stdio import stdio_server

async def main():
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

Create launcher script:
```python
# run_mcp_server.py
#!/usr/bin/env python3
"""
MCP Server launcher for ai-terminal tools.
Usage: python run_mcp_server.py
"""
import sys
from mcp_server import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] Implement stdio transport
- [ ] Create launcher script
- [ ] Make launcher executable
- [ ] Test with simple MCP client

**Success Criteria**:
- [ ] Server starts via stdio
- [ ] Can communicate with MCP clients
- [ ] Tools discoverable from clients

---

### Task 1.4: Add Usage Examples to Tool Metadata ⏱️ 1.5h
**File**: `tools.py`

Enhance tools with MCP-friendly metadata (resources):

```python
# In RunPythonSandboxTool
@property
def mcp_resources(self) -> list[dict]:
    """Expose usage examples as MCP resources"""
    return [
        {
            "uri": "example://sandbox/file-io",
            "name": "Sandbox File I/O Pattern",
            "description": "How to access project files in sandbox",
            "mimeType": "text/plain",
            "content": """import os
import pandas as pd

# Access project files
project_dir = os.environ['SANDBOX_PROJECT']
df = pd.read_csv(os.path.join(project_dir, 'data.csv'))

# Process data...
# Plots auto-save to artifacts/"""
        },
        {
            "uri": "example://sandbox/plotting",
            "name": "Plotting in Sandbox",
            "description": "How plots are automatically saved",
            "mimeType": "text/plain",
            "content": """import matplotlib.pyplot as plt

# Create plot
plt.plot([1, 2, 3, 4])
plt.title('My Plot')

# Automatically saved to artifacts/plot_1.png
# No need to call plt.savefig()"""
        }
    ]
```

Add resources endpoint to MCP server:
```python
@server.list_resources()
async def list_resources():
    """Expose usage examples as resources"""
    resources = []
    for tool in TOOLS.values():
        if hasattr(tool, 'mcp_resources'):
            resources.extend(tool.mcp_resources)
    return resources
```

**Success Criteria**:
- [ ] Key tools have usage examples as resources
- [ ] Resources endpoint implemented
- [ ] Examples are clear and copy-pasteable

---

### Task 1.5: Client Configuration Documentation ⏱️ 1h
**File**: `docs/mcp_server_usage.md` (new)

Document how to use our MCP server with popular clients:

**Claude Desktop config**:
```json
{
  "mcpServers": {
    "ai-terminal": {
      "command": "python",
      "args": ["/path/to/ai-terminal/run_mcp_server.py"],
      "env": {
        "PYTHONPATH": "/path/to/ai-terminal"
      }
    }
  }
}
```

**Cursor config**:
```json
{
  "mcpServers": {
    "ai-terminal": {
      "command": "python",
      "args": ["/path/to/ai-terminal/run_mcp_server.py"]
    }
  }
}
```

- [ ] Document Claude Desktop setup
- [ ] Document Cursor setup
- [ ] Document Cherry Studio setup
- [ ] Add troubleshooting section
- [ ] Include example usage scenarios

**Success Criteria**:
- [ ] Clear setup instructions for 3+ clients
- [ ] Troubleshooting guide
- [ ] Example workflows

---

### Task 1.6: Testing MCP Server ⏱️ 2h
**File**: `tests/test_mcp_server.py` (new)

```python
import pytest
from mcp_server import server, list_tools, call_tool

@pytest.mark.asyncio
async def test_list_tools():
    """Test tool discovery"""
    tools = await list_tools()
    assert len(tools) > 0
    assert any(t.name == "run_python_sandbox" for t in tools)

@pytest.mark.asyncio
async def test_call_run_command():
    """Test executing run_command via MCP"""
    result = await call_tool("run_command", {"command": "echo hello"})
    assert "hello" in result.lower()

@pytest.mark.asyncio
async def test_call_sandbox():
    """Test sandbox execution via MCP"""
    result = await call_tool("run_python_sandbox", {
        "code": "print('Hello from sandbox')"
    })
    assert "Hello from sandbox" in result

@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling for invalid tools"""
    result = await call_tool("nonexistent_tool", {})
    assert "Error" in result or "not found" in result.lower()
```

Manual integration test with Claude Desktop:
- [ ] Configure Claude Desktop with our server
- [ ] Test: "Read the config.py file"
- [ ] Test: "Run 'ls -la' in shell"
- [ ] Test: "Execute Python code to calculate 2+2"
- [ ] Test: "Search Wikipedia for quantum computing"

**Success Criteria**:
- [ ] All unit tests pass
- [ ] Claude Desktop can discover our tools
- [ ] Claude can successfully execute tools
- [ ] Error handling works correctly

---

## PHASE 2: MCP Client Implementation [6-8h]

Enable our agent to consume external MCP tools

### Task 2.1: Install MCP Client SDK ⏱️ 30min
**File**: `requirements.txt`, `mcp_client.py` (new)

- [ ] MCP SDK already installed (from Phase 1)
- [ ] Create `mcp_client.py` module
- [ ] Import client components:
  ```python
  from mcp import ClientSession, StdioServerParameters
  from mcp.client.stdio import stdio_client
  ```

**Success Criteria**:
- [ ] Client module created
- [ ] Can import MCP client libraries

---

### Task 2.2: Implement MCP Server Connection Manager ⏱️ 2h
**File**: `mcp_client.py`

```python
from typing import Dict, List
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

class MCPClientManager:
    """Manages connections to multiple MCP servers"""
    
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.available_tools: Dict[str, dict] = {}
    
    async def connect_server(self, name: str, command: str, args: List[str], env: dict = None):
        """Connect to an MCP server"""
        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env or {}
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Discover tools
                tools = await session.list_tools()
                
                # Store session and tools
                self.sessions[name] = session
                for tool in tools.tools:
                    self.available_tools[f"{name}:{tool.name}"] = {
                        "server": name,
                        "tool": tool,
                        "session": session
                    }
    
    async def call_tool(self, full_name: str, arguments: dict) -> str:
        """Call a tool from connected MCP server"""
        if full_name not in self.available_tools:
            return f"Error: Tool {full_name} not found"
        
        tool_info = self.available_tools[full_name]
        session = tool_info["session"]
        tool_name = tool_info["tool"].name
        
        result = await session.call_tool(tool_name, arguments)
        return result.content[0].text if result.content else ""
    
    def get_available_tools(self) -> List[dict]:
        """Get list of all available tools from all servers"""
        return [
            {
                "name": full_name,
                "description": info["tool"].description,
                "schema": info["tool"].inputSchema
            }
            for full_name, info in self.available_tools.items()
        ]
```

**Success Criteria**:
- [ ] Can connect to multiple MCP servers
- [ ] Tool discovery works
- [ ] Tool calls route correctly
- [ ] Clean error handling

---

### Task 2.3: Integrate MCP Client into Agent ⏱️ 2h
**File**: `agent.py`

Add MCP client to agent:

```python
class MiniAgent:
    def __init__(self):
        # ... existing init ...
        
        # MCP client for external tools
        self.mcp_client = MCPClientManager()
        self.mcp_tools_loaded = False
    
    async def _load_mcp_servers(self):
        """Load configured MCP servers"""
        mcp_config = self.config.mcp_servers or []
        
        for server_config in mcp_config:
            await self.mcp_client.connect_server(
                name=server_config["name"],
                command=server_config["command"],
                args=server_config.get("args", []),
                env=server_config.get("env", {})
            )
        
        self.mcp_tools_loaded = True
    
    def _get_all_tool_schemas(self):
        """Combine internal and MCP tools"""
        schemas = get_tool_schemas()  # Internal tools
        
        if self.mcp_tools_loaded:
            # Add MCP tools
            for tool in self.mcp_client.get_available_tools():
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["schema"]
                    }
                })
        
        return schemas
```

Update tool execution to handle MCP tools:

```python
async def _execute_tool(self, tool_name: str, args: dict) -> str:
    """Execute internal or MCP tool"""
    
    # Check if it's an MCP tool (format: "server:tool_name")
    if ":" in tool_name:
        return await self.mcp_client.call_tool(tool_name, args)
    
    # Internal tool
    tool = TOOLS.get(tool_name)
    if not tool:
        return f"Error: Tool '{tool_name}' not found"
    
    return tool.execute(**args)
```

**Success Criteria**:
- [ ] MCP client integrated into agent
- [ ] Can load configured MCP servers
- [ ] Internal + MCP tools combined in schema
- [ ] Tool execution routes correctly

---

### Task 2.4: Add MCP Configuration Support ⏱️ 1h
**File**: `config.py`, `.env.example`

```python
# config.py
@dataclass
class Config:
    # ... existing fields ...
    
    mcp_servers: Optional[List[dict]] = None

def load_config() -> Config:
    # ... existing loading ...
    
    # Load MCP server configs from environment or JSON file
    mcp_config_path = os.getenv("MCP_CONFIG_PATH", "mcp_config.json")
    mcp_servers = []
    
    if os.path.exists(mcp_config_path):
        with open(mcp_config_path) as f:
            mcp_config = json.load(f)
            mcp_servers = mcp_config.get("servers", [])
    
    return Config(
        # ... existing params ...
        mcp_servers=mcp_servers
    )
```

Create `mcp_config.json.example`:
```json
{
  "servers": [
    {
      "name": "minimax",
      "command": "uvx",
      "args": ["minimax-mcp"],
      "env": {
        "MINIMAX_API_KEY": "your-key-here"
      }
    }
  ]
}
```

**Success Criteria**:
- [ ] MCP config loading works
- [ ] Example config documented
- [ ] Graceful handling if no MCP servers configured

---

### Task 2.5: Testing MCP Client Integration ⏱️ 1.5h
**File**: `tests/test_mcp_client.py` (new)

```python
@pytest.mark.asyncio
async def test_mcp_client_connection():
    """Test connecting to an MCP server"""
    client = MCPClientManager()
    # Use a test MCP server
    await client.connect_server("test", "python", ["test_mcp_server.py"])
    
    tools = client.get_available_tools()
    assert len(tools) > 0

@pytest.mark.asyncio
async def test_agent_with_mcp_tools():
    """Test agent can use MCP tools"""
    agent = MiniAgent()
    await agent._load_mcp_servers()
    
    schemas = agent._get_all_tool_schemas()
    # Should have internal + MCP tools
    assert len(schemas) > len(TOOLS)
```

Manual integration test:
- [ ] Configure MiniMax MCP server
- [ ] Test: "Generate a short audio clip saying 'Hello World'"
- [ ] Test: "Create an image of a sunset over mountains"
- [ ] Verify multimodal outputs saved correctly

**Success Criteria**:
- [ ] Unit tests pass
- [ ] Can connect to real MCP servers
- [ ] Agent successfully calls MCP tools
- [ ] Multimodal outputs work

---

## PHASE 3: Dynamic Prompting (Internal Optimization) [6-8h]

Optimize internal prompt generation for better tool usage

### Task 3.1: Define Prompt Templates ⏱️ 1h
**File**: `agent.py`

```python
PROMPT_TEMPLATES = {
    "base": """Shell automation expert and conversational assistant.
Use tools for file I/O, commands, and external info. Respond directly for conversation.""",
    
    "python_sandbox": """Python sandbox (run_python_sandbox):
- Isolated execution with resource limits
- Access project files: os.environ['SANDBOX_PROJECT']
- Example: pd.read_csv(os.path.join(os.environ['SANDBOX_PROJECT'], 'data.csv'))
- Plots auto-save to artifacts/""",
    
    "shell_ops": """Shell tools:
- run_command: non-interactive commands
- run_interactive: vim, top, htop, etc.
- run_sudo_command: privileged operations""",
    
    "mcp_tools": """External capabilities via MCP:
- Multimodal generation (video, audio, images)
- Database access
- Browser automation
Check available MCP tools for current capabilities.""",
}
```

**Success Criteria**:
- [ ] 4-5 minimal templates defined
- [ ] Templates are descriptive, not prescriptive
- [ ] Total <500 chars

---

### Task 3.2: Implement Planning Phase ⏱️ 2h
**File**: `agent.py`

```python
def _plan_execution(self, user_query: str) -> dict:
    """LLM plans approach and selects needed templates"""
    
    # Build tool catalog (cache this per session)
    if not hasattr(self, '_tool_catalog_cache'):
        self._tool_catalog_cache = {
            "internal": [{"name": t.name, "description": t.description} for t in TOOLS.values()],
            "mcp": self.mcp_client.get_available_tools() if self.mcp_tools_loaded else []
        }
    
    planning_prompt = f"""Analyze this query and plan your approach.

USER QUERY:
{user_query}

AVAILABLE TOOLS:
{json.dumps(self._tool_catalog_cache, indent=2)}

PROMPT TEMPLATES: {list(PROMPT_TEMPLATES.keys())}

Return JSON:
{{
  "approach": "brief how you'll solve this",
  "primary_tools": ["tool1", "tool2"],
  "needed_templates": ["template1", "template2"]
}}"""
    
    try:
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": "Task planner. Return only JSON."},
                {"role": "user", "content": planning_prompt}
            ],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"}
        )
        
        plan = json.loads(response.choices[0].message.content)
        self._log("EXECUTION_PLAN", json.dumps(plan))
        return plan
    except Exception as e:
        self._log("PLANNING_ERROR", str(e))
        return {"needed_templates": ["base"], "primary_tools": [], "approach": f"fallback: {e}"}
```

**Success Criteria**:
- [ ] Planning call returns valid JSON
- [ ] Tool catalog cached per session
- [ ] <500ms overhead
- [ ] Graceful fallback

---

### Task 3.3: Implement Template Assembly ⏱️ 1h
**File**: `agent.py`

```python
def _assemble_prompt(self, plan: dict) -> str:
    """Compose system prompt from selected templates"""
    needed = set(plan.get("needed_templates", []))
    needed.add("base")  # Always include
    
    parts = []
    for key in ["base", "python_sandbox", "shell_ops", "mcp_tools"]:
        if key in needed and key in PROMPT_TEMPLATES:
            parts.append(PROMPT_TEMPLATES[key])
    
    if hasattr(self, 'system_context'):
        parts.append(self.system_context)
    
    return "\n\n".join(parts)
```

**Success Criteria**:
- [ ] Prompt assembly works
- [ ] Templates combined correctly
- [ ] Deterministic ordering

---

### Task 3.4: Integration into process_input ⏱️ 1h
**File**: `agent.py`

```python
def process_input(self, user_input: str, max_steps: int = None):
    # ... existing setup ...
    
    # PLANNING: Let LLM decide what guidance it needs
    plan = self._plan_execution(user_input)
    dynamic_prompt = self._assemble_prompt(plan)
    
    # Update system message
    self.message_history[0]["content"] = dynamic_prompt
    
    # Log
    self._log("DYNAMIC_PROMPT", json.dumps({
        "templates": plan.get("needed_templates", []),
        "length": len(dynamic_prompt),
        "approach": plan.get("approach", "")
    }))
    
    # Continue normal flow...
```

**Success Criteria**:
- [ ] Planning integrated before LLM call
- [ ] No breaking changes to execution
- [ ] Logging works

---

### Task 3.5: Testing Dynamic Prompting ⏱️ 2h
**File**: `tests/test_dynamic_prompting.py` (new)

```python
def test_planning_with_data_query():
    """Data query selects python_sandbox template"""
    agent = MiniAgent()
    plan = agent._plan_execution("Read data.csv and create a histogram")
    assert "python_sandbox" in plan.get("needed_templates", [])

def test_planning_with_shell_query():
    """Shell query selects shell_ops template"""
    agent = MiniAgent()
    plan = agent._plan_execution("Find all .py files")
    assert "shell_ops" in plan.get("needed_templates", [])

def test_planning_with_mcp_query():
    """MCP-related query selects mcp_tools template"""
    agent = MiniAgent()
    plan = agent._plan_execution("Generate a video of a sunset")
    assert "mcp_tools" in plan.get("needed_templates", [])
```

Manual validation:
- [ ] Simple query produces minimal prompt
- [ ] Data analysis includes sandbox guidance
- [ ] Sandbox code uses `os.environ['SANDBOX_PROJECT']`

**Success Criteria**:
- [ ] All tests pass
- [ ] Template selection makes sense
- [ ] Sandbox usage improves

---

## 🧪 Comprehensive Testing

### Regression Tests [2h]

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
- [ ] All existing tests in `tests/`

### Integration Tests [2h]

**MCP Server Mode**:
- [ ] Claude Desktop can discover our tools
- [ ] Claude can run shell commands via our server
- [ ] Cursor can use our sandbox
- [ ] Error handling works from external clients

**MCP Client Mode**:
- [ ] Our agent can call MiniMax tools
- [ ] Multimodal outputs saved correctly
- [ ] Multiple MCP servers work simultaneously

**Dynamic Prompting**:
- [ ] Correct templates selected for query types
- [ ] Prompt size reduced for simple queries
- [ ] Sandbox file I/O patterns appear when needed

---

## 📚 Documentation [2h]

### User Documentation
- [ ] `docs/mcp_server_usage.md` - How to use our tools from other agents
- [ ] `docs/mcp_client_usage.md` - How to add external MCP tools
- [ ] `docs/dynamic_prompting.md` - How planning system works
- [ ] Update `README.md` with MCP features

### Developer Documentation
- [ ] Architecture diagram
- [ ] How to add new MCP-compatible tools
- [ ] How to configure MCP servers
- [ ] Troubleshooting guide

---

## 📊 Success Metrics

### Quantitative
- **MCP Server**: 3+ clients can successfully use our tools
- **MCP Client**: Can consume 2+ external MCP servers
- **Dynamic Prompting**: 40-60% prompt reduction for simple queries
- **Performance**: <500ms planning overhead
- **Compatibility**: Works with Claude, Cursor, Cherry Studio

### Qualitative
- **Better sandbox usage**: Correct file I/O patterns from dynamic prompting
- **Ecosystem integration**: Part of MCP tool marketplace
- **User experience**: Seamless multimodal capabilities
- **Developer experience**: Easy to add new MCP servers

---

## ⚠️ Risk Mitigation

**Risk**: MCP protocol changes  
**Mitigation**: Use official SDK, follow semantic versioning, monitor MCP updates

**Risk**: MCP server connectivity issues  
**Mitigation**: Graceful degradation, continue with internal tools only

**Risk**: Planning adds latency  
**Mitigation**: Cache tool catalogs, async planning, <500ms target

**Risk**: Breaking existing functionality  
**Mitigation**: Comprehensive regression suite, progressive enhancement

---

## 🚀 Rollout Plan

1. **Phase 1 (MCP Server)**: 2 weeks
   - Develop and test locally
   - Document client setup
   - Beta test with Claude Desktop

2. **Phase 2 (MCP Client)**: 1 week  
   - Integrate MCP client
   - Test with MiniMax MCP
   - Add configuration support

3. **Phase 3 (Dynamic Prompting)**: 1 week
   - Implement planning
   - Test template selection
   - Optimize performance

4. **Testing & Documentation**: 1 week
   - Full regression testing
   - Integration testing
   - Complete documentation

**Total Timeline**: 4-5 weeks

---

## ✅ Approval Checklist

Before merging:
- [ ] All phases completed
- [ ] All regression tests pass
- [ ] MCP server works with 3+ clients
- [ ] MCP client works with 2+ servers
- [ ] Dynamic prompting optimizes sandbox usage
- [ ] Documentation complete
- [ ] Performance validated
- [ ] Code reviewed
- [ ] Approved by: _______________

---

**Estimated Total Effort**: 20-26 hours development + 6-8 hours testing/docs  
**Risk Level**: Medium-High (significant architectural change, new protocol)  
**Impact**: Transformative (joins MCP ecosystem, universal tool access)  
**Philosophy**: Open standards + community-driven + trust-based design
