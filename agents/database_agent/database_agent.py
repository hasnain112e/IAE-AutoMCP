"""Database Agent for MCP Testing"""
import asyncio
import json
from typing import Dict, Any, List
from datetime import datetime
from .mock_databases import DatabaseManager
from .safety_checks import SafetyCheckEngine

class DatabaseAgent:
    """Agent for database testing with safety checks"""

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.safety_engine = SafetyCheckEngine()
        self.agent_id = "database_agent"
        self.port = 8103
        self.status = "initialized"
        self.session_log = []

    def log_session(self, action: str, details: Dict[str, Any]):
        """Log session activity"""
        self.session_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details
        })

    async def explore_schema(self) -> Dict[str, Any]:
        """Exploration Phase: Discover database schema"""
        if not self.safety_engine.phase_manager.can_discover():
            return {
                "success": False,
                "error": "Schema exploration is locked. Already in freeze phase."
            }

        self.log_session("explore_schema", {"phase": "exploration"})

        # Explore PostgreSQL
        pg_schema = self.db_manager.postgresql.get_schema()
        mongo_collections = list(self.db_manager.mongodb.collections.keys())

        self.safety_engine.phase_manager.mark_schema_explored(
            list(pg_schema.keys()) + mongo_collections
        )

        return {
            "success": True,
            "phase": "exploration_complete",
            "postgresql_schema": pg_schema,
            "mongodb_collections": mongo_collections,
            "discovered_tables": self.safety_engine.phase_manager.discovered_tables,
            "status": self.safety_engine.phase_manager.get_status()
        }

    async def query_employees(self, db_type: str = "postgresql") -> Dict[str, Any]:
        """Query employees data (READ-ONLY)"""
        # Validate query
        if db_type.lower() == "postgresql":
            query = "SELECT * FROM employees"
            is_safe, message = self.safety_engine.validate_query(db_type, query)
            if not is_safe:
                self.log_session("query_employees", {"success": False, "reason": message})
                return {"success": False, "error": message}

            results = self.db_manager.postgresql.select("employees")
        else:  # mongodb
            is_safe, message = self.safety_engine.validate_query(db_type, "find")
            if not is_safe:
                self.log_session("query_employees", {"success": False, "reason": message})
                return {"success": False, "error": message}

            results = self.db_manager.mongodb.find("employees")

        self.log_session("query_employees", {
            "db_type": db_type,
            "record_count": len(results),
            "success": True
        })

        return {
            "success": True,
            "data": results,
            "count": len(results),
            "db_type": db_type
        }

    async def query_payrolls(self, emp_id: str = None, db_type: str = "postgresql") -> Dict[str, Any]:
        """Query payroll data (READ-ONLY)"""
        if db_type.lower() == "postgresql":
            query = "SELECT * FROM payrolls" + (f" WHERE emp_id = {emp_id}" if emp_id else "")
            is_safe, message = self.safety_engine.validate_query(db_type, query)
            if not is_safe:
                return {"success": False, "error": message}

            where = {"emp_id": int(emp_id)} if emp_id else None
            results = self.db_manager.postgresql.select("payrolls", where)
        else:  # mongodb
            is_safe, message = self.safety_engine.validate_query(db_type, "find")
            if not is_safe:
                return {"success": False, "error": message}

            query_filter = {"emp_id": emp_id} if emp_id else None
            results = self.db_manager.mongodb.find("payrolls", query_filter)

        self.log_session("query_payrolls", {
            "db_type": db_type,
            "emp_id_filter": emp_id,
            "record_count": len(results)
        })

        return {
            "success": True,
            "data": results,
            "count": len(results),
            "db_type": db_type,
            "filtered_by_emp_id": emp_id
        }

    async def query_departments(self, db_type: str = "postgresql") -> Dict[str, Any]:
        """Query departments (READ-ONLY)"""
        if db_type.lower() == "postgresql":
            query = "SELECT * FROM departments"
            is_safe, message = self.safety_engine.validate_query(db_type, query)
            if not is_safe:
                return {"success": False, "error": message}

            results = self.db_manager.postgresql.select("departments")
        else:  # mongodb
            is_safe, message = self.safety_engine.validate_query(db_type, "find")
            if not is_safe:
                return {"success": False, "error": message}

            results = self.db_manager.mongodb.find("departments")

        self.log_session("query_departments", {
            "db_type": db_type,
            "record_count": len(results)
        })

        return {
            "success": True,
            "data": results,
            "count": len(results),
            "db_type": db_type
        }

    async def try_destructive_query(self, query_type: str) -> Dict[str, Any]:
        """Test destructive query (will be blocked)"""
        queries = {
            "delete": "DELETE FROM employees WHERE id = 1",
            "drop": "DROP TABLE employees",
            "update": "UPDATE employees SET salary = 200000 WHERE id = 1",
            "insert": "INSERT INTO employees VALUES (...)"
        }

        query = queries.get(query_type, "UNKNOWN")
        is_safe, message = self.safety_engine.validate_query("postgresql", query)

        self.log_session("try_destructive_query", {
            "query_type": query_type,
            "is_safe": is_safe,
            "blocked_reason": message
        })

        return {
            "success": False,
            "query": query,
            "is_safe": is_safe,
            "blocked_reason": message
        }

    async def freeze_operations(self) -> Dict[str, Any]:
        """Freeze Phase: Lock all operations"""
        self.safety_engine.move_to_freeze()
        self.log_session("freeze_operations", {"status": "frozen"})

        return {
            "success": True,
            "phase": "freeze_activated",
            "message": "All database operations are now frozen",
            "status": self.safety_engine.phase_manager.get_status()
        }

    async def get_safety_report(self) -> Dict[str, Any]:
        """Get comprehensive safety report"""
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "timestamp": datetime.now().isoformat(),
            "safety_metrics": self.safety_engine.get_safety_report(),
            "phase_status": self.safety_engine.phase_manager.get_status(),
            "session_activity": self.session_log[-20:],  # Last 20 events
            "blocked_queries": self.safety_engine.blocked_queries
        }

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming messages from other agents"""
        action = message.get("action")
        data = message.get("data", {})

        handlers = {
            "explore_schema": self.explore_schema,
            "query_employees": lambda: self.query_employees(data.get("db_type", "postgresql")),
            "query_payrolls": lambda: self.query_payrolls(data.get("emp_id"), data.get("db_type", "postgresql")),
            "query_departments": lambda: self.query_departments(data.get("db_type", "postgresql")),
            "try_destructive_query": lambda: self.try_destructive_query(data.get("type", "delete")),
            "freeze_operations": self.freeze_operations,
            "get_safety_report": self.get_safety_report,
            "health": self._health_check,
        }

        handler = handlers.get(action)
        if handler:
            try:
                result = await handler()
                return {
                    "success": True,
                    "action": action,
                    "result": result
                }
            except Exception as e:
                return {
                    "success": False,
                    "action": action,
                    "error": str(e)
                }

        return {
            "success": False,
            "error": f"Unknown action: {action}"
        }

    async def _health_check(self) -> Dict[str, Any]:
        """Health check endpoint"""
        return {
            "status": "healthy",
            "agent_id": self.agent_id,
            "port": self.port,
            "timestamp": datetime.now().isoformat()
        }


# Global agent instance
database_agent = DatabaseAgent()
