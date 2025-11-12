"""
Telemetry and Metrics Collection for v2.0 Orchestrator

Tracks:
- Route distribution (SHELL, CACHED, CHAT, PLANNER)
- Latency per route
- Cache hit rates
- Plan validity and step success rates
- Token usage per role (Agent A/B/C)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class RouteMetrics:
    """Metrics for a single route classification"""
    route: str
    confidence: float
    latency_ms: int
    cache_hit: bool = False
    interactive: bool = False
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


@dataclass
class StepMetrics:
    """Metrics for a step execution (PLANNER route)"""
    step_id: int
    tool_name: str
    success: bool
    latency_ms: int
    output_size_bytes: int = 0
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


@dataclass
class LLMMetrics:
    """Metrics for LLM calls"""
    role: str  # A, B, or C
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class MetricsCollector:
    """
    Collects and aggregates telemetry data.
    
    Metrics are persisted to the orchestrator.db metrics table.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize metrics collector with database path"""
        from memory.schema import DEFAULT_DB_PATH
        self.db_path = db_path or DEFAULT_DB_PATH
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Create metrics tables if they don't exist"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Route metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS route_metrics (
                id INTEGER PRIMARY KEY,
                route TEXT NOT NULL,
                confidence REAL,
                latency_ms INTEGER,
                cache_hit INTEGER DEFAULT 0,
                interactive INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Step metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS step_metrics (
                id INTEGER PRIMARY KEY,
                step_id INTEGER NOT NULL,
                tool_name TEXT NOT NULL,
                success INTEGER NOT NULL,
                latency_ms INTEGER,
                output_size_bytes INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # LLM metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_metrics (
                id INTEGER PRIMARY KEY,
                role TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                latency_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def record_route_metric(self, metric: RouteMetrics):
        """Record route classification metric"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO route_metrics (route, confidence, latency_ms, cache_hit, interactive)
            VALUES (?, ?, ?, ?, ?)
        """, (metric.route, metric.confidence, metric.latency_ms, 
              int(metric.cache_hit), int(metric.interactive)))
        
        conn.commit()
        conn.close()
    
    def record_step_metric(self, metric: StepMetrics):
        """Record step execution metric"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO step_metrics (step_id, tool_name, success, latency_ms, output_size_bytes)
            VALUES (?, ?, ?, ?, ?)
        """, (metric.step_id, metric.tool_name, int(metric.success), 
              metric.latency_ms, metric.output_size_bytes))
        
        conn.commit()
        conn.close()
    
    def record_llm_metric(self, metric: LLMMetrics):
        """Record LLM call metric"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO llm_metrics (role, model, prompt_tokens, completion_tokens, latency_ms)
            VALUES (?, ?, ?, ?, ?)
        """, (metric.role, metric.model, metric.prompt_tokens, 
              metric.completion_tokens, metric.latency_ms))
        
        conn.commit()
        conn.close()
    
    def get_route_distribution(self, limit_hours: int = 24) -> Dict[str, int]:
        """
        Get route distribution for recent queries.
        
        Args:
            limit_hours: Time window (default: last 24 hours)
        
        Returns:
            Dict with route -> count mapping
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT route, COUNT(*) as count
            FROM route_metrics
            WHERE created_at >= datetime('now', '-{limit_hours} hours')
            GROUP BY route
            ORDER BY count DESC
        """)
        
        results = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return results
    
    def get_latency_stats(self, route: Optional[str] = None, limit_hours: int = 24) -> Dict[str, Any]:
        """
        Get latency statistics.
        
        Args:
            route: Optional route filter (None = all routes)
            limit_hours: Time window
        
        Returns:
            Dict with avg, min, max, p50, p95 latencies
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        where_clause = ""
        params = []
        
        if route:
            where_clause = "WHERE route = ? AND "
            params.append(route)
        else:
            where_clause = "WHERE "
        
        where_clause += f"created_at >= datetime('now', '-{limit_hours} hours')"
        
        cursor.execute(f"""
            SELECT 
                AVG(latency_ms) as avg,
                MIN(latency_ms) as min,
                MAX(latency_ms) as max,
                COUNT(*) as count
            FROM route_metrics
            {where_clause}
        """, params)
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"error": "No data"}
        
        avg, min_latency, max_latency, count = row
        
        # Get percentiles
        cursor.execute(f"""
            SELECT latency_ms
            FROM route_metrics
            {where_clause}
            ORDER BY latency_ms
        """, params)
        
        latencies = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        if not latencies:
            return {"error": "No data"}
        
        latencies.sort()
        p50_idx = int(len(latencies) * 0.5)
        p95_idx = int(len(latencies) * 0.95)
        
        return {
            "route": route or "all",
            "count": count,
            "avg_ms": round(avg, 2) if avg else 0,
            "min_ms": min_latency or 0,
            "max_ms": max_latency or 0,
            "p50_ms": latencies[p50_idx] if p50_idx < len(latencies) else 0,
            "p95_ms": latencies[p95_idx] if p95_idx < len(latencies) else 0,
        }
    
    def get_cache_hit_rate(self, limit_hours: int = 24) -> Dict[str, Any]:
        """
        Get cache hit rate statistics.
        
        Args:
            limit_hours: Time window
        
        Returns:
            Dict with cache hit rate and counts
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT 
                SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END) as hits,
                COUNT(*) as total,
                SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as hit_rate
            FROM route_metrics
            WHERE created_at >= datetime('now', '-{limit_hours} hours')
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        if not row or row[1] == 0:
            return {"error": "No data"}
        
        hits, total, hit_rate = row
        return {
            "hits": hits or 0,
            "total": total or 0,
            "hit_rate_percent": round(hit_rate, 2) if hit_rate else 0,
        }
    
    def get_planner_stats(self, limit_hours: int = 24) -> Dict[str, Any]:
        """
        Get PLANNER route step success statistics.
        
        Args:
            limit_hours: Time window
        
        Returns:
            Dict with success rate by tool
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT 
                tool_name,
                COUNT(*) as total,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                AVG(latency_ms) as avg_latency_ms
            FROM step_metrics
            WHERE created_at >= datetime('now', '-{limit_hours} hours')
            GROUP BY tool_name
            ORDER BY total DESC
        """)
        
        results = {}
        for row in cursor.fetchall():
            tool_name, total, successful, avg_latency = row
            success_rate = (successful / total * 100) if total > 0 else 0
            results[tool_name] = {
                "total_calls": total,
                "successful": successful or 0,
                "success_rate_percent": round(success_rate, 2),
                "avg_latency_ms": round(avg_latency, 2) if avg_latency else 0,
            }
        
        conn.close()
        return results
    
    def get_llm_stats(self, limit_hours: int = 24) -> Dict[str, Any]:
        """
        Get LLM call statistics by role.
        
        Args:
            limit_hours: Time window
        
        Returns:
            Dict with token usage and latency by role
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT 
                role,
                COUNT(*) as calls,
                SUM(prompt_tokens) as total_prompt_tokens,
                SUM(completion_tokens) as total_completion_tokens,
                AVG(latency_ms) as avg_latency_ms
            FROM llm_metrics
            WHERE created_at >= datetime('now', '-{limit_hours} hours')
            GROUP BY role
            ORDER BY calls DESC
        """)
        
        results = {}
        for row in cursor.fetchall():
            role, calls, prompt_tokens, completion_tokens, avg_latency = row
            results[f"Agent_{role}"] = {
                "calls": calls,
                "prompt_tokens": prompt_tokens or 0,
                "completion_tokens": completion_tokens or 0,
                "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0),
                "avg_latency_ms": round(avg_latency, 2) if avg_latency else 0,
            }
        
        conn.close()
        return results
    
    def get_summary_report(self, limit_hours: int = 24) -> Dict[str, Any]:
        """
        Get a comprehensive telemetry report.
        
        Args:
            limit_hours: Time window
        
        Returns:
            Dict with all metrics aggregated
        """
        return {
            "time_window_hours": limit_hours,
            "route_distribution": self.get_route_distribution(limit_hours),
            "cache_hit_rate": self.get_cache_hit_rate(limit_hours),
            "latency_stats": {
                "all": self.get_latency_stats(None, limit_hours),
                "shell": self.get_latency_stats("SHELL", limit_hours),
                "cached": self.get_latency_stats("CACHED", limit_hours),
                "chat": self.get_latency_stats("CHAT", limit_hours),
                "planner": self.get_latency_stats("PLANNER", limit_hours),
            },
            "planner_stats": self.get_planner_stats(limit_hours),
            "llm_stats": self.get_llm_stats(limit_hours),
        }


# Global metrics collector instance
_metrics_instance: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get or create global metrics collector instance"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = MetricsCollector()
    return _metrics_instance
