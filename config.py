import os
from dotenv import load_dotenv

class Config:
    def __init__(self, api_key: str, model: str, max_tokens: int, temperature: float, hide_thinking: bool, max_steps: int):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.hide_thinking = hide_thinking
        self.max_steps = max_steps

def load_config() -> Config:
    load_dotenv()

    # Required settings
    api_key = os.getenv('MINIMAX_M2_API_KEY')
    if not api_key:
        raise ValueError("MINIMAX_M2_API_KEY is required")

    model = os.getenv('MINIMAX_MODEL')
    if not model:
        raise ValueError("MINIMAX_MODEL is required")

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

    return Config(api_key, model, max_tokens, temperature, hide_thinking, max_steps)
