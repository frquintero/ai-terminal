import os
from dotenv import load_dotenv

class Config:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        agent_type: str,
        max_tokens: int,
        temperature: float,
        hide_thinking: bool,
        max_steps: int,
        show_raw_output: bool,
        raw_output_max_chars: int,
        use_event_memory: bool,
        event_log_retention_days: int,
        event_memory_max_events: int,
        event_memory_max_chars: int,
        artifact_threshold_bytes: int,
        save_llm_traces: bool,
    ):
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
        self.use_event_memory = use_event_memory
        self.event_log_retention_days = event_log_retention_days
        self.event_memory_max_events = event_memory_max_events
        self.event_memory_max_chars = event_memory_max_chars
        self.artifact_threshold_bytes = artifact_threshold_bytes
        self.save_llm_traces = save_llm_traces

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
        # Accept both CUSTOM_* and OPENAI_* prefixes (prefer CUSTOM)
        api_key = os.getenv('CUSTOM_API_KEY') or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("CUSTOM_API_KEY or OPENAI_API_KEY is required when AGENT_TYPE=custom")
        model = os.getenv('CUSTOM_MODEL') or os.getenv('OPENAI_MODEL') or os.getenv('MODEL')
        if not model:
            raise ValueError("CUSTOM_MODEL, OPENAI_MODEL, or MODEL is required when AGENT_TYPE=custom")
        base_url = os.getenv('CUSTOM_BASE_URL') or os.getenv('OPENAI_BASE_URL')
        if not base_url:
            raise ValueError("CUSTOM_BASE_URL or OPENAI_BASE_URL is required when AGENT_TYPE=custom")
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

    use_event_memory = os.getenv('USE_EVENT_MEMORY', '1').lower() in ('1', 'true', 'yes')

    save_llm_traces_str = os.getenv('SAVE_LLM_TRACES', 'true').lower()
    if save_llm_traces_str in ('true', '1', 'yes'):
        save_llm_traces = True
    elif save_llm_traces_str in ('false', '0', 'no'):
        save_llm_traces = False
    else:
        raise ValueError("SAVE_LLM_TRACES must be true or false")

    def _parse_int_env(name: str, default: str) -> int:
        value = os.getenv(name, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be an integer")

    event_log_retention_days = _parse_int_env('EVENT_LOG_RETENTION_DAYS', '7')
    event_memory_max_events = _parse_int_env('EVENT_MEMORY_MAX_EVENTS', '40')
    event_memory_max_chars = _parse_int_env('EVENT_MEMORY_MAX_CHARS', '6000')
    artifact_threshold_bytes = _parse_int_env('EVENT_MEMORY_ARTIFACT_THRESHOLD', '8192')

    return Config(
        api_key,
        model,
        base_url,
        agent_type,
        max_tokens,
        temperature,
        hide_thinking,
        max_steps,
        show_raw_output,
        raw_output_max_chars,
        use_event_memory,
        event_log_retention_days,
        event_memory_max_events,
        event_memory_max_chars,
        artifact_threshold_bytes,
        save_llm_traces,
    )
