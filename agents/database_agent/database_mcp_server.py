"""FastMCP Server wrapping DatabaseAgent — exposes mock MongoDB & PostgreSQL as MCP tools."""
import re
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastmcp import FastMCP
from agents.database_agent.database_agent import DatabaseAgent
from agents.database_agent.safety_checks import QueryValidator

mcp = FastMCP("Database MCP Server")

# Single stateful agent per server session
_agent = DatabaseAgent()
_validator = QueryValidator()


@mcp.tool()
async def explore_schema() -> dict:
    """Phase 1 — discover all PostgreSQL tables and MongoDB collections.
    Must be called before running queries."""
    return await _agent.explore_schema()


@mcp.tool()
async def query_employees(db_type: str = "postgresql") -> dict:
    """Read all employee records.

    Args:
        db_type: 'postgresql' or 'mongodb'
    """
    return await _agent.query_employees(db_type=db_type)


@mcp.tool()
async def query_payrolls(emp_id: str = None, db_type: str = "postgresql") -> dict:
    """Read payroll records, optionally filtered by employee ID.

    Args:
        emp_id: Employee ID to filter by (e.g. '1' for PostgreSQL, 'emp_001' for MongoDB). Leave empty for all.
        db_type: 'postgresql' or 'mongodb'
    """
    return await _agent.query_payrolls(emp_id=emp_id, db_type=db_type)


@mcp.tool()
async def query_departments(db_type: str = "postgresql") -> dict:
    """Read all department records.

    Args:
        db_type: 'postgresql' or 'mongodb'
    """
    return await _agent.query_departments(db_type=db_type)


@mcp.tool()
async def execute_sql_query(query: str) -> dict:
    """Execute a safe read-only SQL SELECT query against the mock PostgreSQL database.
    DELETE, DROP, UPDATE, INSERT and other destructive statements are blocked.

    Args:
        query: A SQL SELECT statement, e.g. 'SELECT * FROM employees'
    """
    is_safe, reason = _validator.is_safe_sql_query(query)
    if not is_safe:
        _agent.safety_engine.blocked_queries.append({
            "db_type": "postgresql",
            "query": query,
            "reason": reason
        })
        _agent.safety_engine.query_log.append({
            "db_type": "postgresql",
            "query": query,
            "is_safe": False,
            "message": reason
        })
        return {"success": False, "blocked": True, "reason": reason, "query": query}

    if _agent.safety_engine.phase_manager.is_frozen():
        return {"success": False, "blocked": True, "reason": "Operations are frozen.", "query": query}

    # Parse table name from "SELECT ... FROM <table>"
    match = re.search(r'\bFROM\s+(\w+)', query, re.IGNORECASE)
    if not match:
        return {"success": False, "error": "Could not parse table name from query.", "query": query}

    table = match.group(1).lower()
    pg = _agent.db_manager.postgresql

    if table not in pg.tables:
        return {"success": False, "error": f"Table '{table}' not found. Available: {list(pg.tables.keys())}", "query": query}

    _agent.safety_engine.query_log.append({
        "db_type": "postgresql",
        "query": query,
        "is_safe": True,
        "message": "Safe query"
    })
    _agent.db_manager.log_query("postgresql", "execute_sql_query", {"query": query, "table": table})

    rows = pg.select(table)
    return {"success": True, "query": query, "table": table, "data": rows, "count": len(rows)}


@mcp.tool()
async def execute_mongo_find(collection: str, filter_json: str = "{}") -> dict:
    """Execute a safe MongoDB find() query against the mock MongoDB database.
    Destructive operations (deleteOne, updateOne, insertOne, etc.) are blocked.

    Args:
        collection: Collection name — 'employees', 'payrolls', or 'departments'
        filter_json: JSON string filter, e.g. '{"status": "active"}'. Default is '{}'.
    """
    is_safe, reason = _validator.is_safe_mongo_operation("find", {})
    if not is_safe:
        return {"success": False, "blocked": True, "reason": reason}

    if _agent.safety_engine.phase_manager.is_frozen():
        return {"success": False, "blocked": True, "reason": "Operations are frozen."}

    mongo = _agent.db_manager.mongodb
    if collection not in mongo.collections:
        return {
            "success": False,
            "error": f"Collection '{collection}' not found. Available: {list(mongo.collections.keys())}"
        }

    try:
        query_filter = json.loads(filter_json) if filter_json.strip() else {}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid filter_json: {e}"}

    _agent.db_manager.log_query("mongodb", "find", {"collection": collection, "filter": query_filter})
    results = mongo.find(collection, query_filter if query_filter else None)
    return {"success": True, "collection": collection, "filter": query_filter, "data": results, "count": len(results)}


@mcp.tool()
async def freeze_database() -> dict:
    """Freeze all database operations. After this, no queries can run until the server restarts."""
    return await _agent.freeze_operations()


@mcp.tool()
async def get_safety_report() -> dict:
    """Return the full audit trail: query counts, blocked queries, and current phase status."""
    return await _agent.get_safety_report()


if __name__ == "__main__":
    mcp.run()
