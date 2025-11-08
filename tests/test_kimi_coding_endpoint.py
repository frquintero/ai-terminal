#!/usr/bin/env python3
"""
Test Kimi For Coding endpoint.
Tests the https://api.kimi.com/coding/v1 platform endpoint.

Usage:
    python test_kimi_coding_endpoint.py

Environment variables (from .env):
    KIMI_2_API_KEY - Your Moonshot API key (should work for coding endpoint too)
"""

import os
import sys
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configuration
API_KEY = os.getenv("KIMI_2_API_KEY")
CODING_BASE_URL = "https://api.kimi.com/coding/v1"

if not API_KEY:
    print("❌ ERROR: KIMI_2_API_KEY not found in .env file")
    print("\nPlease set your API key:")
    print("  1. Get key from: https://platform.moonshot.cn/console/api-keys")
    print("  2. Add to .env file: KIMI_2_API_KEY=[REDACTED:api-key]")
    exit(1)

print(f"🔗 Testing Kimi For Coding Endpoint")
print(f"   Base URL: {CODING_BASE_URL}")
print(f"   API Key: {API_KEY[:10]}...{API_KEY[-4:]}")
print()

try:
    client = OpenAI(
        api_key=API_KEY,
        base_url=CODING_BASE_URL,
    )
    
    # First: List available models
    print("📋 Fetching available models from coding endpoint...\n")
    models = client.models.list()
    
    if not models.data:
        print("⚠️  No models found at coding endpoint")
        exit(1)
    
    print(f"✅ Found {len(models.data)} model(s):\n")
    for model in models.data:
        print(f"   • {model.id}")
    
    # Try using first model
    if models.data:
        first_model = models.data[0].id
        print(f"\n📝 Testing chat completion with: {first_model}")
        print()
        
        response = client.chat.completions.create(
            model=first_model,
            messages=[
                {"role": "user", "content": "Write a simple Python function that adds two numbers"},
            ],
            temperature=0.6,
            stream=True,
        )
        
        print("Response:")
        collected_messages = []
        for idx, chunk in enumerate(response):
            chunk_message = chunk.choices[0].delta
            if not chunk_message.content:
                continue
            collected_messages.append(chunk_message)
            # Show progressive output
            if idx % 5 == 0:
                print(f"{''.join([m.content for m in collected_messages])}", end='', flush=True)
        
        # Print final complete message
        full_response = ''.join([m.content for m in collected_messages])
        print(f"\n{full_response}")
        
        print(f"\n✅ SUCCESS: Kimi For Coding endpoint is working!")
        print(f"   Model: {first_model}")
        print(f"   Received {len(collected_messages)} chunks")
        print(f"   Total length: {len(full_response)} characters")
    
except Exception as e:
    print(f"\n❌ ERROR: Connection to Kimi For Coding endpoint failed")
    print(f"   {type(e).__name__}: {e}")
    print("\nTroubleshooting:")
    print("  1. Check API key is valid at https://platform.moonshot.cn/console/api-keys")
    print("  2. Your API key may not have access to the coding endpoint")
    print("  3. Verify endpoint: https://api.kimi.com/coding/v1")
    print("\nFallback: Use standard Moonshot endpoint (https://api.moonshot.ai/v1)")
    exit(1)
