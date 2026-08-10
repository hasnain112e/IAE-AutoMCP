"""
Production query safety — extends existing QueryValidator rules with:
  - Prompt injection stripping
  - Multi-pattern SQL AST-style blocking
  - Audit logging per session
"""
from __future__ import annotations
import re
from datetime import datetime

# Import and reuse existing rules
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agents.database_agent.safety_checks import QueryValidator as _BaseValidator

# Per-session audit log
_audit: dict[str, list[dict]] = {}


DESTRUCTIVE_SQL = _BaseValidator.DESTRUCTIVE_SQL
DESTRUCTIVE_MONGO = _BaseValidator.DESTRUCTIVE_MONGO

# Additional patterns to catch obfuscated attacks
_SQL_INJECTION_PATTERNS = [
    r";\s*(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|RENAME)\b",
    r"--\s*(DROP|DELETE|UPDATE|INSERT)",
    r"/\*.*?(DROP|DELETE|UPDATE)\s+.*?\*/",
    r"\bOR\s+1\s*=\s*1\b",
    r"\bOR\s+'[^']*'\s*=\s*'[^']*'",
]


class ProductionQueryValidator:

    # ── Prompt injection guard ─────────────────────────────────────────────

    @staticmethod
    def strip_prompt_injection(text: str) -> str:
        """Remove embedded SQL commands from natural language input."""
        # Strip SQL command sequences that look injected
        cleaned = re.sub(
            r"(?i)(;\s*)?(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE)\s+\w+[^;]*",
            "[REMOVED]", text
        )
        return cleaned.strip()

    # ── SQL safety ─────────────────────────────────────────────────────────

    @staticmethod
    def is_safe_sql(query: str) -> tuple[bool, str]:
        """Validate SQL is read-only SELECT. Returns (is_safe, reason)."""
        # Use base validator first
        ok, reason = _BaseValidator.is_safe_sql_query(query)
        if not ok:
            return False, reason

        # Extra injection pattern check
        for pattern in _SQL_INJECTION_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return False, f"Potential SQL injection pattern detected"

        return True, "Query is safe"

    # ── MongoDB safety ─────────────────────────────────────────────────────

    @staticmethod
    def is_safe_mongo(operation: str, filter_doc: dict) -> tuple[bool, str]:
        """Validate MongoDB operation is read-only."""
        return _BaseValidator.is_safe_mongo_operation(operation, filter_doc)

    @staticmethod
    def is_safe_mongo_filter(filter_doc: dict) -> tuple[bool, str]:
        """Block filter documents that contain MongoDB write operators."""
        return _BaseValidator.is_safe_mongo_query(filter_doc)

    # ── Audit log ──────────────────────────────────────────────────────────

    @staticmethod
    def log(session_id: str, query: str, safe: bool, reason: str):
        if session_id not in _audit:
            _audit[session_id] = []
        _audit[session_id].append({
            "query": query[:300],
            "safe": safe,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        })

    @staticmethod
    def get_audit(session_id: str) -> list[dict]:
        return _audit.get(session_id, [])

    @staticmethod
    def clear_audit(session_id: str):
        _audit.pop(session_id, None)

    # ── Combined validate + log ────────────────────────────────────────────

    @classmethod
    def validate_sql(cls, session_id: str, query: str) -> tuple[bool, str]:
        safe, reason = cls.is_safe_sql(query)
        cls.log(session_id, query, safe, reason)
        return safe, reason

    @classmethod
    def validate_mongo(cls, session_id: str, operation: str, filter_doc: dict) -> tuple[bool, str]:
        safe, reason = cls.is_safe_mongo(operation, filter_doc)
        if safe:
            safe, reason = cls.is_safe_mongo_filter(filter_doc)
        cls.log(session_id, f"{operation}({filter_doc})", safe, reason)
        return safe, reason
