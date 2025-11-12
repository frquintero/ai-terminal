"""
Intention Cache - Query-to-tool mapping via SQLite FTS5

Wraps Memory API's intention_cache table to provide:
- Semantic search via FTS5 BM25 scoring
- Confidence-based cache hit detection
- Tool/args retrieval for CACHED route
"""

from typing import Dict, List, Optional, Tuple, Any

from router.rules import Route


class CacheHit:
    """Represents a cache lookup result"""
    
    def __init__(
        self,
        cache_id: int,
        tool_name: str,
        tool_args: Dict[str, Any],
        user_query: str,
        score: float,
        usage_count: int
    ):
        self.cache_id = cache_id
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.user_query = user_query
        self.score = score
        self.usage_count = usage_count
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for logging"""
        return {
            "cache_id": self.cache_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "user_query": self.user_query,
            "score": self.score,
            "usage_count": self.usage_count
        }


class IntentionCache:
    """
    Intention cache lookup using Memory API's FTS5 search.
    
    Provides threshold-based cache hit detection for CACHED route.
    """
    
    # Conservative thresholds for MVP
    # (will tune based on real-world usage metrics)
    DEFAULT_MIN_SCORE = 0.0         # FTS5 BM25 score threshold (accept any negative rank for MVP)
    DEFAULT_MIN_USAGE = 1           # Minimum successful executions
    DEFAULT_SEARCH_LIMIT = 5        # Max cache entries to search
    
    def __init__(self, memory):
        """
        Initialize intention cache.
        
        Args:
            memory: Memory instance for FTS5 queries
        """
        self.memory = memory
        self.min_score = self.DEFAULT_MIN_SCORE
        self.min_usage = self.DEFAULT_MIN_USAGE
        self.search_limit = self.DEFAULT_SEARCH_LIMIT
    
    def lookup(self, query: str) -> Optional[CacheHit]:
        """
        Search intention cache for matching execution.
        
        Args:
            query: User query text
        
        Returns:
            CacheHit if confident match found, None otherwise
        
        Algorithm:
        1. FTS5 BM25 search (Memory.search_intention_cache)
        2. Filter by thresholds (score, usage_count)
        3. Return top result if confident, else None
        """
        # Search cache via Memory API
        # Note: search_intention_cache returns results with min_success=True by default
        hits = self.memory.search_intention_cache(
            query=query,
            limit=self.search_limit,
            min_success=True
        )
        
        if not hits:
            return None
        
        # Check top result against thresholds
        top_hit = hits[0]
        
        # FTS5 BM25 rank is negative (more negative = better match)
        # Threshold is also negative, so rank must be <= threshold
        # Example: rank=-0.5, threshold=-1.0 → -0.5 > -1.0 → REJECT (not good enough)
        #          rank=-1.5, threshold=-1.0 → -1.5 <= -1.0 → ACCEPT (good match)
        # For MVP, accept all matches (threshold -1.0, any negative rank passes)
        rank = top_hit.get("rank", 0)
        if rank > self.min_score:
            return None
        
        # Check usage count
        if top_hit.get("usage_count", 0) < self.min_usage:
            return None
        
        # Confident match - return CacheHit
        return CacheHit(
            cache_id=top_hit["id"],
            tool_name=top_hit["tool_name"],
            tool_args=top_hit["tool_args"],
            user_query=top_hit["user_query_text"],
            score=top_hit["rank"],
            usage_count=top_hit["usage_count"]
        )
    
    def update_usage(self, cache_id: int):
        """
        Increment usage counter for cache hit.
        
        Called after successful CACHED route execution.
        """
        self.memory.update_cache_usage(cache_id)
    
    def add_execution(
        self,
        user_query: str,
        normalized_intent: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        success: bool
    ):
        """
        Record successful execution to cache.
        
        Args:
            user_query: Original user query
            normalized_intent: Normalized intent (for FTS matching)
            tool_name: Tool that was executed
            tool_args: Tool arguments
            success: Whether execution succeeded
        """
        self.memory.add_to_intention_cache(
            user_query=user_query,
            normalized_intent=normalized_intent,
            tool_name=tool_name,
            tool_args=tool_args,
            success=success
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics for debugging"""
        return {
            "min_score_threshold": self.min_score,
            "min_usage_threshold": self.min_usage,
            "search_limit": self.search_limit,
        }
