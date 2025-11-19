#!/usr/bin/env python3
"""
Interactive configuration wizard for ai-terminal.

Creates .env files with secure API key input, provider selection,
and profile management for multiple agent backends.
"""

import os
import sys
import re
import ast
import getpass
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from openai import OpenAI


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}\n")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_info(text: str):
    """Print info message"""
    print(f"{Colors.BLUE}→ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def prompt_choice(question: str, choices: list, default: Optional[int] = None) -> int:
    """Prompt user to select from a list of choices"""
    print(f"\n{Colors.BOLD}{question}{Colors.END}")
    for i, choice in enumerate(choices, 1):
        default_marker = f" {Colors.GREEN}(default){Colors.END}" if default == i else ""
        print(f"  {i}. {choice}{default_marker}")
    
    while True:
        try:
            prompt = f"\nChoice [1-{len(choices)}]"
            if default:
                prompt += f" (default: {default})"
            prompt += ": "
            
            choice_input = input(prompt).strip()
            if not choice_input and default:
                return default
            
            choice = int(choice_input)
            if 1 <= choice <= len(choices):
                return choice
            print_error(f"Please enter a number between 1 and {len(choices)}")
        except ValueError:
            print_error("Please enter a valid number")
        except KeyboardInterrupt:
            print("\n")
            sys.exit(0)


def prompt_string(question: str, default: Optional[str] = None, required: bool = True) -> str:
    """Prompt user for a string input"""
    prompt = f"\n{Colors.BOLD}{question}{Colors.END}"
    if default:
        prompt += f" (default: {default})"
    prompt += ": "
    
    while True:
        try:
            value = input(prompt).strip()
            if not value and default:
                return default
            if not value and not required:
                return ""
            if not value and required:
                print_error("This field is required")
                continue
            return value
        except KeyboardInterrupt:
            print("\n")
            sys.exit(0)


def prompt_password(question: str, default: Optional[str] = None) -> str:
    """Prompt user for password/API key (masked input)"""
    if default:
        masked = default[:8] + "..." + default[-4:] if len(default) > 12 else "***"
        prompt = f"\n{Colors.BOLD}{question}{Colors.END}\n{Colors.GREEN}(press Enter to keep existing: {masked}){Colors.END}\n{Colors.YELLOW}(input will be hidden){Colors.END}: "
    else:
        prompt = f"\n{Colors.BOLD}{question}{Colors.END}\n{Colors.YELLOW}(input will be hidden){Colors.END}: "
    
    while True:
        try:
            value = getpass.getpass(prompt).strip()
            if not value and default:
                return default
            if not value and not default:
                print_error("API key is required")
                continue
            return value
        except KeyboardInterrupt:
            print("\n")
            sys.exit(0)


def prompt_int(question: str, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    """Prompt user for integer input"""
    prompt = f"\n{Colors.BOLD}{question}{Colors.END} (default: {default}): "
    
    while True:
        try:
            value = input(prompt).strip()
            if not value:
                return default
            
            int_value = int(value)
            if min_val is not None and int_value < min_val:
                print_error(f"Value must be at least {min_val}")
                continue
            if max_val is not None and int_value > max_val:
                print_error(f"Value must be at most {max_val}")
                continue
            return int_value
        except ValueError:
            print_error("Please enter a valid integer")
        except KeyboardInterrupt:
            print("\n")
            sys.exit(0)


def prompt_float(question: str, default: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    """Prompt user for float input"""
    prompt = f"\n{Colors.BOLD}{question}{Colors.END} (default: {default}): "
    
    while True:
        try:
            value = input(prompt).strip()
            if not value:
                return default
            
            float_value = float(value)
            if min_val is not None and float_value < min_val:
                print_error(f"Value must be at least {min_val}")
                continue
            if max_val is not None and float_value > max_val:
                print_error(f"Value must be at most {max_val}")
                continue
            return float_value
        except ValueError:
            print_error("Please enter a valid number")
        except KeyboardInterrupt:
            print("\n")
            sys.exit(0)


def prompt_bool(question: str, default: bool = True) -> bool:
    """Prompt user for yes/no input"""
    default_str = "Y/n" if default else "y/N"
    prompt = f"\n{Colors.BOLD}{question}{Colors.END} [{default_str}]: "
    
    while True:
        try:
            value = input(prompt).strip().lower()
            if not value:
                return default
            if value in ['y', 'yes', 'true', '1']:
                return True
            if value in ['n', 'no', 'false', '0']:
                return False
            print_error("Please enter y or n")
        except KeyboardInterrupt:
            print("\n")
            sys.exit(0)


def load_existing_env(filename: str = ".env") -> Dict[str, str]:
    """Load existing .env file if it exists"""
    filepath = Path(filename)
    config = {}
    
    if not filepath.exists():
        return config
    
    try:
        for line in filepath.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
        
        if config:
            print_success(f"Loaded existing configuration from {filename}")
    except Exception as e:
        print_warning(f"Could not load {filename}: {e}")
    
    return config


def discover_agent_backends() -> List[Tuple[str, str, str]]:
    """
    Discover supported agent backends by parsing config.py.
    Returns list of (agent_type, description, api_endpoint)
    """
    backends = []
    
    try:
        config_path = Path("config.py")
        if not config_path.exists():
            # Fallback to hardcoded list
            return [
                ("minimax", "MiniMax M2", "https://platform.minimaxi.com"),
                ("kimi2", "Kimi K2 (Moonshot AI)", "https://platform.moonshot.ai")
            ]
        
        config_code = config_path.read_text()
        
        # Parse if/elif blocks for agent_type
        minimax_match = re.search(r"elif agent_type == ['\"]minimax['\"]:", config_code)
        kimi_match = re.search(r"if agent_type == ['\"]kimi2['\"]:", config_code)
        custom_match = re.search(r"elif agent_type == ['\"]custom['\"]:", config_code)
        
        if minimax_match or "MINIMAX_M2_API_KEY" in config_code:
            backends.append(("minimax", "MiniMax M2", "https://platform.minimaxi.com"))
        
        if kimi_match or "KIMI_2_API_KEY" in config_code:
            backends.append(("kimi2", "Kimi K2 (Moonshot AI)", "https://platform.moonshot.ai"))
        
        # Don't show custom unless explicitly requested
        # if custom_match:
        #     backends.append(("custom", "Custom OpenAI-compatible endpoint", "custom"))
        
    except Exception as e:
        print_warning(f"Could not parse config.py: {e}")
        # Fallback
        backends = [
            ("minimax", "MiniMax M2", "https://platform.minimaxi.com"),
            ("kimi2", "Kimi K2 (Moonshot AI)", "https://platform.moonshot.ai")
        ]
    
    return backends


def test_connection(agent_type: str, api_key: str, model: str, base_url: str) -> bool:
    """Test API connection with minimal request"""
    print_info(f"Testing connection to {base_url}...")
    
    try:
        client = OpenAI(base_url=base_url, api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0.0
        )
        
        if response.choices and response.choices[0].message:
            print_success(f"Connection successful! Model: {model}")
            return True
        else:
            print_error("Connection failed: No response from API")
            return False
            
    except Exception as e:
        print_error(f"Connection failed: {e}")
        return False


def configure_minimax(existing: Dict[str, str]) -> Dict[str, str]:
    """Configure MiniMax M2 backend"""
    print_header("MiniMax M2 Configuration")
    
    config = {}
    config['AGENT_TYPE'] = 'minimax'
    
    # Check for existing API key
    existing_key = existing.get('MINIMAX_M2_API_KEY')
    if existing_key:
        print_success(f"Found existing API key: {existing_key[:8]}...{existing_key[-4:]}")
        use_existing = prompt_bool("Use this existing API key?", default=True)
        if use_existing:
            config['MINIMAX_M2_API_KEY'] = existing_key
        else:
            config['MINIMAX_M2_API_KEY'] = prompt_password("Enter your MiniMax API key")
    else:
        print_info("Get your API key from: https://platform.minimaxi.com")
        config['MINIMAX_M2_API_KEY'] = prompt_password("Enter your MiniMax API key")
    
    config['MINIMAX_MODEL'] = prompt_string("Model name", default=existing.get('MINIMAX_MODEL', 'MiniMax-M2'))
    
    return config


def configure_kimi2(existing: Dict[str, str]) -> Dict[str, str]:
    """Configure Kimi K2 backend"""
    print_header("Kimi K2 Configuration")
    
    config = {}
    config['AGENT_TYPE'] = 'kimi2'
    
    # Check for existing API key
    existing_key = existing.get('KIMI_2_API_KEY')
    if existing_key:
        print_success(f"Found existing API key: {existing_key[:8]}...{existing_key[-4:]}")
        use_existing = prompt_bool("Use this existing API key?", default=True)
        if use_existing:
            config['KIMI_2_API_KEY'] = existing_key
        else:
            config['KIMI_2_API_KEY'] = prompt_password("Enter your Kimi K2 API key")
    else:
        print_info("Get your API key from: https://platform.moonshot.ai")
        config['KIMI_2_API_KEY'] = prompt_password("Enter your Kimi K2 API key")
    
    config['KIMI_2_MODEL'] = prompt_string("Model name", default=existing.get('KIMI_2_MODEL', 'kimi-k2-turbo-preview'))
    config['KIMI_2_BASE_URL'] = prompt_string("Base URL", default=existing.get('KIMI_2_BASE_URL', 'https://api.moonshot.ai/v1'))
    
    return config


def configure_shared_options(existing: Dict[str, str]) -> Dict[str, str]:
    """Configure shared model parameters"""
    print_header("Model Parameters")
    
    config = {}
    
    print_info("These settings control model behavior")
    
    # Load existing or use defaults
    existing_tokens = int(existing.get('MAX_TOKENS', '1024'))
    existing_temp = float(existing.get('TEMPERATURE', '0.7'))
    existing_steps = int(existing.get('MAX_STEPS', '15'))
    existing_hide = existing.get('HIDE_THINKING', 'true').lower() == 'true'
    existing_raw = existing.get('SHOW_RAW_OUTPUT', 'false').lower() == 'true'
    
    config['MAX_TOKENS'] = str(prompt_int("Max tokens per response", default=existing_tokens, min_val=1, max_val=32768))
    config['TEMPERATURE'] = str(prompt_float("Temperature (0.0-2.0, higher = more creative)", default=existing_temp, min_val=0.0, max_val=2.0))
    config['MAX_STEPS'] = str(prompt_int("Max tool calling steps", default=existing_steps, min_val=1, max_val=50))
    config['HIDE_THINKING'] = 'true' if prompt_bool("Hide model thinking tags", default=existing_hide) else 'false'
    config['SHOW_RAW_OUTPUT'] = 'true' if prompt_bool("Show raw tool outputs", default=existing_raw) else 'false'
    
    return config


def write_env_file(config: Dict[str, str], filename: str = ".env"):
    """Write configuration to .env file, updating existing keys"""
    filepath = Path(filename)
    
    # Load existing configuration
    existing = load_existing_env(filename)
    
    # Update existing with new config
    existing.update(config)
    
    # Build .env content from merged config
    lines = []
    lines.append("# AI Terminal Configuration")
    lines.append(f"# Generated by setup.py\n")
    
    # Agent backend section
    agent_type = existing.get('AGENT_TYPE', 'minimax')
    lines.append("# Agent Backend")
    lines.append(f"AGENT_TYPE={agent_type}\n")
    
    # Backend-specific config - include all possible backends
    if 'MINIMAX_M2_API_KEY' in existing or agent_type == 'minimax':
        lines.append("# MiniMax M2 Settings")
        lines.append(f"MINIMAX_M2_API_KEY={existing.get('MINIMAX_M2_API_KEY', '')}")
        lines.append(f"MINIMAX_MODEL={existing.get('MINIMAX_MODEL', '')}\n")
    
    if 'KIMI_2_API_KEY' in existing or agent_type == 'kimi2':
        lines.append("# Kimi K2 Settings")
        lines.append(f"KIMI_2_API_KEY={existing.get('KIMI_2_API_KEY', '')}")
        lines.append(f"KIMI_2_MODEL={existing.get('KIMI_2_MODEL', '')}")
        lines.append(f"KIMI_2_BASE_URL={existing.get('KIMI_2_BASE_URL', '')}\n")
    
    if 'CUSTOM_API_KEY' in existing or agent_type == 'custom':
        lines.append("# Custom Backend Settings")
        lines.append(f"CUSTOM_API_KEY={existing.get('CUSTOM_API_KEY', '')}")
        lines.append(f"CUSTOM_MODEL={existing.get('CUSTOM_MODEL', '')}")
        lines.append(f"CUSTOM_BASE_URL={existing.get('CUSTOM_BASE_URL', '')}\n")
    
    # Shared parameters
    lines.append("# Model Parameters")
    lines.append(f"MAX_TOKENS={existing.get('MAX_TOKENS', '2048')}")
    lines.append(f"TEMPERATURE={existing.get('TEMPERATURE', '0.7')}")
    lines.append(f"AGENT_A_TEMPERATURE={existing.get('AGENT_A_TEMPERATURE', existing.get('TEMPERATURE', '0.7'))}")
    lines.append(f"AGENT_B_TEMPERATURE={existing.get('AGENT_B_TEMPERATURE', existing.get('TEMPERATURE', '0.7'))}")
    lines.append(f"MAX_STEPS={existing.get('MAX_STEPS', '5')}")
    lines.append(f"HIDE_THINKING={existing.get('HIDE_THINKING', 'true')}")
    lines.append(f"SHOW_RAW_OUTPUT={existing.get('SHOW_RAW_OUTPUT', 'false')}")
    
    # Write file
    try:
        filepath.write_text('\n'.join(lines) + '\n')
        print_success(f"Configuration saved to {filename}")
        return True
    except Exception as e:
        print_error(f"Failed to write {filename}: {e}")
        return False


def main():
    """Main setup wizard"""
    print_header("AI Terminal Setup Wizard")
    
    print(f"{Colors.BOLD}This wizard will help you configure your AI agent backend.{Colors.END}")
    print("You can create multiple profiles by saving to different .env files.")
    
    # Load existing configuration
    existing = load_existing_env(".env")
    
    # Discover available backends from config.py
    backends = discover_agent_backends()
    
    if not backends:
        print_error("No agent backends found in config.py")
        return
    
    # Determine default choice based on existing config
    default_choice = 1
    existing_type = existing.get('AGENT_TYPE')
    if existing_type:
        for i, (agent_type, _, _) in enumerate(backends, 1):
            if agent_type == existing_type:
                default_choice = i
                print_info(f"Current backend: {existing_type}")
                break
    
    # Step 1: Choose provider
    provider_choices = [f"{desc} ({url})" for _, desc, url in backends]
    provider_choice = prompt_choice(
        "Select your AI provider:",
        provider_choices,
        default=default_choice
    )
    
    # Get selected backend
    selected_backend = backends[provider_choice - 1]
    agent_type, _, _ = selected_backend
    
    # Step 2: Configure backend
    if agent_type == 'minimax':
        config = configure_minimax(existing)
        base_url = "https://api.minimax.io/v1"
        model = config['MINIMAX_MODEL']
        api_key = config['MINIMAX_M2_API_KEY']
    elif agent_type == 'kimi2':
        config = configure_kimi2(existing)
        base_url = config['KIMI_2_BASE_URL']
        model = config['KIMI_2_MODEL']
        api_key = config['KIMI_2_API_KEY']
    else:
        print_error(f"Unknown backend: {agent_type}")
        return
    
    # Step 3: Configure shared options
    shared_config = configure_shared_options(existing)
    config.update(shared_config)
    
    # Step 4: Test connection
    print_header("Connection Test")
    if prompt_bool("Test connection before saving?", default=True):
        if not test_connection(config['AGENT_TYPE'], api_key, model, base_url):
            if not prompt_bool("Connection failed. Save configuration anyway?", default=False):
                print_info("Setup cancelled")
                return
    
    # Step 5: Write configuration
    print_header("Save Configuration")
    
    if write_env_file(config, ".env"):
        print_header("Setup Complete!")
        print_success("Configuration saved to .env")
        
        print_info("\nYou can now run the agent:")
        print(f"  {Colors.CYAN}python main.py{Colors.END}")
        
        print_info("\nTo temporarily use a different backend:")
        print(f"  {Colors.CYAN}python main.py --agent kimi2{Colors.END}")
        print(f"  {Colors.CYAN}python main.py --agent minimax --temperature 0.9{Colors.END}")
        
        print("\n" + Colors.BOLD + "Enjoy using AI Terminal!" + Colors.END + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Setup cancelled{Colors.END}\n")
        sys.exit(0)
