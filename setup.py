#!/usr/bin/env python3
"""
Interactive configuration wizard for ai-terminal.

Creates .env files with secure API key input, provider selection,
and profile management for multiple agent backends.
"""

import os
import sys
import getpass
from pathlib import Path
from typing import Optional, Dict
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


def prompt_password(question: str) -> str:
    """Prompt user for password/API key (masked input)"""
    prompt = f"\n{Colors.BOLD}{question}{Colors.END}\n{Colors.YELLOW}(input will be hidden){Colors.END}: "
    
    while True:
        try:
            value = getpass.getpass(prompt).strip()
            if not value:
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


def configure_minimax() -> Dict[str, str]:
    """Configure MiniMax M2 backend"""
    print_header("MiniMax M2 Configuration")
    
    config = {}
    config['AGENT_TYPE'] = 'minimax'
    
    print_info("Get your API key from: https://platform.minimaxi.com")
    config['MINIMAX_M2_API_KEY'] = prompt_password("Enter your MiniMax API key")
    
    config['MINIMAX_MODEL'] = prompt_string("Model name", default="MiniMax-M2")
    
    return config


def configure_kimi2() -> Dict[str, str]:
    """Configure Kimi K2 backend"""
    print_header("Kimi K2 Configuration")
    
    config = {}
    config['AGENT_TYPE'] = 'kimi2'
    
    print_info("Get your API key from: https://platform.moonshot.ai")
    config['KIMI_2_API_KEY'] = prompt_password("Enter your Kimi K2 API key")
    
    config['KIMI_2_MODEL'] = prompt_string("Model name", default="kimi-k2-turbo-preview")
    config['KIMI_2_BASE_URL'] = prompt_string("Base URL", default="https://api.moonshot.ai/v1")
    
    return config


def configure_custom() -> Dict[str, str]:
    """Configure custom OpenAI-compatible backend"""
    print_header("Custom Backend Configuration")
    
    config = {}
    config['AGENT_TYPE'] = 'custom'
    
    config['CUSTOM_API_KEY'] = prompt_password("Enter your API key")
    config['CUSTOM_MODEL'] = prompt_string("Model name", required=True)
    config['CUSTOM_BASE_URL'] = prompt_string("Base URL (e.g., https://api.example.com/v1)", required=True)
    
    return config


def configure_shared_options() -> Dict[str, str]:
    """Configure shared model parameters"""
    print_header("Model Parameters")
    
    config = {}
    
    print_info("These settings control model behavior")
    config['MAX_TOKENS'] = str(prompt_int("Max tokens per response", default=1024, min_val=1, max_val=32768))
    config['TEMPERATURE'] = str(prompt_float("Temperature (0.0-2.0, higher = more creative)", default=0.7, min_val=0.0, max_val=2.0))
    config['MAX_STEPS'] = str(prompt_int("Max tool calling steps", default=15, min_val=1, max_val=50))
    config['HIDE_THINKING'] = 'true' if prompt_bool("Hide model thinking tags", default=True) else 'false'
    config['SHOW_RAW_OUTPUT'] = 'false' if prompt_bool("Show clean summaries (hide raw tool outputs)", default=True) else 'true'
    
    return config


def write_env_file(config: Dict[str, str], filename: str = ".env"):
    """Write configuration to .env file"""
    filepath = Path(filename)
    
    # Check if file exists
    if filepath.exists():
        print_warning(f"{filename} already exists")
        if not prompt_bool("Overwrite?", default=False):
            print_info("Configuration cancelled")
            return False
    
    # Build .env content
    lines = []
    lines.append("# AI Terminal Configuration")
    lines.append(f"# Generated by setup.py\n")
    
    # Agent backend section
    agent_type = config.get('AGENT_TYPE', 'minimax')
    lines.append("# Agent Backend")
    lines.append(f"AGENT_TYPE={agent_type}\n")
    
    # Backend-specific config
    if agent_type == 'minimax':
        lines.append("# MiniMax M2 Settings")
        lines.append(f"MINIMAX_M2_API_KEY={config['MINIMAX_M2_API_KEY']}")
        lines.append(f"MINIMAX_MODEL={config['MINIMAX_MODEL']}\n")
    elif agent_type == 'kimi2':
        lines.append("# Kimi K2 Settings")
        lines.append(f"KIMI_2_API_KEY={config['KIMI_2_API_KEY']}")
        lines.append(f"KIMI_2_MODEL={config['KIMI_2_MODEL']}")
        lines.append(f"KIMI_2_BASE_URL={config['KIMI_2_BASE_URL']}\n")
    elif agent_type == 'custom':
        lines.append("# Custom Backend Settings")
        lines.append(f"CUSTOM_API_KEY={config['CUSTOM_API_KEY']}")
        lines.append(f"CUSTOM_MODEL={config['CUSTOM_MODEL']}")
        lines.append(f"CUSTOM_BASE_URL={config['CUSTOM_BASE_URL']}\n")
    
    # Shared parameters
    lines.append("# Model Parameters")
    lines.append(f"MAX_TOKENS={config['MAX_TOKENS']}")
    lines.append(f"TEMPERATURE={config['TEMPERATURE']}")
    lines.append(f"MAX_STEPS={config['MAX_STEPS']}")
    lines.append(f"HIDE_THINKING={config['HIDE_THINKING']}")
    lines.append(f"SHOW_RAW_OUTPUT={config['SHOW_RAW_OUTPUT']}")
    
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
    
    # Step 1: Choose provider
    provider_choice = prompt_choice(
        "Select your AI provider:",
        [
            "MiniMax M2 (https://platform.minimaxi.com)",
            "Kimi K2 (Moonshot AI - https://platform.moonshot.ai)",
            "Custom OpenAI-compatible endpoint"
        ],
        default=1
    )
    
    # Step 2: Configure backend
    if provider_choice == 1:
        config = configure_minimax()
        base_url = "https://api.minimax.io/v1"
        model = config['MINIMAX_MODEL']
        api_key = config['MINIMAX_M2_API_KEY']
    elif provider_choice == 2:
        config = configure_kimi2()
        base_url = config['KIMI_2_BASE_URL']
        model = config['KIMI_2_MODEL']
        api_key = config['KIMI_2_API_KEY']
    else:
        config = configure_custom()
        base_url = config['CUSTOM_BASE_URL']
        model = config['CUSTOM_MODEL']
        api_key = config['CUSTOM_API_KEY']
    
    # Step 3: Configure shared options
    shared_config = configure_shared_options()
    config.update(shared_config)
    
    # Step 4: Test connection
    print_header("Connection Test")
    if prompt_bool("Test connection before saving?", default=True):
        if not test_connection(config['AGENT_TYPE'], api_key, model, base_url):
            if not prompt_bool("Connection failed. Save configuration anyway?", default=False):
                print_info("Setup cancelled")
                return
    
    # Step 5: Choose profile name
    print_header("Save Configuration")
    
    use_profile = prompt_bool("Save as named profile? (e.g., .env.minimax, .env.kimi)", default=False)
    
    if use_profile:
        agent_type = config['AGENT_TYPE']
        default_name = f".env.{agent_type}"
        profile_name = prompt_string(f"Profile filename", default=default_name)
        if not profile_name.startswith('.env'):
            profile_name = f".env.{profile_name}"
    else:
        profile_name = ".env"
    
    # Step 6: Write configuration
    if write_env_file(config, profile_name):
        print_header("Setup Complete!")
        print_success(f"Configuration saved to {profile_name}")
        
        if use_profile:
            print_info(f"\nTo use this profile, create a symlink:")
            print(f"  {Colors.CYAN}ln -sf {profile_name} .env{Colors.END}")
        else:
            print_info("\nYou can now run the agent:")
            print(f"  {Colors.CYAN}python main.py{Colors.END}")
        
        print("\n" + Colors.BOLD + "Enjoy using AI Terminal!" + Colors.END + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Setup cancelled{Colors.END}\n")
        sys.exit(0)
