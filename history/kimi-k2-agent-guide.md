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
KIMI_2_API_KEY=sk-or-v1-xxxxx  # From platform.moonshot.ai or openrouter.ai
KIMI_2_MODEL=kimi-k2-instruct
KIMI_2_BASE_URL=https://api.moonshot.ai/v1  # Or OpenRouter: https://openrouter.ai/api/v1
```

### 2. Config Loader Pattern

Update `config.py` to support multiple agent backends:

```python
# In load_config():
agent_type = os.getenv('AGENT_TYPE', 'minimax')  # minimax | kimi2

if agent_type == 'kimi2':
    api_key = os.getenv('KIMI_2_API_KEY')
    model = os.getenv('KIMI_2_MODEL', 'kimi-k2-instruct')
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

1. **Moonshot Platform** (direct):
   - https://platform.moonshot.ai
   - Create account → Generate API key (starts with `sk-or-v1-`)
   - Potentially faster and cheaper

2. **OpenRouter** (aggregator):
   - https://openrouter.ai
   - Single API for multiple models
   - Model name: `moonshotai/kimi-k2-instruct`
   - Base URL: `https://openrouter.ai/api/v1`

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

## Next Steps

1. **Minimal changes**: Just update config.py to accept base_url parameter
2. **Add agent selector**: Create setup.py with interactive menu
3. **Test thoroughly**: Verify tool calling with Kimi K2 API
4. **Document pricing**: Add cost comparison to README
5. **Profile switcher**: Support .env.minimax, .env.kimi, etc.
