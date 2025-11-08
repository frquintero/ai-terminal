#!/usr/bin/env python3
"""
Quick connectivity test for Kimi API.
Tests basic streaming chat completion to verify API key and endpoint work.

Usage:
    python test_kimi_connection.py

Environment variables (from .env):
    KIMI_2_API_KEY - Your Moonshot API key
    KIMI_2_BASE_URL - API endpoint (default: https://api.moonshot.cn/v1)
    KIMI_2_MODEL - Model name (default: kimi-k2-turbo-preview)
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configuration
API_KEY = os.getenv("KIMI_2_API_KEY")
BASE_URL = os.getenv("KIMI_2_BASE_URL", "https://api.moonshot.ai/v1")
MODEL = os.getenv("KIMI_2_MODEL", "kimi-k2-turbo-preview")

if not API_KEY:
    print("❌ ERROR: KIMI_2_API_KEY not found in .env file")
    print("\nPlease set your API key:")
    print("  1. Get key from: https://platform.moonshot.cn/console/api-keys")
    print("  2. Add to .env file: KIMI_2_API_KEY=sk-xxxxx")
    exit(1)

print(f"🔗 Testing Kimi API Connection")
print(f"   Base URL: {BASE_URL}")
print(f"   Model: {MODEL}")
print(f"   API Key: {API_KEY[:10]}...{API_KEY[-4:]}")
print()

try:
    client = OpenAI(
        api_key=API_KEY,
        base_url=BASE_URL,
    )
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are Kimi, an AI assistant provided by Moonshot AI. You excel at conversing in Chinese and English. You provide users with safe, helpful, and accurate responses. You refuse to answer any questions related to terrorism, racism, or explicit content. Moonshot AI is a proper noun and should not be translated into other languages.",
            },
            {"role": "user", "content": "Write a simple Python function that adds two numbers"},
        ],
        temperature=0.6,
        stream=True,
    )
    
    print("📝 Response:")
    collected_messages = []
    for idx, chunk in enumerate(response):
        chunk_message = chunk.choices[0].delta
        if not chunk_message.content:
            continue
        collected_messages.append(chunk_message)
        # Show progressive output
        if idx % 5 == 0:  # Print every 5th chunk to reduce noise
            print(f"{''.join([m.content for m in collected_messages])}", end='', flush=True)
    
    # Print final complete message
    full_response = ''.join([m.content for m in collected_messages])
    print(f"\n{full_response}")
    
    print("\n✅ SUCCESS: Kimi API connection working!")
    print(f"   Received {len(collected_messages)} chunks")
    print(f"   Total length: {len(full_response)} characters")
    
except Exception as e:
    print(f"\n❌ ERROR: Connection failed")
    print(f"   {type(e).__name__}: {e}")
    print("\nTroubleshooting:")
    print("  1. Check API key is valid at https://platform.moonshot.cn/console/api-keys")
    print("  2. Verify base URL (try both .cn and .ai)")
    print(f"  3. Try different model: kimi-k2-0905-preview or kimi-k2-turbo-preview")
    exit(1)
