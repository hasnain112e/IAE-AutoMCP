"""
In-process proxy for the 10 existing MCP server tool functions.

Calls set_connector() to inject the session-specific connector into the MCP
server's module-level global before every tool call.

Thread-safety: _MCP_GLOBAL_LOCK serializes all set_connector + tool call pairs
across ALL sessions, preventing the global from being overwritten mid-execution.
This means concurrent query requests block each other at the MCP layer — acceptable
for correctness; run uvicorn with --workers 1 to match this single-process constraint.
"""
from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import agents.db_explorer.mcp_server as _mcp

logger = logging.getLogger(__name__)

# Serializes set_connector() + subsequent tool call across all concurrent sessions.
_MCP_GLOBAL_LOCK = asyncio.Lock()


def _unwrap(fn):
    """FastMCP may wrap the coroutine in a Tool object; retrieve the original."""
    return getattr(fn, "fn", fn)


class MCPToolProxy:
    """
    Wraps every existing MCP tool function with connector injection.
    Each session instantiates its own proxy bound to its connector.
    """

    def __init__(self, connector, session_id: str) -> None:
        self._connector = connector
        self._session_id = session_id

    async def _call_tool(self, tool_fn, *args, **kwargs):
        async with _MCP_GLOBAL_LOCK:
            _mcp.set_connector(self._connector, self._session_id)
            result = await _unwrap(tool_fn)(*args, **kwargs)
            logger.debug(
                "MCPToolProxy | session=%s | tool=%s | ok",
                self._session_id,
                getattr(tool_fn, "__name__", getattr(tool_fn, "name", repr(tool_fn))),
            )
            return result

    # ── Tool wrappers ─────────────────────────────────────────────────────────

    async def get_schema(self) -> dict:
        return await self._call_tool(_mcp.get_schema)

    async def get_tables(self) -> list:
        return await self._call_tool(_mcp.get_tables)

    async def get_collections(self) -> list:
        return await self._call_tool(_mcp.get_collections)

    async def sample_data(self, table: str, limit: int = 5) -> list:
        return await self._call_tool(_mcp.sample_data, table, limit)

    async def summarize_schema(self) -> str:
        return await self._call_tool(_mcp.summarize_schema)

    async def run_sql_query(self, query: str) -> dict:
        return await self._call_tool(_mcp.run_sql_query, query)

    async def run_mongo_query(
        self,
        collection: str,
        filter_json: str = "{}",
        projection_json: str = "{}",
    ) -> dict:
        return await self._call_tool(
            _mcp.run_mongo_query, collection, filter_json, projection_json
        )

    async def validate_query(self, query: str, db_type: str = "postgresql") -> dict:
        return await self._call_tool(_mcp.validate_query, query, db_type)

    async def optimize_query(self, query: str) -> dict:
        return await self._call_tool(_mcp.optimize_query, query)

    async def explain_query(self, query: str) -> str:
        return await self._call_tool(_mcp.explain_query, query)
