"""
Lightweight command/query classification helpers.

These helpers replace the legacy Router fast-path logic so the orchestrator can
decide how to handle a query without instantiating router.Router.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from orchestrator.command_patterns import (
    CHAT_PATTERNS_COMPILED,
    INTERACTIVE_PATTERNS_COMPILED,
    SHELL_PATTERNS_COMPILED,
)


class QueryRoute(str, Enum):
    """Route destinations understood by the orchestrator."""

    SHELL = "SHELL"
    CHAT = "CHAT"
    PLANNER = "PLANNER"


@dataclass(frozen=True)
class ClassificationResult:
    """Structured response for classification decisions."""

    route: QueryRoute
    matched_pattern: Optional[str] = None


def normalize_query(query: str) -> str:
    """Normalize user input for regex matching."""
    return query.strip()


def is_shell_command(query: str) -> bool:
    """Return True if the query matches a known shell command pattern."""
    normalized = normalize_query(query)
    return any(pattern.match(normalized) for pattern in SHELL_PATTERNS_COMPILED)


def is_interactive_command(query: str) -> bool:
    """Return True if the query is an interactive shell command."""
    normalized = normalize_query(query)
    return any(pattern.match(normalized) for pattern in INTERACTIVE_PATTERNS_COMPILED)


def is_simple_chat_query(query: str) -> bool:
    """Return True if the query is a simple informational question."""
    normalized = normalize_query(query)
    return any(pattern.search(normalized) for pattern in CHAT_PATTERNS_COMPILED)


def classify_query(query: str) -> ClassificationResult:
    """
    Classify a query into SHELL/CHAT/PLANNER using regex heuristics.

    This mirrors router.RuleEngine.classify but lives inside the orchestrator
    package so we can drop the Router dependency entirely.
    """
    normalized = normalize_query(query)

    for pattern in SHELL_PATTERNS_COMPILED:
        if pattern.match(normalized):
            return ClassificationResult(QueryRoute.SHELL, pattern.pattern)

    for pattern in CHAT_PATTERNS_COMPILED:
        if pattern.search(normalized):
            return ClassificationResult(QueryRoute.CHAT, pattern.pattern)

    return ClassificationResult(QueryRoute.PLANNER, None)
