"""
LLMClient - Reusable LLM interaction wrapper for v2.0 Orchestrator

Extracted from agent.py for use across Agent A, B, and C roles.
Handles OpenAI API calls with logging, error handling, and tracing.
"""

import hashlib
import json
import time
import uuid
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
            base_url=config.base_url,
            api_key=config.api_key
        )
    
    def call(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        cycle_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Call LLM with messages and optional tools.
        
        Args:
            messages: List of messages (system, user, assistant, tool)
            tools: Optional tool schemas
            cycle_id: Cycle ID for logging
            max_tokens: Override default max_tokens
            temperature: Override default temperature
        
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
            
            # Call OpenAI API
            response = self.client.chat.completions.create(**api_kwargs)
            
            # Calculate latency
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Extract usage and message
            if not response.choices:
                raise ValueError("No choices returned from API")
            
            assistant_message = response.choices[0].message
            
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
                    response_text=assistant_message.content or "",
                    usage=usage_dict,
                    latency_ms=latency_ms
                )
            
            return {
                "message": assistant_message,
                "usage": usage_dict,
                "latency_ms": latency_ms,
                "trace_id": trace_id,
                "error": None
            }
        
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            
            return {
                "message": None,
                "usage": None,
                "latency_ms": latency_ms,
                "trace_id": trace_id,
                "error": str(e)
            }
    
    def _log_to_memory(
        self,
        cycle_id: str,
        messages: List[Dict[str, Any]],
        response_text: str,
        usage: Optional[Dict[str, int]],
        latency_ms: int
    ):
        """
        Log interaction to Memory.
        
        Args:
            cycle_id: Cycle ID
            messages: Full message history sent to API
            response_text: Assistant response text
            usage: Token usage dict
            latency_ms: Call latency
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
        if hasattr(self.config, 'save_llm_traces') and self.config.save_llm_traces:
            full_prompt = json.dumps(messages, indent=2)
            self.memory.save_llm_trace(
                cycle_id=cycle_id,
                role=self.role,
                full_prompt=full_prompt,
                full_response=response_text,
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
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
