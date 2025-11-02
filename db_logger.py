import sqlite3
import json
import os
from datetime import datetime


class DBLogger:
    """SQLite-based structured logging for AI Terminal sessions"""
    
    def __init__(self, db_path: str = "logs/session_logs.db"):
        """Initialize database connection and ensure tables exist"""
        self.db_path = db_path
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        
        # Connect to database (removed check_same_thread for safety)
        self.conn = sqlite3.connect(db_path)
        
        # Enable pragmas for better performance and safety
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Create tables if they don't exist"""
        cursor = self.conn.cursor()
        
        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                system_info TEXT NOT NULL
            )
        """)
        
        # Log entries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS log_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
        """)
        
        self.conn.commit()
    
    def start_session(self, system_info: dict) -> int:
        """Start a new session and return the session ID"""
        cursor = self.conn.cursor()
        start_time = datetime.now().isoformat()
        system_info_json = json.dumps(system_info)
        
        cursor.execute(
            "INSERT INTO sessions (start_time, system_info) VALUES (?, ?)",
            (start_time, system_info_json)
        )
        self.conn.commit()
        
        return cursor.lastrowid
    
    def log_entry(self, session_id: int, log_type: str, content: str):
        """Log an entry for a specific session"""
        cursor = self.conn.cursor()
        timestamp = datetime.now().isoformat()
        
        cursor.execute(
            "INSERT INTO log_entries (session_id, timestamp, type, content) VALUES (?, ?, ?, ?)",
            (session_id, timestamp, log_type, content)
        )
        self.conn.commit()
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
