import os
from dotenv import load_dotenv

class Config:
    def __init__(self, api_key: str, model: str, base_url: str, agent_type: str, max_tokens: int, temperature: float, hide_thinking: bool, max_steps: int, show_raw_output: bool, raw_output_max_chars: int):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.agent_type = agent_type
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.hide_thinking = hide_thinking
        self.max_steps = max_steps
        self.show_raw_output = show_raw_output
        self.raw_output_max_chars = raw_output_max_chars

def load_config() -> Config:
    load_dotenv()

    # Agent backend selection (default: minimax for backward compatibility)
    agent_type = os.getenv('AGENT_TYPE', 'minimax').lower()
    
    # Load agent-specific configuration
    if agent_type == 'kimi2':
        api_key = os.getenv('KIMI_2_API_KEY')
        if not api_key:
            raise ValueError("KIMI_2_API_KEY is required when AGENT_TYPE=kimi2")
        model = os.getenv('KIMI_2_MODEL', 'kimi-k2-turbo-preview')
        base_url = os.getenv('KIMI_2_BASE_URL', 'https://api.moonshot.ai/v1')
    elif agent_type == 'minimax':
        api_key = os.getenv('MINIMAX_M2_API_KEY')
        if not api_key:
            raise ValueError("MINIMAX_M2_API_KEY is required")
        model = os.getenv('MINIMAX_MODEL')
        if not model:
            raise ValueError("MINIMAX_MODEL is required")
        base_url = 'https://api.minimax.io/v1'
    elif agent_type == 'custom':
        # Custom OpenAI-compatible endpoint
        api_key = os.getenv('CUSTOM_API_KEY')
        if not api_key:
            raise ValueError("CUSTOM_API_KEY is required when AGENT_TYPE=custom")
        model = os.getenv('CUSTOM_MODEL')
        if not model:
            raise ValueError("CUSTOM_MODEL is required when AGENT_TYPE=custom")
        base_url = os.getenv('CUSTOM_BASE_URL')
        if not base_url:
            raise ValueError("CUSTOM_BASE_URL is required when AGENT_TYPE=custom")
    else:
        raise ValueError(f"Invalid AGENT_TYPE: {agent_type}. Must be 'minimax', 'kimi2', or 'custom'")

    # Optional with defaults
    max_tokens_str = os.getenv('MAX_TOKENS', '1024')
    try:
        max_tokens = int(max_tokens_str)
    except ValueError:
        raise ValueError("MAX_TOKENS must be an integer")

    temperature_str = os.getenv('TEMPERATURE', '0.7')
    try:
        temperature = float(temperature_str)
    except ValueError:
        raise ValueError("TEMPERATURE must be a float")

    hide_thinking_str = os.getenv('HIDE_THINKING', 'true')
    if hide_thinking_str.lower() in ('true', '1', 'yes'):
        hide_thinking = True
    elif hide_thinking_str.lower() in ('false', '0', 'no'):
        hide_thinking = False
    else:
        raise ValueError("HIDE_THINKING must be true or false")

    max_steps_str = os.getenv('MAX_STEPS', '15')
    try:
        max_steps = int(max_steps_str)
    except ValueError:
        raise ValueError("MAX_STEPS must be an integer")

    show_raw_output_str = os.getenv('SHOW_RAW_OUTPUT', 'false')
    if show_raw_output_str.lower() in ('true', '1', 'yes'):
        show_raw_output = True
    elif show_raw_output_str.lower() in ('false', '0', 'no'):
        show_raw_output = False
    else:
        raise ValueError("SHOW_RAW_OUTPUT must be true or false")

    raw_output_max_chars_str = os.getenv('RAW_OUTPUT_MAX_CHARS', '4000')
    try:
        raw_output_max_chars = int(raw_output_max_chars_str)
    except ValueError:
        raise ValueError("RAW_OUTPUT_MAX_CHARS must be an integer")

    return Config(api_key, model, base_url, agent_type, max_tokens, temperature, hide_thinking, max_steps, show_raw_output, raw_output_max_chars)
