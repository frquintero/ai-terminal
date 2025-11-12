"""
Unified Memory System for v2.0 Orchestrator

This module provides THE SINGLE SOURCE OF TRUTH for all system state:
- ONE SQLite database (logs/orchestrator.db)
- ONE Memory class that manages all persistence
- NO fragmentation (replaces v1.3 db_logger, filesystem_context, history_store, event_memory)

Usage:
    from memory import Memory
    
    mem = Memory()
    cycle_id = mem.create_cycle(session_id, query="user query")
    mem.save_router_decision(cycle_id, route="CHAT", confidence=0.95)
"""

from memory.schema import init_db
from memory.api import Memory

__all__ = ["Memory", "init_db"]
