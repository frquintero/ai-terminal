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
        self.config.save_llm_traces = False
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

    @patch("openai.OpenAI")
    def test_logs_tool_call_summary_when_content_empty(self, mock_openai):
        # Setup
        self.config.save_llm_traces = False
        memory = MagicMock()
        memory.log_interaction = MagicMock()
        memory.record_llm_metric = MagicMock()

        client = LLMClient(self.config, role='A', memory=memory)
        tool_call = SimpleNamespace(
            function=SimpleNamespace(
                name="delegate_to_agent_b",
                arguments='{"intent":"Do a thing","success_criteria":["ok"]}'
            )
        )
        mock_completion = MagicMock()
        mock_completion.choices = [
            SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tool_call]))
        ]
        mock_openai.return_value.chat.completions.create.return_value = mock_completion

        # Execute
        client.call(messages=[{"role": "user", "content": "hi"}], cycle_id="cycle-1")

        # Verify the synthesized response text was logged
        logged_kwargs = memory.log_interaction.call_args.kwargs
        self.assertIn("delegate_to_agent_b", logged_kwargs["response_preview"])
        self.assertIn("intent", logged_kwargs["response_preview"])

if __name__ == "__main__":
    unittest.main()
