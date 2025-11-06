#!/usr/bin/env python3
"""
List all available Kimi/Moonshot AI models via API.

Usage:
    python utils/list_kimi_models.py

Environment:
    KIMI_2_API_KEY - Your Moonshot AI API key
    or
    MOONSHOT_API_KEY - Alternative env var name

Output:
    Displays all available models with details:
    - Model ID
    - Created date
    - Owned by
    - Recommended for agent use (if applicable)
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# Color codes for terminal output
class Colors:
    BOLD = '\033[1m'
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'


def get_api_key():
    """Get API key from environment"""
    load_dotenv()
    
    # Try both env var names
    api_key = os.getenv('KIMI_2_API_KEY') or os.getenv('MOONSHOT_API_KEY')
    
    if not api_key:
        print(f"{Colors.RED}Error: KIMI_2_API_KEY or MOONSHOT_API_KEY not set{Colors.END}")
        print("\nSet it with:")
        print(f"  export KIMI_2_API_KEY=sk-your_key_here")
        print("\nOr add to .env file:")
        print(f"  KIMI_2_API_KEY=sk-your_key_here")
        sys.exit(1)
    
    return api_key


def format_timestamp(timestamp):
    """Format Unix timestamp to readable date"""
    try:
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return str(timestamp)


def is_recommended_model(model_id):
    """Determine if model is recommended for agent use"""
    # Models with 'turbo' are typically production-ready
    # Models with 'preview' are experimental but may have newer features
    # Prefer: turbo > preview > base
    
    if 'turbo' in model_id.lower():
        return True, "Production-ready, optimized for speed"
    elif 'preview' in model_id.lower():
        return True, "Preview version, may have newer features"
    elif 'k2' in model_id.lower():
        return True, "Kimi K2 model family"
    else:
        return False, "Older generation model"


def main():
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}Moonshot AI / Kimi Model Listing{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}\n")
    
    # Get API key
    api_key = get_api_key()
    masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
    print(f"API Key: {masked_key}")
    print(f"Base URL: https://api.moonshot.ai/v1\n")
    
    # Initialize client
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.moonshot.ai/v1"
        )
    except Exception as e:
        print(f"{Colors.RED}Error initializing client: {e}{Colors.END}")
        sys.exit(1)
    
    # List models
    try:
        print(f"{Colors.BOLD}Fetching available models...{Colors.END}\n")
        model_list = client.models.list()
        model_data = model_list.data
    except Exception as e:
        print(f"{Colors.RED}Error fetching models: {e}{Colors.END}")
        sys.exit(1)
    
    if not model_data:
        print(f"{Colors.YELLOW}No models found{Colors.END}")
        return
    
    print(f"{Colors.BOLD}Found {len(model_data)} model(s):{Colors.END}\n")
    
    # Sort models by ID (newer models typically have later names)
    sorted_models = sorted(model_data, key=lambda m: m.id)
    
    # Track recommended models
    recommended = []
    
    for i, model in enumerate(sorted_models, 1):
        model_id = model.id
        created = getattr(model, 'created', None)
        owned_by = getattr(model, 'owned_by', 'unknown')
        
        is_rec, reason = is_recommended_model(model_id)
        
        print(f"{Colors.BOLD}[{i}] {model_id}{Colors.END}")
        
        if created:
            print(f"    Created: {format_timestamp(created)}")
        if owned_by:
            print(f"    Owned by: {owned_by}")
        
        if is_rec:
            print(f"    {Colors.GREEN}✓ RECOMMENDED{Colors.END}: {reason}")
            recommended.append((model_id, reason))
        else:
            print(f"    {Colors.YELLOW}○ {reason}{Colors.END}")
        
        print()
    
    # Summary
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}Recommendation Summary for AI Terminal Agent{Colors.END}\n")
    
    # Categorize models
    kimi_k2_models = [m.id for m in sorted_models if 'kimi-k2' in m.id.lower()]
    turbo_models = [m for m in kimi_k2_models if 'turbo' in m.lower()]
    thinking_models = [m for m in kimi_k2_models if 'thinking' in m.lower()]
    
    if kimi_k2_models:
        print(f"{Colors.BOLD}Kimi K2 Models (Latest Generation):{Colors.END}\n")
        
        # Best for general agent use
        if turbo_models:
            print(f"{Colors.GREEN}✓ Best for Agent Use (Speed + Quality):{Colors.END}")
            for model in turbo_models:
                marker = " ← CURRENT" if model == os.getenv('KIMI_2_MODEL', 'kimi-k2-turbo-preview') else ""
                print(f"    • {model}{marker}")
            print()
        
        # Best for complex reasoning
        if thinking_models:
            print(f"{Colors.CYAN}○ Best for Complex Reasoning:{Colors.END}")
            for model in thinking_models:
                print(f"    • {model}")
            print(f"    {Colors.YELLOW}Note: Thinking models expose reasoning steps (slower){Colors.END}")
            print()
        
        # Preview/experimental
        preview_k2 = [m for m in kimi_k2_models if 'preview' in m.lower() and 'thinking' not in m.lower()]
        if preview_k2:
            print(f"{Colors.YELLOW}○ Preview/Experimental Versions:{Colors.END}")
            for model in preview_k2:
                print(f"    • {model}")
            print()
    
    # Highlight the best choice
    best_choice = 'kimi-k2-turbo-preview'  # Current default
    if 'kimi-k2-thinking-turbo' in kimi_k2_models:
        thinking_turbo_choice = 'kimi-k2-thinking-turbo'
    else:
        thinking_turbo_choice = None
    
    print(f"{Colors.BOLD}{Colors.GREEN}RECOMMENDED FOR AI TERMINAL:{Colors.END}")
    print(f"  {Colors.BOLD}{best_choice}{Colors.END}")
    print(f"  Balanced speed and quality for agent tasks")
    
    if thinking_turbo_choice:
        print(f"\n{Colors.BOLD}{Colors.CYAN}ALTERNATIVE (Complex Tasks):{Colors.END}")
        print(f"  {Colors.BOLD}{thinking_turbo_choice}{Colors.END}")
        print(f"  Better reasoning, shows thinking process (slower)")
    
    print()
    
    # Current configuration check
    print(f"{Colors.BOLD}Current ai-terminal configuration:{Colors.END}")
    current_model = os.getenv('KIMI_2_MODEL', 'kimi-k2-turbo-preview')
    print(f"  KIMI_2_MODEL={current_model}")
    
    if any(current_model == m for m, _ in recommended):
        print(f"  {Colors.GREEN}✓ Using recommended model{Colors.END}")
    elif current_model in [m.id for m in sorted_models]:
        print(f"  {Colors.YELLOW}⚠ Model exists but may not be optimal{Colors.END}")
    else:
        print(f"  {Colors.RED}✗ Model not found in API listing!{Colors.END}")
        print(f"  {Colors.RED}  Update KIMI_2_MODEL in .env or config.py{Colors.END}")
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Interrupted{Colors.END}\n")
        sys.exit(0)
