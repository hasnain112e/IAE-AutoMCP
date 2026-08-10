"""Database Agent API Routes"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import re
import json
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.database_agent.database_agent import DatabaseAgent
from agents.database_agent.safety_checks import QueryValidator

router = APIRouter(prefix="/database", tags=["database"])

_shared_agent = DatabaseAgent()
_validator = QueryValidator()


def _fresh():
    return DatabaseAgent()


def _reset_shared():
    global _shared_agent
    _shared_agent = DatabaseAgent()


# ── models ─────────────────────────────────────────────────────────────────

class SqlBody(BaseModel):
    query: str

class MongoBody(BaseModel):
    collection: str
    filter: dict = {}

class AgentQueryBody(BaseModel):
    question: str
    db_preference: str = "postgresql"


# ── health / reset ─────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "phase": _shared_agent.safety_engine.phase_manager.current_phase,
        "frozen": _shared_agent.safety_engine.phase_manager.is_frozen(),
    }


@router.post("/reset")
async def reset():
    _reset_shared()
    return {"success": True, "message": "Agent reset to clean state"}


# ── shared step endpoints ───────────────────────────────────────────────────

@router.post("/explore-schema")
async def explore_schema():
    return await _shared_agent.explore_schema()


@router.post("/query/employees")
async def query_employees(db_type: str = "postgresql"):
    return await _shared_agent.query_employees(db_type)


@router.post("/query/payrolls")
async def query_payrolls(db_type: str = "postgresql", emp_id: Optional[str] = None):
    return await _shared_agent.query_payrolls(emp_id, db_type)


@router.post("/query/departments")
async def query_departments(db_type: str = "postgresql"):
    return await _shared_agent.query_departments(db_type)


@router.post("/test-destructive/{query_type}")
async def test_destructive(query_type: str):
    return await _shared_agent.try_destructive_query(query_type)


@router.post("/freeze")
async def freeze_operations():
    return await _shared_agent.freeze_operations()


@router.get("/safety-report")
async def get_safety_report():
    return await _shared_agent.get_safety_report()


# ── PostgreSQL custom SQL query ─────────────────────────────────────────────

@router.post("/pg/execute")
async def pg_execute(body: SqlBody):
    """Run any safe SELECT query against mock PostgreSQL."""
    is_safe, reason = _validator.is_safe_sql_query(body.query)
    if not is_safe:
        return {"success": False, "blocked": True, "reason": reason, "query": body.query}

    if _shared_agent.safety_engine.phase_manager.is_frozen():
        return {"success": False, "blocked": True, "reason": "Database is frozen.", "query": body.query}

    match = re.search(r'\bFROM\s+(\w+)', body.query, re.IGNORECASE)
    if not match:
        return {"success": False, "error": "Could not parse table name from query."}

    table = match.group(1).lower()
    pg = _shared_agent.db_manager.postgresql
    if table not in pg.tables:
        return {"success": False, "error": f"Table '{table}' not found. Available: {list(pg.tables.keys())}"}

    # Parse WHERE col = val (string or numeric)
    where_match = re.search(r'\bWHERE\s+(\w+)\s*=\s*[\'"]?(\w+)[\'"]?', body.query, re.IGNORECASE)
    where = None
    if where_match:
        col, raw_val = where_match.group(1), where_match.group(2)
        # Try numeric cast so integer columns match
        try:
            val = int(raw_val)
        except ValueError:
            val = raw_val
        where = {col: val}

    _shared_agent.db_manager.log_query("postgresql", "custom_sql", {"query": body.query})
    rows = pg.select(table, where)
    return {"success": True, "query": body.query, "table": table, "data": rows, "count": len(rows)}


# ── MongoDB custom find ─────────────────────────────────────────────────────

@router.post("/mongo/find")
async def mongo_find(body: MongoBody):
    """Run a safe find() against mock MongoDB."""
    is_safe, reason = _validator.is_safe_mongo_operation("find", {})
    if not is_safe:
        return {"success": False, "blocked": True, "reason": reason}

    if _shared_agent.safety_engine.phase_manager.is_frozen():
        return {"success": False, "blocked": True, "reason": "Database is frozen."}

    mongo = _shared_agent.db_manager.mongodb
    if body.collection not in mongo.collections:
        return {"success": False, "error": f"Collection '{body.collection}' not found. Available: {list(mongo.collections.keys())}"}

    _shared_agent.db_manager.log_query("mongodb", "find", {"collection": body.collection, "filter": body.filter})
    results = mongo.find(body.collection, body.filter if body.filter else None)
    return {"success": True, "collection": body.collection, "filter": body.filter, "data": results, "count": len(results)}


# ── AI Agent natural-language query ────────────────────────────────────────

@router.post("/agent/query")
async def agent_query(body: AgentQueryBody):
    """Natural language → agent writes its own SQL/Mongo queries → returns answer."""
    try:
        from agents.database_agent.query_agent import DatabaseQueryAgent
        agent = DatabaseQueryAgent()
        result = await asyncio.to_thread(agent.run, body.question)
        return result
    except ValueError as e:
        return {"success": False, "error": str(e), "answer": "OpenAI API key not configured."}
    except Exception as e:
        return {"success": False, "error": str(e), "answer": f"Agent error: {e}"}


# ── auto run ────────────────────────────────────────────────────────────────

@router.post("/run-full-test")
async def run_full_test(db_type: str = "postgresql"):
    """Run complete workflow on a fresh agent for one database."""
    agent = _fresh()
    try:
        explore   = await agent.explore_schema()
        employees = await agent.query_employees(db_type)
        payrolls  = await agent.query_payrolls(db_type=db_type)
        depts     = await agent.query_departments(db_type)
        dest_del  = await agent.try_destructive_query("delete")
        dest_drop = await agent.try_destructive_query("drop")
        report    = await agent.get_safety_report()

        return {
            "success": True,
            "db_type": db_type,
            "workflow": {
                "exploration":      explore,
                "employee_query":   employees,
                "payroll_query":    payrolls,
                "dept_query":       depts,
                "destructive_delete": dest_del,
                "destructive_drop":   dest_drop,
                "safety_report":    report,
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
