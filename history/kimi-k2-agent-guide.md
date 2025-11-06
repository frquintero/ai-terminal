# Kimi K2 Mini Agent Integration Guide

## Overview
Kimi K2 is a trillion-parameter MoE (Mixture of Experts) model from Moonshot AI with:
- 32B activated parameters, 1T total parameters
- 128K context window
- Native tool use / function calling support
- Strong code generation and reasoning capabilities
- OpenAI/Anthropic-compatible API

**API Platform**: https://platform.moonshot.ai

---

## Integration Template for ai-terminal

### 1. Environment Configuration

Add to `.env`:
```bash
# Kimi K2 Configuration
KIMI_2_API_KEY=sk-xxxxx  # From platform.moonshot.ai
KIMI_2_MODEL=kimi-k2-turbo-preview
KIMI_2_BASE_URL=https://api.moonshot.ai/v1
```

### 2. Config Loader Pattern

Update `config.py` to support multiple agent backends:

```python
# In load_config():
agent_type = os.getenv('AGENT_TYPE', 'minimax')  # minimax | kimi2

if agent_type == 'kimi2':
    api_key = os.getenv('KIMI_2_API_KEY')
    model = os.getenv('KIMI_2_MODEL', 'kimi-k2-turbo-preview')
    base_url = os.getenv('KIMI_2_BASE_URL', 'https://api.moonshot.ai/v1')
elif agent_type == 'minimax':
    api_key = os.getenv('MINIMAX_M2_API_KEY')
    model = os.getenv('MINIMAX_MODEL', 'MiniMax-M2')
    base_url = 'https://api.minimax.io/v1'
```

### 3. Agent Class Factory

Current approach (single class):
```python
# agent.py line 21-24
self.client = openai.OpenAI(
    base_url="https://api.minimax.io/v1",
    api_key=self.config.api_key
)
```

Flexible approach:
```python
# agent.py line 21-24
self.client = openai.OpenAI(
    base_url=self.config.base_url,
    api_key=self.config.api_key
)
```

### 4. Tool/Function Calling Compatibility

Kimi K2 supports OpenAI-compatible function calling:
- Uses same `tools` parameter format
- Returns `tool_calls` in response
- Expects `tool` role messages in history

**No changes needed** - existing tool handling (lines 235-351 in agent.py) works as-is.

### 5. Model-Specific Considerations

**System Prompt**:
- Kimi K2 handles longer prompts well (128K context)
- Strong with shell/terminal tasks
- May need adjusted temperature (test 0.5-0.8)

**Token Limits**:
- Default MAX_TOKENS=1024 may be low for Kimi K2
- Consider 2048-4096 for complex tool chains

**Step Limits**:
- Kimi K2 is agentic by design
- May handle higher MAX_STEPS (20-30) efficiently

---

## Quick Start Templates

### Option A: Simple Environment Switch
```bash
# .env
AGENT_TYPE=kimi2
KIMI_2_API_KEY=sk-or-v1-xxxxx
KIMI_2_MODEL=kimi-k2-instruct
MAX_TOKENS=2048
MAX_STEPS=20
```

### Option B: Dedicated Kimi Profile
Create `.env.kimi`:
```bash
AGENT_TYPE=kimi2
KIMI_2_API_KEY=sk-or-v1-xxxxx
KIMI_2_MODEL=kimi-k2-instruct
KIMI_2_BASE_URL=https://api.moonshot.ai/v1
MAX_TOKENS=2048
TEMPERATURE=0.6
MAX_STEPS=20
HIDE_THINKING=true
SHOW_RAW_OUTPUT=false
```

Run with: `python main.py --env .env.kimi`

---

## API Key Sources

**✅ TESTED & VERIFIED:**

1. **Moonshot Platform** (direct, RECOMMENDED):
   - Sign up: https://platform.moonshot.ai
   - Base URL: `https://api.moonshot.ai/v1`
   - Model name: `kimi-k2-turbo-preview` (or `kimi-k2-0905-preview`)
   - API key format: starts with `sk-`
   - Free tier available, faster response times

2. **OpenRouter** (aggregator alternative):
   - https://openrouter.ai
   - Model name: `moonshotai/kimi-k2-0905`
   - Base URL: `https://openrouter.ai/api/v1`
   - Requires separate OpenRouter API key (not Moonshot key)

---

## Testing Checklist

- [ ] API key authentication works
- [ ] Function calling with tools (run_command, read_file, etc.)
- [ ] Multi-step tool chains (3+ tool calls)
- [ ] Long context handling (large file reads)
- [ ] Error handling for malformed tool calls
- [ ] History trimming with 128K context
- [ ] Interactive tools (run_interactive)
- [ ] Python sandbox integration

---

## Performance Notes

Based on benchmarks:
- **Strong**: Code generation, multi-step reasoning, long context
- **Agentic**: Native tool use, better at complex workflows
- **Cost**: ~5x cheaper than Claude Sonnet 4 (via OpenRouter)
- **Speed**: Comparable to GPT-4 class models

---

## Standalone Testing (REQUIRED Before Integration)

**Critical**: Build and run `test_kimi2_agent.py` to verify full functionality BEFORE integrating into main codebase.

### Test Structure

```python
# tests/test_kimi2_agent.py
import os
from openai import OpenAI

# Test 1: API Connection
# - Initialize OpenAI client with Kimi K2 credentials
# - Verify authentication succeeds

# Test 2: Basic Chat Completion
# - Send simple message: "What is 2+2?"
# - Verify response is received and reasonable

# Test 3: Function Calling with Tools
# - Provide tool schemas for: run_command, read_file, write_file
# - Test prompt: "Create a file test.txt with content 'hello', read it back, and show the date"
# - Verify:
#   * Model generates tool calls (write_file, read_file, run_command)
#   * Tool call JSON is properly formatted
#   * Multi-step reasoning works (2-3 tool calls in sequence)
#   * Final response synthesizes tool results

# Test 4: Error Handling
# - Invalid API key
# - Malformed tool call
# - Network timeout
```

### Success Criteria

✅ All 4 tests pass  
✅ Function calling returns valid tool_calls array  
✅ Multi-step workflow completes (write → read → command)  
✅ Response quality matches or exceeds MiniMax M2  
✅ No unexpected API errors or rate limits  

**Only proceed with config.py/agent.py integration after tests pass.**

---

## Next Steps

1. **✅ BLOCKER**: Run standalone test suite (test_kimi2_agent.py)
2. **Minimal changes**: Update config.py to accept base_url parameter
3. **Add agent selector**: Create setup.py with interactive menu
4. **Test thoroughly**: Verify tool calling with Kimi K2 API in full agent
5. **Document pricing**: Add cost comparison to README
6. **Profile switcher**: Support .env.minimax, .env.kimi, etc.
