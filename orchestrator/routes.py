"""
Route definitions and decision dataclass for the routerless orchestrator.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from router.cache import CacheHit


class Route(str, Enum):
    """Query routing destinations."""

    CHAT = "CHAT"
    SHELL = "SHELL"
    CACHED = "CACHED"
    PLANNER = "PLANNER"


@dataclass
class RouterResult:
    """Route classification result compatible with the legacy structure."""

    route: Route
    confidence: float
    latency_ms: int
    matched_rule: Optional[str] = None
    cache_hit: Optional[CacheHit] = None

    def to_dict(self):
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
