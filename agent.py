from config import Config, load_config
from tools import get_tool_schemas, TOOLS
import openai
import json
import re

class MiniAgent:
    def __init__(self):
        self.config = load_config()
        self.client = openai.OpenAI(
            base_url="https://api.minimax.io/v1",
            api_key=self.config.api_key
        )
        self.message_history = [
            {
                "role": "system",
                "content": """You are an AI-powered Linux shell terminal assistant. You can execute shell commands, read and write files, process content, and engage in conversation.

Available tools:
- read_file: Read the contents of a file
- write_file: Create or overwrite a file with content
- run_command: Execute a shell command
- chat: Provide a conversational response
- process_content: Analyze and process text content

When users provide input, determine if it requires tool use or just conversation. For commands, use run_command. For file operations, use read_file or write_file. For content analysis, use process_content. For chat, use chat tool or respond directly.

Always prioritize safety and helpfulness."""
            }
        ]

    def process_input(self, user_input: str) -> str:
        self.message_history.append({"role": "user", "content": user_input})
        tools = get_tool_schemas()
        max_steps = 10  # Prevent infinite loops
        step_count = 0
        while step_count < max_steps:
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=self.message_history,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    tools=tools
                )
                if response.choices is None:
                    if hasattr(response, 'base_resp'):
                        base_resp = response.base_resp
                        if isinstance(base_resp, dict) and 'status_msg' in base_resp:
                            return f"API Error: {base_resp['status_msg']}"
                        else:
                            return "API Error: Unknown error occurred."
                    else:
                        return "API Error: No base_resp found."
                assistant_message = response.choices[0].message
            except Exception as e:
                return f"API Error: {str(e)}"
            if assistant_message.tool_calls:
                self.message_history.append(assistant_message)
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    tool = TOOLS[tool_name]
                    args = json.loads(tool_call.function.arguments)
                    result = tool.execute(**args)
                    tool_message = {
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tool_call.id
                    }
                    self.message_history.append(tool_message)
            else:
                self.message_history.append(assistant_message)
                break
            step_count += 1
            if step_count >= max_steps:
                error_message = {
                    "role": "assistant",
                    "content": "Maximum tool calling steps exceeded. Please simplify your request."
                }
                self.message_history.append(error_message)
                return error_message["content"]
        content = assistant_message.content or ""
        if self.config.hide_thinking:
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        return content
