"""
Router Module - Intelligent query classification for v2.0 Orchestrator

Routes queries to appropriate execution path:
- CHAT: Simple informational queries → Agent C
- CACHED: Previously executed queries → Direct tool execution + Agent C narrator
- SHELL: Shell commands → Direct shell execution + Agent C narrator
- PLANNER: Complex multi-step tasks → Agent A/B loop + Agent C summarizer

Target metrics:
- 90%+ shell commands hit SHELL fast-path
- <100ms router latency
- Conservative fallback to PLANNER when ambiguous
"""

from router.router import Router, Route, RouterResult

__all__ = ["Router", "Route", "RouterResult"]
