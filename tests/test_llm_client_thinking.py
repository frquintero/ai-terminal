import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from llm_client import LLMClient
from config import Config

class TestLLMClientThinking(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock(spec=Config)
        self.config.base_url = "http://test"
        self.config.api_key = "test"
        self.config.model = "test-model"
        self.config.max_tokens = 100
        self.config.temperature = 0.5
        # Default to hiding thinking
        self.config.hide_thinking = True

    @patch("openai.OpenAI")
    def test_strips_thinking_tags_when_enabled(self, mock_openai):
        # Setup
        client = LLMClient(self.config)
        mock_completion = MagicMock()
        mock_completion.choices = [
            SimpleNamespace(message=SimpleNamespace(content="<think>I am thinking...</think>{\"response\": \"Hello\"}"))
        ]
        mock_openai.return_value.chat.completions.create.return_value = mock_completion

        # Execute
        result = client.call(messages=[{"role": "user", "content": "hi"}])

        # Verify
        self.assertEqual(result["message"].content, "{\"response\": \"Hello\"}")

    @patch("openai.OpenAI")
    def test_keeps_thinking_tags_when_disabled(self, mock_openai):
        # Setup
        self.config.hide_thinking = False
        client = LLMClient(self.config)
        mock_completion = MagicMock()
        content = "<think>I am thinking...</think>{\"response\": \"Hello\"}"
        mock_completion.choices = [
            SimpleNamespace(message=SimpleNamespace(content=content))
        ]
        mock_openai.return_value.chat.completions.create.return_value = mock_completion

        # Execute
        result = client.call(messages=[{"role": "user", "content": "hi"}])

        # Verify
        self.assertEqual(result["message"].content, content)

if __name__ == "__main__":
    unittest.main()
