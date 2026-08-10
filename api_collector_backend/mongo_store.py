"""
MongoDB storage for generated MCP tool collections.

Auto-saves every successful /collect-tools run.
Fail-silent: if MongoDB is unavailable the rest of the app keeps working.
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_client = None


def _get_db():
    global _client
    if _client is None:
        from pymongo import MongoClient
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _client["automcp"]


def save_tools(
    source_type: str,
    source_name: str,
    tools: list,
    output_format: str,
) -> str:
    """Save a tool collection to MongoDB. Returns the document _id."""
    doc_id = str(uuid.uuid4())
    _get_db()["mcp_tools"].insert_one({
        "_id": doc_id,
        "source_type": source_type,
        "source_name": source_name,
        "tool_count": len(tools),
        "tools": [t.model_dump() for t in tools],
        "output_format": output_format,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    logger.info("mongo_store | saved | id=%s | tools=%d | source=%s", doc_id, len(tools), source_name)
    return doc_id


def list_collections(limit: int = 50) -> list[dict]:
    """Return recent tool collections (tools array excluded for performance)."""
    cursor = (
        _get_db()["mcp_tools"]
        .find({}, {"tools": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [{**d, "_id": str(d["_id"])} for d in cursor]


def get_collection(doc_id: str) -> dict | None:
    """Return a full tool collection by ID."""
    doc = _get_db()["mcp_tools"].find_one({"_id": doc_id})
    if not doc:
        return None
    return {**doc, "_id": str(doc["_id"])}


def delete_collection(doc_id: str) -> bool:
    """Delete a tool collection. Returns True if deleted."""
    result = _get_db()["mcp_tools"].delete_one({"_id": doc_id})
    return result.deleted_count > 0


# ── MCP Server storage ────────────────────────────────────────────────────────

def save_mcp_server(
    source_name: str,
    source_type: str,
    generated_code: str,
    tools_count: int,
    api_spec_filename: str = "",
) -> str:
    """Save a generated MCP server to MongoDB. Returns the document _id."""
    doc_id = str(uuid.uuid4())
    _get_db()["mcp_servers"].insert_one({
        "_id": doc_id,
        "source_name": source_name,
        "source_type": source_type,
        "api_spec_filename": api_spec_filename,
        "tools_count": tools_count,
        "generated_code": generated_code,
        "code_lines": generated_code.count("\n") + 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    logger.info("mongo_store | mcp_server saved | id=%s | tools=%d | source=%s", doc_id, tools_count, source_name)
    return doc_id


def list_mcp_servers(limit: int = 50) -> list[dict]:
    """Return recent MCP servers (generated_code excluded for performance)."""
    cursor = (
        _get_db()["mcp_servers"]
        .find({}, {"generated_code": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [{**d, "_id": str(d["_id"])} for d in cursor]


def get_mcp_server(doc_id: str) -> dict | None:
    """Return a full MCP server document by ID (includes generated_code)."""
    doc = _get_db()["mcp_servers"].find_one({"_id": doc_id})
    if not doc:
        return None
    return {**doc, "_id": str(doc["_id"])}


def delete_mcp_server(doc_id: str) -> bool:
    """Delete a stored MCP server. Returns True if deleted."""
    result = _get_db()["mcp_servers"].delete_one({"_id": doc_id})
    return result.deleted_count > 0
