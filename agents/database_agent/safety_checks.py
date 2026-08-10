"""Safety Checks for Read-Only Database Access"""
import re
from typing import Tuple, List

class QueryValidator:
    """Validate queries to ensure read-only operations"""

    # Destructive SQL keywords
    DESTRUCTIVE_SQL = {
        'DELETE', 'DROP', 'TRUNCATE', 'INSERT', 'UPDATE',
        'CREATE', 'ALTER', 'RENAME', 'MODIFY', 'EXEC',
        'EXECUTE', 'GRANT', 'REVOKE', 'PRAGMA'
    }

    # Dangerous MongoDB operations
    DESTRUCTIVE_MONGO = {
        'deleteOne', 'deleteMany', 'dropCollection', 'drop',
        'updateOne', 'updateMany', 'findOneAndDelete', 'findOneAndUpdate',
        'insertOne', 'insertMany', 'replaceOne', 'bulkWrite'
    }

    # MongoDB write operators that must never appear in a filter/query doc
    DESTRUCTIVE_MONGO_OPERATORS = {
        '$set', '$unset', '$push', '$pull', '$pop', '$rename',
        '$inc', '$mul', '$addToSet', '$pullAll', '$setOnInsert',
        '$currentDate', '$bit', '$isolated', '$out', '$merge',
    }

    @staticmethod
    def is_safe_sql_query(query: str) -> Tuple[bool, str]:
        """Check if SQL query is read-only"""
        # Remove comments and normalize
        cleaned = QueryValidator._clean_query(query)
        tokens = cleaned.upper().split()

        if not tokens:
            return False, "Empty query"

        # First keyword must be SELECT
        if tokens[0] != 'SELECT':
            dangerous_op = next((t for t in tokens if t in QueryValidator.DESTRUCTIVE_SQL), None)
            if dangerous_op:
                return False, f"Destructive operation not allowed: {dangerous_op}"
            return False, "Only SELECT queries allowed"

        # Check for dangerous keywords anywhere
        for token in tokens:
            if token in QueryValidator.DESTRUCTIVE_SQL:
                return False, f"Destructive keyword not allowed: {token}"

        return True, "Safe query"

    @staticmethod
    def is_safe_mongo_query(filter_doc: dict) -> Tuple[bool, str]:
        """Block MongoDB filter documents containing write operators."""
        import json
        raw = json.dumps(filter_doc)
        for op in QueryValidator.DESTRUCTIVE_MONGO_OPERATORS:
            if op in raw:
                return False, f"Write operator not allowed in query: {op}"
        return True, "Safe filter"

    @staticmethod
    def is_safe_mongo_operation(operation: str, details: dict) -> Tuple[bool, str]:
        """Check if MongoDB operation is read-only"""
        # Check operation name
        for danger_op in QueryValidator.DESTRUCTIVE_MONGO:
            if danger_op.lower() in operation.lower():
                return False, f"Destructive operation not allowed: {danger_op}"

        # Allowed read operations
        allowed_ops = {
            'find', 'findone', 'finall', 'aggregate',
            'count', 'distinct', 'explain', 'indexinformation'
        }

        if not any(allowed in operation.lower() for allowed in allowed_ops):
            return False, f"Only read operations allowed, got: {operation}"

        return True, "Safe operation"

    @staticmethod
    def _clean_query(query: str) -> str:
        """Remove comments from query"""
        # Remove line comments
        query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
        # Remove block comments
        query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)
        return query.strip()


class OperationPhase:
    """Track and enforce operation phases"""

    PHASE_EXPLORATION = "exploration"
    PHASE_FREEZE = "freeze"

    def __init__(self):
        self.current_phase = self.PHASE_EXPLORATION
        self.schema_discovered = False
        self.discovered_tables = []
        self.discovery_count = 0

    def mark_schema_explored(self, tables: List[str]):
        """Mark schema as explored"""
        self.schema_discovered = True
        self.discovered_tables = tables
        self.discovery_count += 1

    def freeze(self):
        """Freeze operations - move to freeze phase"""
        self.current_phase = self.PHASE_FREEZE

    def is_frozen(self) -> bool:
        """Check if operations are frozen"""
        return self.current_phase == self.PHASE_FREEZE

    def can_discover(self) -> bool:
        """Check if agent can discover schema"""
        return self.current_phase == self.PHASE_EXPLORATION

    def get_status(self) -> dict:
        """Get phase status"""
        return {
            "current_phase": self.current_phase,
            "is_frozen": self.is_frozen(),
            "schema_discovered": self.schema_discovered,
            "discovered_tables": self.discovered_tables,
            "discovery_count": self.discovery_count
        }


class SafetyCheckEngine:
    """Main engine for safety enforcement"""

    def __init__(self):
        self.validator = QueryValidator()
        self.phase_manager = OperationPhase()
        self.query_log = []
        self.blocked_queries = []

    def validate_query(self, db_type: str, query_or_op: str, details: dict = None) -> Tuple[bool, str]:
        """Validate query before execution"""
        if self.phase_manager.is_frozen():
            return False, "Operations are frozen. Cannot execute queries in freeze phase."

        if db_type.lower() == 'postgresql':
            is_safe, message = self.validator.is_safe_sql_query(query_or_op)
        elif db_type.lower() == 'mongodb':
            is_safe, message = self.validator.is_safe_mongo_operation(query_or_op, details or {})
        else:
            return False, f"Unknown database type: {db_type}"

        if not is_safe:
            self.blocked_queries.append({
                "db_type": db_type,
                "query": query_or_op,
                "reason": message
            })

        self.query_log.append({
            "db_type": db_type,
            "query": query_or_op,
            "is_safe": is_safe,
            "message": message
        })

        return is_safe, message

    def move_to_freeze(self):
        """Transition to freeze phase"""
        self.phase_manager.freeze()

    def get_safety_report(self) -> dict:
        """Get security report"""
        return {
            "total_queries_attempted": len(self.query_log),
            "safe_queries": sum(1 for q in self.query_log if q['is_safe']),
            "blocked_queries": len(self.blocked_queries),
            "phase_status": self.phase_manager.get_status(),
            "blocked_query_details": self.blocked_queries[-10:],  # Last 10
        }
