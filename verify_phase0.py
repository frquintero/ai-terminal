#!/usr/bin/env python3
"""
Phase 0 Dependency Verification Script
Checks all foundational assumptions for Context v2 implementation
"""

import os
import sys
import sqlite3
from pathlib import Path

def check_memory_module():
    """Verify memory module has required methods."""
    print("📦 Checking memory module...")
    try:
        from memory.api import Memory
        
        # Check log_interaction method exists
        if not hasattr(Memory, 'log_interaction'):
            print("  ❌ Memory.log_interaction() method NOT FOUND")
            return False
        print("  ✅ Memory.log_interaction() exists")
        
        # Check create_session method exists
        if not hasattr(Memory, 'create_session'):
            print("  ❌ Memory.create_session() method NOT FOUND")
            return False
        print("  ✅ Memory.create_session() exists")
        
        # Check get_session method exists
        if not hasattr(Memory, 'get_session'):
            print("  ❌ Memory.get_session() method NOT FOUND")
            return False
        print("  ✅ Memory.get_session() exists")
        
        return True
    except ImportError as e:
        print(f"  ❌ Cannot import memory.api: {e}")
        return False

def check_database_schema():
    """Verify database tables exist."""
    print("\n🗄️  Checking database schema...")
    
    db_path = Path("logs/orchestrator.db")
    if not db_path.exists():
        print(f"  ⚠️  Database not found at {db_path} (will be created on first run)")
        return True  # OK - will be created
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check interactions table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='interactions'"
        )
        if not cursor.fetchone():
            print("  ❌ interactions table NOT FOUND")
            return False
        print("  ✅ interactions table exists")
        
        # Check sessions table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        )
        if not cursor.fetchone():
            print("  ❌ sessions table NOT FOUND")
            return False
        print("  ✅ sessions table exists")
        
        # Check sessions.system_info_json column
        cursor.execute("PRAGMA table_info(sessions)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'system_info_json' not in columns:
            print("  ❌ sessions.system_info_json column NOT FOUND")
            return False
        print("  ✅ sessions.system_info_json column exists")
        
        # Check router_decisions table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='router_decisions'"
        )
        if not cursor.fetchone():
            print("  ❌ router_decisions table NOT FOUND")
            return False
        print("  ✅ router_decisions table exists")
        
        # Check task_state table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='task_state'"
        )
        if not cursor.fetchone():
            print("  ❌ task_state table NOT FOUND")
            return False
        print("  ✅ task_state table exists")
        
        # Check step_outputs table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='step_outputs'"
        )
        if not cursor.fetchone():
            print("  ❌ step_outputs table NOT FOUND")
            return False
        print("  ✅ step_outputs table exists")
        
        # Check chat_history table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_history'"
        )
        if not cursor.fetchone():
            print("  ❌ chat_history table NOT FOUND")
            return False
        print("  ✅ chat_history table exists")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"  ❌ Database error: {e}")
        return False

def check_orchestrator_integration():
    """Verify orchestrator uses memory methods."""
    print("\n🔗 Checking orchestrator integration...")
    
    try:
        from orchestrator.orchestrator import Orchestrator
        
        # Check if orchestrator file contains create_session call
        orchestrator_file = Path("orchestrator/orchestrator.py")
        if not orchestrator_file.exists():
            print("  ❌ orchestrator.py NOT FOUND")
            return False
        
        content = orchestrator_file.read_text()
        
        if 'create_session' not in content:
            print("  ❌ Orchestrator doesn't call create_session()")
            return False
        print("  ✅ Orchestrator calls create_session()")
        
        if 'system_info' not in content:
            print("  ❌ Orchestrator doesn't populate system_info")
            return False
        print("  ✅ Orchestrator populates system_info")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error checking orchestrator: {e}")
        return False

def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Phase 0: Dependency Verification")
    print("Context v2 Implementation Prerequisites")
    print("=" * 60)
    
    checks = [
        ("Memory Module", check_memory_module),
        ("Database Schema", check_database_schema),
        ("Orchestrator Integration", check_orchestrator_integration),
    ]
    
    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} check FAILED with exception: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
        if not result:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n🎉 All checks passed! Ready for Phase 1a implementation.")
        return 0
    else:
        print("\n⚠️  Some checks failed. Fix issues before proceeding.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
