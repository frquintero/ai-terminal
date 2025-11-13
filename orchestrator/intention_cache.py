"""
Intention Cache utilities for routerless orchestration.

Provides CacheHit data holder and IntentionCache wrapper around Memory's
intention_cache FTS5 table.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class CacheHit:
    """Represents a cache lookup result."""

    def __init__(
        self,
        cache_id: int,
        tool_name: str,
        tool_args: Dict[str, Any],
        user_query: str,
        score: float,
        usage_count: int,
    ):
        self.cache_id = cache_id
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.user_query = user_query
        self.score = score
        self.usage_count = usage_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cache_id": self.cache_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "user_query": self.user_query,
            "score": self.score,
            "usage_count": self.usage_count,
        }


class IntentionCache:
    """FTS5-backed cache lookup via Memory API."""

    DEFAULT_MIN_SCORE = 0.0
    DEFAULT_MIN_USAGE = 1
    DEFAULT_SEARCH_LIMIT = 5

    def __init__(self, memory):
        self.memory = memory
        self.min_score = self.DEFAULT_MIN_SCORE
        self.min_usage = self.DEFAULT_MIN_USAGE
        self.search_limit = self.DEFAULT_SEARCH_LIMIT

    def lookup(self, query: str) -> Optional[CacheHit]:
        hits = self.memory.search_intention_cache(
            query=query,
            limit=self.search_limit,
            min_success=True,
        )
        if not hits:
            return None

        top_hit = hits[0]
        rank = top_hit.get("rank", 0)
        if rank > self.min_score:
            return None
        if top_hit.get("usage_count", 0) < self.min_usage:
            return None

        return CacheHit(
            cache_id=top_hit["id"],
            tool_name=top_hit["tool_name"],
            tool_args=top_hit["tool_args"],
            user_query=top_hit["user_query_text"],
            score=top_hit["rank"],
            usage_count=top_hit["usage_count"],
        )

    def update_usage(self, cache_id: int):
        self.memory.update_cache_usage(cache_id)

    def add_execution(
        self,
        user_query: str,
        normalized_intent: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        success: bool,
    ):
        self.memory.add_to_intention_cache(
            user_query=user_query,
            normalized_intent=normalized_intent,
            tool_name=tool_name,
            tool_args=tool_args,
            success=success,
        )

    def get_stats(self) -> Dict[str, Any]:
        return {
            "min_score_threshold": self.min_score,
            "min_usage_threshold": self.min_usage,
            "search_limit": self.search_limit,
        }
