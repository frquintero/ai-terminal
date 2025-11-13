"""
Rule-based query classification for Router

Fast regex patterns to detect:
- SHELL: Direct shell commands (ls, git, docker, etc.)
- CHAT: Simple informational queries (what is, explain, define)
- Conservative fallback to PLANNER for ambiguous cases
"""

from enum import Enum
from typing import Dict, Optional, Tuple

from orchestrator.command_patterns import (
    CHAT_PATTERNS_COMPILED,
    INTERACTIVE_PATTERNS_COMPILED,
    SHELL_PATTERNS_COMPILED,
)


class Route(str, Enum):
    """Query routing destinations"""
    CHAT = "CHAT"       # Simple Q&A → Agent C
    CACHED = "CACHED"   # Previously executed → Tool + Agent C narrator
    SHELL = "SHELL"     # Shell command → Direct execution + Agent C narrator  
    PLANNER = "PLANNER" # Complex task → Agent A/B loop + Agent C summarizer


class RuleEngine:
    """
    Fast regex-based query classifier.
    
    Classification order (highest to lowest precedence):
    1. SHELL - Direct shell commands
    2. CHAT - Simple informational queries
    3. PLANNER - Fallback for everything else (conservative)
    
    Note: CACHED route handled separately by IntentionCache lookup
    """
    
    def __init__(self):
        """Initialize rule engine with compiled patterns"""
        self.shell_patterns = SHELL_PATTERNS_COMPILED
        self.chat_patterns = CHAT_PATTERNS_COMPILED
        self.interactive_patterns = INTERACTIVE_PATTERNS_COMPILED
    
    def classify(self, query: str) -> Tuple[Optional[Route], Optional[str]]:
        """
        Classify query using regex rules.
        
        Args:
            query: User query text
        
        Returns:
            (route, matched_rule) tuple
            - route: Route enum if matched, None if no match
            - matched_rule: Pattern that matched (for logging/debugging)
        
        Classification logic:
        - Check SHELL patterns first (highest priority)
        - Then CHAT patterns
        - Return None if no match (caller should fallback to PLANNER)
        """
        query_stripped = query.strip()
        
        # Priority 1: Shell commands
        for pattern in self.shell_patterns:
            if pattern.match(query_stripped):
                return Route.SHELL, pattern.pattern
        
        # Priority 2: Chat queries
        for pattern in self.chat_patterns:
            if pattern.search(query_stripped):
                return Route.CHAT, pattern.pattern
        
        # No match - return None (caller falls back to PLANNER)
        return None, None
    
    def is_interactive_command(self, query: str) -> bool:
        """
        Detect if query is an interactive command that requires TTY.
        
        Args:
            query: User query text
        
        Returns:
            True if matches interactive command pattern
        """
        query_stripped = query.strip()
        for pattern in self.interactive_patterns:
            if pattern.match(query_stripped):
                return True
        return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get rule statistics for debugging"""
        return {
            "shell_patterns": len(self.shell_patterns),
            "chat_patterns": len(self.chat_patterns),
            "interactive_patterns": len(self.interactive_patterns),
        }
