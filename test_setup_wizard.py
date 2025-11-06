#!/usr/bin/env python3
"""
Test setup.py wizard functions without interactive prompts.
"""

import os
import tempfile
from pathlib import Path
from setup import write_env_file, test_connection


def test_write_env_minimax():
    """Test writing MiniMax configuration"""
    config = {
        'AGENT_TYPE': 'minimax',
        'MINIMAX_M2_API_KEY': 'test_key_12345',
        'MINIMAX_MODEL': 'MiniMax-M2',
        'MAX_TOKENS': '1024',
        'TEMPERATURE': '0.7',
        'MAX_STEPS': '15',
        'HIDE_THINKING': 'true',
        'SHOW_RAW_OUTPUT': 'false'
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env.test"
        write_env_file(config, str(env_path))
        
        assert env_path.exists(), "Config file not created"
        content = env_path.read_text()
        
        assert 'AGENT_TYPE=minimax' in content
        assert 'MINIMAX_M2_API_KEY=test_key_12345' in content
        assert 'MINIMAX_MODEL=MiniMax-M2' in content
        assert 'MAX_TOKENS=1024' in content
        
        print("✓ MiniMax config write test passed")


def test_write_env_kimi2():
    """Test writing Kimi K2 configuration"""
    config = {
        'AGENT_TYPE': 'kimi2',
        'KIMI_2_API_KEY': 'sk-test_kimi_key',
        'KIMI_2_MODEL': 'kimi-k2-turbo-preview',
        'KIMI_2_BASE_URL': 'https://api.moonshot.ai/v1',
        'MAX_TOKENS': '2048',
        'TEMPERATURE': '0.6',
        'MAX_STEPS': '20',
        'HIDE_THINKING': 'true',
        'SHOW_RAW_OUTPUT': 'false'
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env.kimi"
        write_env_file(config, str(env_path))
        
        assert env_path.exists(), "Config file not created"
        content = env_path.read_text()
        
        assert 'AGENT_TYPE=kimi2' in content
        assert 'KIMI_2_API_KEY=sk-test_kimi_key' in content
        assert 'KIMI_2_MODEL=kimi-k2-turbo-preview' in content
        assert 'KIMI_2_BASE_URL=https://api.moonshot.ai/v1' in content
        assert 'MAX_TOKENS=2048' in content
        
        print("✓ Kimi K2 config write test passed")


def test_write_env_custom():
    """Test writing custom backend configuration"""
    config = {
        'AGENT_TYPE': 'custom',
        'CUSTOM_API_KEY': 'custom_key_abc',
        'CUSTOM_MODEL': 'my-custom-model',
        'CUSTOM_BASE_URL': 'https://api.example.com/v1',
        'MAX_TOKENS': '4096',
        'TEMPERATURE': '0.8',
        'MAX_STEPS': '25',
        'HIDE_THINKING': 'false',
        'SHOW_RAW_OUTPUT': 'true'
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env.custom"
        write_env_file(config, str(env_path))
        
        assert env_path.exists(), "Config file not created"
        content = env_path.read_text()
        
        assert 'AGENT_TYPE=custom' in content
        assert 'CUSTOM_API_KEY=custom_key_abc' in content
        assert 'CUSTOM_MODEL=my-custom-model' in content
        assert 'CUSTOM_BASE_URL=https://api.example.com/v1' in content
        
        print("✓ Custom backend config write test passed")


def test_connection_test():
    """Test connection testing function (should fail with fake key)"""
    # This should fail gracefully
    result = test_connection(
        agent_type='kimi2',
        api_key='fake_key',
        model='kimi-k2-turbo-preview',
        base_url='https://api.moonshot.ai/v1'
    )
    
    assert result == False, "Connection test should fail with invalid key"
    print("✓ Connection test (expected failure) passed")


def test_discover_backends():
    """Test backend discovery from config.py"""
    from setup import discover_agent_backends
    
    backends = discover_agent_backends()
    
    assert len(backends) >= 2, "Should discover at least 2 backends"
    
    backend_types = [agent_type for agent_type, _, _ in backends]
    assert 'minimax' in backend_types, "Should discover minimax backend"
    assert 'kimi2' in backend_types, "Should discover kimi2 backend"
    
    print("✓ Backend discovery test passed")


def test_load_existing_env():
    """Test loading existing .env file"""
    import tempfile
    from setup import load_existing_env
    
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env"
        env_path.write_text("""
# Test config
AGENT_TYPE=kimi2
KIMI_2_API_KEY=sk-test123
KIMI_2_MODEL=kimi-k2-turbo-preview
MAX_TOKENS=2048
""")
        
        config = load_existing_env(str(env_path))
        
        assert config['AGENT_TYPE'] == 'kimi2'
        assert config['KIMI_2_API_KEY'] == 'sk-test123'
        assert config['MAX_TOKENS'] == '2048'
        
        print("✓ Load existing .env test passed")


if __name__ == "__main__":
    print("Testing setup.py wizard functions...\n")
    
    test_write_env_minimax()
    test_write_env_kimi2()
    test_write_env_custom()
    test_connection_test()
    test_discover_backends()
    test_load_existing_env()
    
    print("\n✅ All setup.py tests passed!")
