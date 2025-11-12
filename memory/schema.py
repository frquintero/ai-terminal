"""
Database Schema for v2.0 Orchestrator Memory System

Based on IMPLEMENTATION_PLAN.md §5.2 and history/SCHEMA_DECISION.md

All tables in ONE database: logs/orchestrator.db
"""

import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path("logs/orchestrator.db")

SCHEMA_VERSION = 1

CREATE_TABLES = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Session tracking (global state)
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model TEXT NOT NULL,
    system_info_json TEXT,
    last_activity_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Router decisions (classification per query)
CREATE TABLE IF NOT EXISTS router_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL UNIQUE,
    query_text TEXT NOT NULL,
    route TEXT NOT NULL CHECK (route IN ('CHAT', 'CACHED', 'PLANNER', 'SHELL')),
    confidence REAL,
    rules_json TEXT,
    cache_hit_tool TEXT,
    cache_hit_args_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- Intention cache (for CACHED route zero-LLM execution)
CREATE TABLE IF NOT EXISTS intention_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_query_text TEXT NOT NULL,
    normalized_intent TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_args_json TEXT NOT NULL,
    success_flag INTEGER NOT NULL DEFAULT 1 CHECK (success_flag IN (0, 1)),
    usage_count INTEGER NOT NULL DEFAULT 1,
    last_used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- FTS5 virtual table for intention cache semantic search
CREATE VIRTUAL TABLE IF NOT EXISTS intention_cache_fts USING fts5(
    user_query_text,
    normalized_intent,
    content=intention_cache,
    content_rowid=id
);

-- FTS triggers to keep virtual table in sync
CREATE TRIGGER IF NOT EXISTS intention_cache_ai AFTER INSERT ON intention_cache BEGIN
    INSERT INTO intention_cache_fts(rowid, user_query_text, normalized_intent)
    VALUES (new.id, new.user_query_text, new.normalized_intent);
END;

CREATE TRIGGER IF NOT EXISTS intention_cache_ad AFTER DELETE ON intention_cache BEGIN
    INSERT INTO intention_cache_fts(intention_cache_fts, rowid, user_query_text, normalized_intent)
    VALUES ('delete', old.id, old.user_query_text, old.normalized_intent);
END;

CREATE TRIGGER IF NOT EXISTS intention_cache_au AFTER UPDATE ON intention_cache BEGIN
    INSERT INTO intention_cache_fts(intention_cache_fts, rowid, user_query_text, normalized_intent)
    VALUES ('delete', old.id, old.user_query_text, old.normalized_intent);
    INSERT INTO intention_cache_fts(rowid, user_query_text, normalized_intent)
    VALUES (new.id, new.user_query_text, new.normalized_intent);
END;

-- Interaction logging (ALL roles: A, B, C)
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('A', 'B', 'C')),
    system_prompt_checksum TEXT NOT NULL,
    prompt_preview TEXT,
    response_preview TEXT,
    token_usage_json TEXT,
    latency_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cycle_id) REFERENCES router_decisions(cycle_id)
);

-- Task state (for PLANNER route - Agent A/B workflows)
CREATE TABLE IF NOT EXISTS task_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL UNIQUE,
    plan_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'done', 'error')),
    current_step_id INTEGER,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cycle_id) REFERENCES router_decisions(cycle_id)
);

-- Step outputs (for PLANNER route - Agent B execution results)
CREATE TABLE IF NOT EXISTS step_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL,
    step_id INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    tool_args_json TEXT NOT NULL,
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    exit_code INTEGER,
    output_preview TEXT,
    artifact_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cycle_id) REFERENCES router_decisions(cycle_id)
);

-- Chat history (for CHAT route - conversational context)
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    user_query TEXT NOT NULL,
    agent_response TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (cycle_id) REFERENCES router_decisions(cycle_id)
);

-- LLM traces (detailed prompt/response logging for debugging)
CREATE TABLE IF NOT EXISTS llm_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('A', 'B', 'C')),
    full_prompt TEXT NOT NULL,
    full_response TEXT NOT NULL,
    model TEXT NOT NULL,
    temperature REAL,
    max_tokens INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cycle_id) REFERENCES router_decisions(cycle_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_router_decisions_cycle_id ON router_decisions(cycle_id);
CREATE INDEX IF NOT EXISTS idx_router_decisions_session_id ON router_decisions(session_id);
CREATE INDEX IF NOT EXISTS idx_interactions_cycle_id ON interactions(cycle_id);
CREATE INDEX IF NOT EXISTS idx_task_state_cycle_id ON task_state(cycle_id);
CREATE INDEX IF NOT EXISTS idx_step_outputs_cycle_id ON step_outputs(cycle_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_cycle_id ON chat_history(cycle_id);
CREATE INDEX IF NOT EXISTS idx_llm_traces_cycle_id ON llm_traces(cycle_id);
CREATE INDEX IF NOT EXISTS idx_intention_cache_tool ON intention_cache(tool_name);
CREATE INDEX IF NOT EXISTS idx_intention_cache_success ON intention_cache(success_flag);
"""


def init_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Initialize orchestrator database with complete schema.
    
    Idempotent: Safe to call multiple times.
    Creates logs/ directory if it doesn't exist.
    
    Args:
        db_path: Path to database file (default: logs/orchestrator.db)
    
    Returns:
        sqlite3.Connection: Database connection
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    
    # Ensure logs directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect and enable foreign keys
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Execute schema
    conn.executescript(CREATE_TABLES)
    
    # Record schema version
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
        (SCHEMA_VERSION,)
    )
    conn.commit()
    
    return conn


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get current schema version."""
    cursor = conn.execute("SELECT MAX(version) FROM schema_version")
    result = cursor.fetchone()
    return result[0] if result and result[0] is not None else 0
