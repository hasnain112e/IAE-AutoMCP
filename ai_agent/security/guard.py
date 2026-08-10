"""
SecurityGuard — read-only enforcement layer wrapping ProductionQueryValidator.

Adds supplementary patterns not covered by the base validator:
- SQL: EXEC, MSSQL extended procs (XP_*), UNION-based schema enumeration
- MongoDB: JS-eval operators ($where, $function, $accumulator)

Also fixes the MCP server's internal mongo validation gap — that check always
passes {} as the filter doc, so it never inspects the actual filter content.
This guard parses and validates the real filter before execution.
"""
from __future__ import annotations
import json
import logging
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.db_explorer.safety import ProductionQueryValidator

logger = logging.getLogger(__name__)

_EXTRA_SQL_PATTERNS: list[tuple[str, str]] = [
    (r"\bEXEC(?:UTE)?\b", "EXEC/EXECUTE blocked"),
    (r"\bXP_\w+", "MSSQL extended procedure blocked"),
    (r"UNION\s+(?:ALL\s+)?SELECT.{0,200}information_schema", "Schema enumeration via UNION blocked"),
    (r";\s*WAITFOR\s+DELAY", "Time-based injection blocked"),
]

_BLOCKED_MONGO_OPS: frozenset[str] = frozenset({
    "$where", "$function", "$accumulator",
})


class SecurityGuard:

    @staticmethod
    def validate(query: str, db_type: str, session_id: str) -> tuple[bool, str]:
        """
        Primary entry point. Returns (is_safe, reason).
        Logs every decision to the audit trail.
        """
        if db_type == "mongodb":
            return SecurityGuard._validate_mongo(query, session_id)
        return SecurityGuard._validate_sql(query, session_id)

    @staticmethod
    def _validate_sql(query: str, session_id: str) -> tuple[bool, str]:
        is_safe, reason = ProductionQueryValidator.validate_sql(session_id, query)
        if not is_safe:
            logger.warning("SecurityGuard SQL block | session=%s | reason=%s", session_id, reason)
            return False, reason

        for pattern, label in _EXTRA_SQL_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE | re.DOTALL):
                ProductionQueryValidator.log(session_id, query, False, label)
                logger.warning("SecurityGuard extra-pattern block | session=%s | label=%s", session_id, label)
                return False, label

        return True, "Query is safe"

    @staticmethod
    def _validate_mongo(filter_json: str, session_id: str) -> tuple[bool, str]:
        try:
            parsed: dict = json.loads(filter_json) if filter_json.strip() else {}
        except json.JSONDecodeError:
            reason = "Invalid JSON in MongoDB filter"
            ProductionQueryValidator.log(session_id, filter_json, False, reason)
            logger.warning("SecurityGuard invalid JSON | session=%s", session_id)
            return False, reason

        blocked_op = SecurityGuard._find_blocked_mongo_op(parsed)
        if blocked_op:
            reason = f"Blocked MongoDB operator: {blocked_op}"
            ProductionQueryValidator.log(session_id, filter_json, False, reason)
            logger.warning("SecurityGuard mongo-op block | session=%s | op=%s", session_id, blocked_op)
            return False, reason

        # Delegate to base validator with the actual parsed filter
        is_safe, reason = ProductionQueryValidator.validate_mongo(session_id, "find", parsed)
        if not is_safe:
            logger.warning("SecurityGuard mongo base-validator block | session=%s | reason=%s", session_id, reason)
        return is_safe, reason

    @staticmethod
    def _find_blocked_mongo_op(obj) -> str | None:
        """Recursively search for blocked MongoDB operators."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in _BLOCKED_MONGO_OPS:
                    return k
                found = SecurityGuard._find_blocked_mongo_op(v)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = SecurityGuard._find_blocked_mongo_op(item)
                if found:
                    return found
        return None

    @staticmethod
    def get_audit(session_id: str) -> list[dict]:
        return ProductionQueryValidator.get_audit(session_id)
