"""Compatibility shim while IntentionCache migrates under orchestrator."""

from orchestrator.intention_cache import CacheHit, IntentionCache

__all__ = ["CacheHit", "IntentionCache"]
