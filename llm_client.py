"""
LLMClient - Reusable LLM interaction wrapper for v2.0 Orchestrator

Extracted from agent.py for use across Agent A, B, and C roles.
Handles OpenAI API calls with logging, error handling, and tracing.
"""

import hashlib
import json
import time
import uuid
import re
from typing import Any, Dict, List, Optional

import openai

from config import Config


class LLMClient:
    """
    Reusable LLM client for calling OpenAI-compatible APIs.
    
    Features:
    - Role-specific system prompts
    - Token usage tracking
    - Latency measurement
    - Error handling with trace IDs
    - Optional logging to Memory
    
    Usage:
        client = LLMClient(config, role="A")
        response = client.call(messages, tools=None)
    """
    
    def __init__(
        self,
        config: Config,
        role: str = None,
        memory=None
    ):
        """
        Initialize LLM client.
        
        Args:
            config: Configuration object with API settings
            role: Agent role (A, B, C) for logging
            memory: Optional Memory instance for logging interactions
        """
        self.config = config
        self.role = role
        self.memory = memory
        
        self.client = openai.OpenAI(
            base_url=getattr(config, "base_url", None),
            api_key=getattr(config, "api_key", None)
        )
    
    def call(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        cycle_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Call LLM with messages and optional tools, with exponential backoff retry.
        
        Args:
            messages: List of messages (system, user, assistant, tool)
            tools: Optional tool schemas
            tool_choice: Optional tool choice (auto, none, or specific tool)
            cycle_id: Cycle ID for logging
            max_tokens: Override default max_tokens
            temperature: Override default temperature
            max_retries: Number of retries for transient errors (default: 3)
        
        Returns:
            Dict with:
                - message: Assistant message object
                - usage: Token usage dict
                - latency_ms: Call latency
                - trace_id: Trace ID for debugging
                - error: Error message (if failed)
        """
        trace_id = uuid.uuid4().hex[:8]
        start_time = time.time()
        
        # Use config defaults if not overridden
        if max_tokens is None:
            max_tokens = self.config.max_tokens
        if temperature is None:
            temperature = self.config.temperature
        
        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(max_retries):
            try:
                # Build API request
                api_kwargs = {
                    "model": self.config.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                
                if tools:
                    api_kwargs["tools"] = tools
                    if tool_choice:
                        api_kwargs["tool_choice"] = tool_choice
                else:
                    # Only force JSON object format if NOT using tools
                    # This avoids conflicts with tool calling models
                    if self.role in ("A", "B"):
                        api_kwargs["response_format"] = {"type": "json_object"}
                
                # Call OpenAI API
                response = self.client.chat.completions.create(**api_kwargs)
                
                # Calculate latency
                latency_ms = int((time.time() - start_time) * 1000)
                
                # Extract usage and message
                if not response.choices:
                    raise ValueError("No choices returned from API")
                
                assistant_message = response.choices[0].message

                # Optionally strip <think> blocks from content for cleaner logs
                raw_content = assistant_message.content or ""
                if getattr(self.config, "hide_thinking", False) and raw_content:
                    raw_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
                    try:
                        assistant_message.content = raw_content  # keep downstream behavior consistent
                    except Exception:
                        pass
                
                # Derive trace text for logging: use message content if present,
                # otherwise summarize tool calls so telemetry isn't blank.
                response_text = assistant_message.content or ""
                if not response_text:
                    tool_calls = getattr(assistant_message, "tool_calls", None) or []
                    summaries = []
                    for tc in tool_calls:
                        func = getattr(tc, "function", None)
                        name = getattr(func, "name", None) or getattr(tc, "name", "")
                        raw_args = getattr(func, "arguments", None) or getattr(tc, "arguments", "")
                        arg_excerpt = raw_args or ""
                        if len(arg_excerpt) > 200:
                            arg_excerpt = arg_excerpt[:200] + "..."
                        if name and arg_excerpt:
                            summaries.append(f"{name}: {arg_excerpt}")
                        elif name:
                            summaries.append(name)
                        elif arg_excerpt:
                            summaries.append(arg_excerpt)
                        else:
                            summaries.append("tool_call")
                    if summaries:
                        response_text = "; ".join(summaries)
                
                usage_dict = None
                if hasattr(response, 'usage') and response.usage:
                    usage_dict = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                
                # Log to memory if available
                if self.memory and cycle_id and self.role:
                    self._log_to_memory(
                        cycle_id=cycle_id,
                        messages=messages,
                        response_text=response_text,
                        usage=usage_dict,
                        latency_ms=latency_ms,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                
                # Record LLM metrics
                if self.role and usage_dict:
                    if self.memory and hasattr(self.memory, "record_llm_metric"):
                        self.memory.record_llm_metric(
                            role=self.role,
                            model=self.config.model,
                            prompt_tokens=usage_dict["prompt_tokens"],
                            completion_tokens=usage_dict["completion_tokens"],
                            latency_ms=latency_ms
                        )
                    else:
                        from orchestrator.metrics import get_metrics, LLMMetrics
                        metrics = get_metrics()
                        metrics.record_llm_metric(LLMMetrics(
                            role=self.role,
                            model=self.config.model,
                            prompt_tokens=usage_dict["prompt_tokens"],
                            completion_tokens=usage_dict["completion_tokens"],
                            latency_ms=latency_ms
                        ))
                
                return {
                    "message": assistant_message,
                    "usage": usage_dict,
                    "latency_ms": latency_ms,
                    "trace_id": trace_id,
                    "error": None
                }
            
            except Exception as e:
                last_error = e
                
                # Check if error is retryable
                is_retryable = self._is_retryable_error(e)
                is_last_attempt = (attempt == max_retries - 1)
                
                if is_retryable and not is_last_attempt:
                    # Exponential backoff: 1s, 2s, 4s
                    delay = 2 ** attempt
                    # Silently retry (no logging to not spam logs)
                    time.sleep(delay)
                    continue
                else:
                    # Non-retryable or last attempt, return error
                    break
        
        # All retries exhausted or non-retryable error
        latency_ms = int((time.time() - start_time) * 1000)
        error_text = str(last_error) if last_error else "Unknown error"
        failed_generation = self._extract_failed_generation(last_error)
        if failed_generation:
            error_text = f"{error_text} | failed_generation: {failed_generation}"

        # Log failed attempt so we retain traces for debugging
        if self.memory and cycle_id and self.role:
            self._log_to_memory(
                cycle_id=cycle_id,
                messages=messages,
                response_text=error_text,
                usage=None,
                latency_ms=latency_ms,
                temperature=temperature,
                max_tokens=max_tokens
            )

            if self.config.save_llm_traces:
                full_prompt = json.dumps(messages, indent=2)
                full_response = json.dumps(
                    {
                        "error": str(last_error) if last_error else "Unknown error",
                        "failed_generation": failed_generation
                    },
                    indent=2
                )
                self.memory.save_llm_trace(
                    cycle_id=cycle_id,
                    role=self.role,
                    full_prompt=full_prompt,
                    full_response=full_response,
                    model=self.config.model,
                    temperature=temperature,
                    max_tokens=max_tokens
                )

        return {
            "message": None,
            "usage": None,
            "latency_ms": latency_ms,
            "trace_id": trace_id,
            "error": error_text
        }

    def _extract_failed_generation(self, error: Exception) -> Optional[str]:
        """
        Best-effort extraction of the failed_generation payload from an LLM error.
        """
        if not error:
            return None

        # OpenAI client errors often carry a response with a body
        response = getattr(error, "response", None)
        if response:
            body = getattr(response, "body", None) or getattr(response, "data", None) or getattr(response, "text", None)
            if body:
                try:
                    body_text = body.decode() if hasattr(body, "decode") else str(body)
                    parsed = json.loads(body_text)
                    failed_gen = parsed.get("error", {}).get("failed_generation")
                    if failed_gen:
                        return failed_gen
                except Exception:
                    pass

        # Fallback: regex against the stringified exception
        error_str = str(error)
        if "failed_generation" in error_str:
            import re
            match = re.search(r"failed_generation[^\\w]*['\"]([^'\"]+)['\"]", error_str)
            if match:
                return match.group(1)
        return None
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an error should trigger a retry.
        
        Retryable: timeout, rate limit, connection errors
        Non-retryable: auth errors, malformed requests
        """
        error_str = str(error).lower()
        
        # Retryable patterns
        retryable_patterns = [
            'timeout',
            'rate_limit',
            '429',
            'connection',
            'temporarily unavailable',
            '503',
            'service unavailable',
            'deadline exceeded'
        ]
        
        # Non-retryable patterns
        non_retryable_patterns = [
            'invalid api key',
            '401',
            '403',
            'authentication',
            'unauthorized',
            'forbidden',
            'malformed',
            'invalid request',
            '400',
            'bad request'
        ]
        
        # Check retryable first
        for pattern in retryable_patterns:
            if pattern in error_str:
                return True
        
        # Check non-retryable
        for pattern in non_retryable_patterns:
            if pattern in error_str:
                return False
        
        # Unknown error: don't retry to avoid infinite loops
        return False
    
    def _log_to_memory(
        self,
        cycle_id: str,
        messages: List[Dict[str, Any]],
        response_text: str,
        usage: Optional[Dict[str, int]],
        latency_ms: int,
        temperature: float,
        max_tokens: int
    ):
        """
        Log interaction to Memory.
        
        Args:
            cycle_id: Cycle ID
            messages: Full message history sent to API
            response_text: Assistant response text
            usage: Token usage dict
            latency_ms: Call latency
            temperature: Temperature used for this call
            max_tokens: Max tokens used for this call
        """
        # Extract system prompt for checksum
        system_prompt = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
                break
        
        # Compute system prompt checksum
        checksum = hashlib.sha256(system_prompt.encode()).hexdigest()[:16]
        
        # Generate previews (first 500 chars)
        prompt_preview = self._generate_prompt_preview(messages)
        response_preview = response_text[:500] if response_text else ""
        
        # Log interaction
        self.memory.log_interaction(
            cycle_id=cycle_id,
            role=self.role,
            system_prompt_checksum=checksum,
            prompt_preview=prompt_preview,
            response_preview=response_preview,
            token_usage=usage,
            latency_ms=latency_ms
        )
        
        # Optional: Save full trace for debugging
        if self.config.save_llm_traces:
            full_prompt = json.dumps(messages, indent=2)
            self.memory.save_llm_trace(
                cycle_id=cycle_id,
                role=self.role,
                full_prompt=full_prompt,
                full_response=response_text,
                model=self.config.model,
                temperature=temperature,
                max_tokens=max_tokens
            )
    
    def _generate_prompt_preview(self, messages: List[Dict[str, Any]]) -> str:
        """
        Generate a preview of the prompt (first 500 chars of user messages).
        
        Args:
            messages: Message list
        
        Returns:
            Preview string
        """
        user_messages = [
            msg.get("content", "")
            for msg in messages
            if msg.get("role") == "user"
        ]
        
        combined = "\n".join(user_messages)
        return combined[:500]
    
    def call_streaming(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        cycle_id: Optional[str] = None
    ):
        """
        Call LLM with streaming response (future enhancement).
        
        Not implemented in MVP - placeholder for Phase 5 polish.
        """
        raise NotImplementedError("Streaming not yet supported in v2.0 MVP")
