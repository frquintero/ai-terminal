"""
Router - Intelligent query classifier for v2.0 Orchestrator

Routes queries using precedence hierarchy:
1. SHELL - Regex match for shell commands (highest priority)
2. CACHED - FTS5 lookup for previously executed queries
3. CHAT - Regex match for simple questions
4. PLANNER - Conservative fallback for everything else

Target: <100ms latency, 90%+ shell fast-path hit rate
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from router.rules import Route, RuleEngine
from router.cache import IntentionCache, CacheHit


@dataclass
class RouterResult:
    """
    Router classification result.
    
    Contains route decision + metadata for logging/debugging.
    """
    route: Route
    confidence: float           # 0.0-1.0 confidence score
    latency_ms: int            # Classification latency
    matched_rule: Optional[str] = None       # Regex pattern that matched (for SHELL/CHAT)
    cache_hit: Optional[CacheHit] = None     # Cache result (for CACHED)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for Memory logging"""
        result = {
            "route": self.route.value,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
        }
        
        if self.matched_rule:
            result["matched_rule"] = self.matched_rule
        
        if self.cache_hit:
            result["cache_hit"] = self.cache_hit.to_dict()
        
        return result


class Router:
    """
    Query router with rule-based + FTS5 cache classification.
    
    Stateless design - all state in Memory, no instance variables except config.
    """
    
    # Confidence scores for different route types
    SHELL_CONFIDENCE = 0.95    # High confidence for regex-matched shell commands
    CACHED_CONFIDENCE = 0.90   # High confidence for FTS5 cache hits
    CHAT_CONFIDENCE = 0.85     # Medium-high confidence for chat patterns
    PLANNER_CONFIDENCE = 0.50  # Low confidence for fallback
    
    def __init__(self, memory):
        """
        Initialize router.
        
        Args:
            memory: Memory instance for cache lookups and logging
        """
        self.memory = memory
        self.rule_engine = RuleEngine()
        self.intention_cache = IntentionCache(memory)
    
    def classify(self, query: str) -> RouterResult:
        """
        Classify query and return route decision.
        
        Args:
            query: User query text
        
        Returns:
            RouterResult with route, confidence, and metadata
        
        Classification precedence:
        1. SHELL - Regex match (ls, git, docker, etc.) → HIGHEST PRIORITY
        2. CACHED - FTS5 cache hit (previous successful execution)
        3. CHAT - Regex match (what is, explain, etc.)
        4. PLANNER - Conservative fallback (everything else)
        
        Design notes:
        - SHELL has highest priority to hit fast-path for 50%+ of queries
        - CACHED checked second to leverage execution history
        - CHAT checked third for simple questions
        - PLANNER is safe fallback when uncertain
        """
        start_time = time.time()
        
        # Priority 1: Shell command detection (fast regex)
        route, matched_rule = self.rule_engine.classify(query)
        if route == Route.SHELL:
            latency_ms = int((time.time() - start_time) * 1000)
            return RouterResult(
                route=Route.SHELL,
                confidence=self.SHELL_CONFIDENCE,
                latency_ms=latency_ms,
                matched_rule=matched_rule
            )
        
        # Priority 2: Intention cache lookup (FTS5 search)
        cache_hit = self.intention_cache.lookup(query)
        if cache_hit:
            latency_ms = int((time.time() - start_time) * 1000)
            return RouterResult(
                route=Route.CACHED,
                confidence=self.CACHED_CONFIDENCE,
                latency_ms=latency_ms,
                cache_hit=cache_hit
            )
        
        # Priority 3: Chat query detection (fast regex)
        if route == Route.CHAT:
            latency_ms = int((time.time() - start_time) * 1000)
            return RouterResult(
                route=Route.CHAT,
                confidence=self.CHAT_CONFIDENCE,
                latency_ms=latency_ms,
                matched_rule=matched_rule
            )
        
        # Priority 4: Conservative fallback to PLANNER
        latency_ms = int((time.time() - start_time) * 1000)
        return RouterResult(
            route=Route.PLANNER,
            confidence=self.PLANNER_CONFIDENCE,
            latency_ms=latency_ms
        )
    
    def log_decision(self, cycle_id: str, query: str, result: RouterResult):
        """
        Log routing decision to Memory.
        
        Args:
            cycle_id: Orchestration cycle ID
            query: User query
            result: RouterResult from classify()
        
        Logs to router_decisions table via Memory API.
        """
        # Extract cache hit metadata if present
        cache_hit_tool = None
        cache_hit_args = None
        
        if result.cache_hit:
            cache_hit_tool = result.cache_hit.tool_name
            cache_hit_args = result.cache_hit.tool_args
        
        # Build rules dict for logging
        rules = {}
        if result.matched_rule:
            rules["pattern"] = result.matched_rule
        if result.cache_hit:
            rules["cache_id"] = result.cache_hit.cache_id
            rules["cache_score"] = result.cache_hit.score
        
        # Log via Memory API
        # Note: cycle already created by orchestrator, we just update the decision
        self.memory.save_router_decision(
            cycle_id=cycle_id,
            route=result.route.value,
            confidence=result.confidence,
            rules=rules if rules else None,
            cache_hit_tool=cache_hit_tool,
            cache_hit_args=cache_hit_args
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics for debugging"""
        return {
            "rule_engine": self.rule_engine.get_stats(),
            "intention_cache": self.intention_cache.get_stats(),
            "confidence_thresholds": {
                "shell": self.SHELL_CONFIDENCE,
                "cached": self.CACHED_CONFIDENCE,
                "chat": self.CHAT_CONFIDENCE,
                "planner": self.PLANNER_CONFIDENCE,
            }
        }
