"""
Schema Migration System for Orchestrator Memory

Idempotent migrations with version tracking.
Allows future schema changes without breaking existing databases.
"""

import sqlite3
from typing import Callable, List, Tuple

from memory.schema import get_schema_version


Migration = Tuple[int, str, Callable[[sqlite3.Connection], None]]


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def migrate_v1_to_v2(conn: sqlite3.Connection):
    """
    Expand step_outputs with structured stdout/stderr + parsed value slots.
    """
    columns = [
        ("stdout", "TEXT"),
        ("stderr", "TEXT"),
        ("raw_stdout", "BLOB"),
        ("raw_stderr", "BLOB"),
        ("output_format_json", "TEXT"),
        ("parsed_outputs_json", "TEXT"),
    ]
    
    for name, ddl in columns:
        if not _column_exists(conn, "step_outputs", name):
            conn.execute(f"ALTER TABLE step_outputs ADD COLUMN {name} {ddl}")
    
    conn.commit()


def migrate_v2_to_v3(conn: sqlite3.Connection):
    """
    Create metrics tables (route_metrics, step_metrics, llm_metrics) inside the primary schema.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS route_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route TEXT NOT NULL,
            confidence REAL,
            latency_ms INTEGER,
            cache_hit INTEGER DEFAULT 0,
            interactive INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS step_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            step_id INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            success INTEGER NOT NULL,
            latency_ms INTEGER,
            output_size_bytes INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            latency_ms INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def migrate_v3_to_v4(conn: sqlite3.Connection):
    """Replace route_metrics with route-less cycle_metrics."""
    conn.execute("DROP TABLE IF EXISTS route_metrics")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cycle_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id TEXT NOT NULL,
            used_plan INTEGER NOT NULL,
            latency_ms INTEGER,
            interactive INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cycle_id) REFERENCES router_decisions(cycle_id)
        )
        """
    )
    conn.commit()


# Registry of all migrations (version, description, migration function)
MIGRATIONS: List[Migration] = [
    (2, "Expand step_outputs for structured outputs", migrate_v1_to_v2),
    (3, "Create metrics tables in unified schema", migrate_v2_to_v3),
    (4, "Swap route_metrics for route-less cycle_metrics", migrate_v3_to_v4),
]


def apply_migrations(conn: sqlite3.Connection, target_version: int = None):
    """
    Apply pending migrations to bring database to target version.
    
    Args:
        conn: Database connection
        target_version: Target schema version (None = latest)
    
    Idempotent: Safe to call multiple times.
    """
    current_version = get_schema_version(conn)
    
    if target_version is None:
        target_version = max([v for v, _, _ in MIGRATIONS], default=current_version)
    
    # Filter migrations that need to be applied
    pending = [
        (v, desc, fn) for v, desc, fn in MIGRATIONS
        if v > current_version and v <= target_version
    ]
    
    if not pending:
        return  # No migrations needed
    
    # Apply migrations in order
    for version, description, migration_fn in sorted(pending):
        print(f"Applying migration v{version}: {description}")
        
        # Run migration
        migration_fn(conn)
        
        # Record version
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (version,)
        )
        conn.commit()
        
        print(f"✓ Migration v{version} complete")


def verify_schema(conn: sqlite3.Connection) -> bool:
    """
    Verify database schema is complete and valid.
    
    Checks:
    - All required tables exist
    - FTS5 virtual table configured
    - Indexes created
    - Foreign keys enabled
    
    Returns:
        True if schema is valid
    """
    required_tables = [
        'schema_version',
        'sessions',
        'router_decisions',
        'intention_cache',
        'intention_cache_fts',
        'interactions',
        'task_state',
        'step_outputs',
        'chat_history',
        'llm_traces',
        'cycle_metrics',
        'step_metrics',
        'llm_metrics'
    ]
    
    # Check foreign keys enabled
    cursor = conn.execute("PRAGMA foreign_keys")
    fk_enabled = cursor.fetchone()[0]
    if not fk_enabled:
        print("❌ Foreign keys not enabled")
        return False
    
    # Check all tables exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    existing_tables = {row[0] for row in cursor.fetchall()}
    
    missing = set(required_tables) - existing_tables
    if missing:
        print(f"❌ Missing tables: {missing}")
        return False
    
    # Check FTS5 triggers exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'intention_cache_%'"
    )
    triggers = [row[0] for row in cursor.fetchall()]
    expected_triggers = ['intention_cache_ai', 'intention_cache_ad', 'intention_cache_au']
    
    if set(triggers) != set(expected_triggers):
        print(f"❌ FTS5 triggers missing or incomplete: {triggers}")
        return False
    
    # Check critical indexes exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )
    indexes = [row[0] for row in cursor.fetchall()]
    
    required_indexes = [
        'idx_router_decisions_cycle_id',
        'idx_interactions_cycle_id',
        'idx_task_state_cycle_id',
        'idx_chat_history_session_id'
    ]
    
    missing_indexes = set(required_indexes) - set(indexes)
    if missing_indexes:
        print(f"❌ Missing indexes: {missing_indexes}")
        return False
    
    print("✓ Schema verification passed")
    return True


def get_migration_status(conn: sqlite3.Connection) -> dict:
    """
    Get migration status summary.
    
    Returns:
        Dict with current_version, latest_version, pending_count
    """
    current = get_schema_version(conn)
    latest = max([v for v, _, _ in MIGRATIONS], default=current)
    pending = sum(1 for v, _, _ in MIGRATIONS if v > current)
    
    return {
        "current_version": current,
        "latest_version": latest,
        "pending_migrations": pending,
        "up_to_date": current >= latest
    }
