"""
Utility script to purge orchestrator database state.

Usage:
    python -m memory.purge_db --yes
"""

import argparse
import sqlite3
from pathlib import Path

from memory.api import Memory
from memory.schema import DEFAULT_DB_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Purge orchestrator memory so only fresh cycles remain."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to orchestrator database (default: logs/orchestrator.db)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--include-sessions",
        action="store_true",
        help="Also delete session metadata"
    )
    parser.add_argument(
        "--include-cache",
        action="store_true",
        help="Also delete intention cache entries"
    )
    parser.add_argument(
        "--force-reset",
        action="store_true",
        help="If the database is corrupt, delete and recreate it"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    
    if not args.yes:
        prompt = (
            f"This will delete orchestrator data from {args.db}. "
            "Type 'yes' to continue: "
        )
        confirmation = input(prompt).strip().lower()
        if confirmation not in {"y", "yes"}:
            print("Aborted.")
            return 1
    
    memory = Memory(db_path=args.db)
    try:
        memory.purge_all_data(
            include_sessions=args.include_sessions,
            include_intention_cache=args.include_cache
        )
        print(f"Purged orchestrator data from {args.db}.")
        return 0
    except sqlite3.DatabaseError as exc:
        memory.close(force=True)
        if not args.force_reset:
            raise
        if args.db.exists():
            args.db.unlink()
        # Recreate empty database
        Memory(db_path=args.db).close(force=True)
        print(f"{args.db} was corrupt. Deleted and recreated a fresh database.")
        return 0
    finally:
        try:
            memory.close(force=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
