"""
10 MCP tools for the production DB Explorer.
Tools run against a shared connector set by the API layer.
"""
from __future__ import annotations
import json
import os
from fastmcp import FastMCP
from openai import OpenAI

from .safety import ProductionQueryValidator
from .schema_manager import SchemaManager
from .query_optimizer import QueryOptimizer

mcp = FastMCP("DB Explorer MCP")

# Connector injected at runtime by the API layer
_connector = None
_session_id = "mcp_default"


def set_connector(connector, session_id: str = "mcp_default"):
    global _connector, _session_id
    _connector = connector
    _session_id = session_id


def _openai():
    kwargs = {"api_key": os.getenv("OPENAI_API_KEY")}
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


# ── Tool 1: get_schema ────────────────────────────────────────────────────────

@mcp.tool()
async def get_schema() -> dict:
    """Return the full database schema (tables → columns)."""
    if not _connector:
        return {"error": "No database connected"}
    return _connector.get_schema()


# ── Tool 2: get_tables ────────────────────────────────────────────────────────

@mcp.tool()
async def get_tables() -> list[dict]:
    """List all tables/collections with their row counts."""
    if not _connector:
        return [{"error": "No database connected"}]
    schema = _connector.get_schema()
    counts = _connector.get_row_counts()
    return [{"name": t, "row_count": counts.get(t, 0), "columns": len(cols)}
            for t, cols in schema.items()]


# ── Tool 3: get_collections ───────────────────────────────────────────────────

@mcp.tool()
async def get_collections() -> list[str]:
    """List MongoDB collection names (MongoDB only)."""
    if not _connector:
        return ["No database connected"]
    schema = _connector.get_schema()
    return list(schema.keys())


# ── Tool 4: sample_data ───────────────────────────────────────────────────────

@mcp.tool()
async def sample_data(table: str, limit: int = 5) -> list[dict]:
    """Return sample rows/documents from a table or collection."""
    if not _connector:
        return [{"error": "No database connected"}]
    try:
        return _connector.sample(table, limit)
    except Exception as e:
        return [{"error": str(e)}]


# ── Tool 5: run_sql_query ─────────────────────────────────────────────────────

@mcp.tool()
async def run_sql_query(query: str) -> dict:
    """Execute a validated SELECT query on the SQL database."""
    if not _connector:
        return {"success": False, "error": "No database connected"}
    safe, reason = ProductionQueryValidator.validate_sql(_session_id, query)
    if not safe:
        return {"success": False, "blocked": True, "reason": reason, "query": query}
    try:
        rows = _connector.execute_sql(query)
        return {"success": True, "query": query, "data": rows, "count": len(rows)}
    except Exception as e:
        return {"success": False, "error": str(e), "query": query}


# ── Tool 6: run_mongo_query ───────────────────────────────────────────────────

@mcp.tool()
async def run_mongo_query(collection: str, filter_json: str = "{}", projection_json: str = "{}") -> dict:
    """Execute a find() on a MongoDB collection."""
    if not _connector:
        return {"success": False, "error": "No database connected"}
    try:
        filter_doc = json.loads(filter_json) if filter_json.strip() else {}
        proj = json.loads(projection_json) if projection_json.strip() not in ("{}", "") else None
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON in filter: {e}"}
    safe, reason = ProductionQueryValidator.validate_mongo(_session_id, "find", filter_doc)
    if not safe:
        return {"success": False, "blocked": True, "reason": reason}
    try:
        docs = _connector.execute_find(collection, filter_doc, proj)
        return {"success": True, "collection": collection, "data": docs, "count": len(docs)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 7: validate_query ────────────────────────────────────────────────────

@mcp.tool()
async def validate_query(query: str, db_type: str = "postgresql") -> dict:
    """Check if a query is safe to execute (read-only validation)."""
    if db_type == "mongodb":
        safe, reason = ProductionQueryValidator.is_safe_mongo("find", {})
    else:
        safe, reason = ProductionQueryValidator.is_safe_sql(query)
    return {"safe": safe, "reason": reason, "query": query}


# ── Tool 8: explain_query ─────────────────────────────────────────────────────

@mcp.tool()
async def explain_query(query: str) -> str:
    """Return a plain English explanation of what a query does."""
    prompt = (
        f"Explain this database query in simple, plain English for a non-technical user.\n"
        f"Be concise (2-3 sentences max).\n\nQuery:\n{query}"
    )
    try:
        client = _openai()
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=200
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Could not explain query: {e}"


# ── Tool 9: optimize_query ────────────────────────────────────────────────────

@mcp.tool()
async def optimize_query(query: str) -> dict:
    """Suggest optimizations for a SQL query."""
    cached = SchemaManager.cache_get(_session_id)
    context = SchemaManager.summarize(cached) if cached else ""
    opt = QueryOptimizer()
    result = opt.optimize(query, context, "")
    return {
        "original": result["original"],
        "optimized": result["optimized"],
        "notes": result["notes"],
        "changed": result["changed"]
    }


# ── Tool 10: summarize_schema ─────────────────────────────────────────────────

@mcp.tool()
async def summarize_schema() -> str:
    """Return a compact summary of the full schema for LLM consumption."""
    cached = SchemaManager.cache_get(_session_id)
    if cached:
        return SchemaManager.summarize(cached)
    if not _connector:
        return "No database connected"
    data = SchemaManager.extract_sync(_connector)
    return SchemaManager.summarize(data)


if __name__ == "__main__":
    mcp.run()
