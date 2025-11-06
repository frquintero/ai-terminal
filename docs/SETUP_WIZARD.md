# Setup Wizard Guide

The interactive setup wizard (`setup.py`) helps you configure AI Terminal with secure API key input, provider selection, and profile management.

## Quick Start

```bash
python setup.py
```

The wizard will guide you through:
1. **Provider selection** (MiniMax, Kimi K2, or custom)
2. **API key input** (masked for security)
3. **Model configuration** (max tokens, temperature, etc.)
4. **Connection testing** (optional)
5. **Profile management** (save as `.env` or named profile)

## Features

### 🔒 Secure API Key Input
- API keys are masked during input (like password prompts)
- Keys are never displayed in terminal output
- Stored securely in `.env` files

### 🎯 Provider Presets

**1. MiniMax M2**
- Base URL: `https://api.minimax.io/v1`
- Default model: `MiniMax-M2`
- Get API key: https://platform.minimaxi.com

**2. Kimi K2 (Moonshot AI)**
- Base URL: `https://api.moonshot.ai/v1`
- Default model: `kimi-k2-turbo-preview`
- Get API key: https://platform.moonshot.ai

**3. Custom OpenAI-Compatible**
- You provide: base URL, model name, API key
- Works with OpenRouter, local LLMs, etc.

### 📊 Model Parameters

The wizard configures:
- **MAX_TOKENS**: Response length (default: 1024)
- **TEMPERATURE**: Creativity level 0.0-2.0 (default: 0.7)
- **MAX_STEPS**: Max tool calling iterations (default: 15)
- **HIDE_THINKING**: Hide model reasoning tags (default: true)
- **SHOW_RAW_OUTPUT**: Display raw tool outputs (default: false)

### 🗂️ Profile Management

#### Single Configuration (.env)
```bash
python setup.py
# Choose "no" for named profile
# Creates: .env
```

#### Multiple Profiles
```bash
python setup.py
# Choose "yes" for named profile
# Suggested names: .env.minimax, .env.kimi, .env.custom
```

Switch between profiles:
```bash
# Use symbolic link
ln -sf .env.kimi .env

# Or copy
cp .env.minimax .env
```

### ✅ Connection Testing

The wizard can test your configuration before saving:
- Sends minimal API request (1 token)
- Verifies authentication
- Confirms model availability
- Optional (can skip and save anyway)

## Example Workflows

### First Time Setup (MiniMax)

```
$ python setup.py

============================================================
AI Terminal Setup Wizard
============================================================

Select your AI provider:
  1. MiniMax M2 (https://platform.minimaxi.com)
  2. Kimi K2 (Moonshot AI - https://platform.moonshot.ai)
  3. Custom OpenAI-compatible endpoint

Choice [1-3] (default: 1): 1

============================================================
MiniMax M2 Configuration
============================================================

→ Get your API key from: https://platform.minimaxi.com

Enter your MiniMax API key
(input will be hidden): ****************

Model name (default: MiniMax-M2): [Enter]

============================================================
Model Parameters
============================================================

→ These settings control model behavior

Max tokens per response (default: 1024): [Enter]
Temperature (0.0-2.0, higher = more creative) (default: 0.7): [Enter]
Max tool calling steps (default: 15): [Enter]
Hide model thinking tags [Y/n]: [Enter]
Show clean summaries (hide raw tool outputs) [Y/n]: [Enter]

============================================================
Connection Test
============================================================

Test connection before saving? [Y/n]: y
→ Testing connection to https://api.minimax.io/v1...
✓ Connection successful! Model: MiniMax-M2

============================================================
Save Configuration
============================================================

Save as named profile? (e.g., .env.minimax, .env.kimi) [y/N]: n

✓ Configuration saved to .env

============================================================
Setup Complete!
============================================================

✓ Configuration saved to .env

→ You can now run the agent:
  python main.py

Enjoy using AI Terminal!
```

### Multi-Profile Setup (Kimi K2)

```bash
# Create Kimi profile
python setup.py
# Select option 2 (Kimi K2)
# Choose "yes" for named profile
# Name it: .env.kimi

# Create MiniMax profile
python setup.py
# Select option 1 (MiniMax)
# Choose "yes" for named profile  
# Name it: .env.minimax

# Switch between profiles
ln -sf .env.kimi .env       # Use Kimi
ln -sf .env.minimax .env    # Use MiniMax
```

### Custom Endpoint (OpenRouter)

```
Select your AI provider:
  1. MiniMax M2
  2. Kimi K2
  3. Custom OpenAI-compatible endpoint

Choice [1-3]: 3

============================================================
Custom Backend Configuration
============================================================

Enter your API key: ******************
Model name: moonshotai/kimi-k2-0905
Base URL (e.g., https://api.example.com/v1): https://openrouter.ai/api/v1
```

## Troubleshooting

### Connection Test Fails

**Invalid Authentication (401)**
- Check API key is correct
- Verify key is active (not expired/revoked)
- Ensure you're using the right provider's key

**Model Not Found (404)**
- Check model name spelling
- Verify model is available for your account
- Try default model name from wizard

**Network Error**
- Check internet connection
- Verify base URL is accessible
- Check firewall/proxy settings

### File Permission Errors

If `.env` file can't be created:
```bash
# Check directory permissions
ls -la .

# Ensure you own the directory
sudo chown -R $USER:$USER .
```

### Override Existing Configuration

The wizard warns before overwriting `.env`:
```
⚠ .env already exists
Overwrite? [y/N]:
```

Backup existing config:
```bash
cp .env .env.backup
python setup.py
```

## Manual Configuration

If you prefer not to use the wizard, edit `.env` directly:

```bash
# Copy template
cp .env.example .env

# Edit with your preferred editor
nano .env
```

See `.env.example` for all available options.

## Security Notes

- ✅ API keys are masked during input
- ✅ `.env` files are in `.gitignore` (not committed)
- ⚠️ Keep `.env` files private (contain secrets)
- ⚠️ Don't share `.env` in public repositories
- ⚠️ Use environment-specific profiles for production

## Advanced Usage

### Environment Variable Override

Override config at runtime:
```bash
AGENT_TYPE=kimi2 KIMI_2_API_KEY=$KEY python main.py
```

### Programmatic Configuration

```python
from config import load_config

# Loads from .env automatically
config = load_config()

print(config.agent_type)  # 'minimax', 'kimi2', or 'custom'
print(config.model)       # Model name
print(config.base_url)    # API endpoint
```

### Docker/CI Configuration

Use `.env` files with Docker:
```dockerfile
# Dockerfile
COPY .env /app/.env
ENV $(cat /app/.env | xargs)
```

Or pass as build args:
```bash
docker build --build-arg AGENT_TYPE=kimi2 \
             --build-arg KIMI_2_API_KEY=$KEY \
             -t ai-terminal .
```
