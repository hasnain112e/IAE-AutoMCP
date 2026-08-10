"""
FastAPI router for /ai-agent/* endpoints.

All business logic lives in Pipeline. This layer only:
  - Validates that a session exists for session-scoped routes
  - Delegates to the pipeline
  - Returns Pydantic response models
"""
from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.db_explorer.connectors import connector_factory
from agents.db_explorer.schema_manager import SchemaManager

from ..agent.pipeline import Pipeline, SessionState
from ..config import agent_config
from ..mcp_client.proxy import MCPToolProxy
from ..models.requests import ConnectRequest, QueryRequest
from ..models.responses import (
    AuditResponse,
    ConnectResponse,
    HealthResponse,
    HistoryResponse,
    QueryResponse,
    SchemaResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-agent", tags=["AI Database Agent"])

# Pipeline singleton — created once when the module is first imported
_pipeline = Pipeline(agent_config)


def _require_session(session_id: str) -> None:
    if not _pipeline.get_session(session_id):
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. Call POST /ai-agent/connect first.",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/connect", response_model=ConnectResponse, summary="Connect to a database")
async def connect(body: ConnectRequest) -> ConnectResponse:
    """
    Connect to a PostgreSQL or MongoDB database.
    Returns a `session_id` used for all subsequent requests.
    """
    return await _pipeline.connect(body)


@router.post(
    "/query/{session_id}",
    response_model=QueryResponse,
    summary="Natural language query",
)
async def query(session_id: str, body: QueryRequest) -> QueryResponse:
    """
    Submit a natural language question. The agent runs the two-phase pipeline:
    **Phase 1** — understand intent, analyze schema, generate query, explain plan.
    **Phase 2** — validate safety, optimize, execute via MCP server, summarize results.
    """
    _require_session(session_id)
    return await _pipeline.run_query(session_id, body.question)


@router.get(
    "/schema/{session_id}",
    response_model=SchemaResponse,
    summary="Fetch live database schema",
)
async def get_schema(session_id: str) -> SchemaResponse:
    """Return the full schema (tables/columns or collections/fields) via the MCP server."""
    _require_session(session_id)
    return await _pipeline.get_schema(session_id)


@router.get(
    "/history/{session_id}",
    response_model=HistoryResponse,
    summary="Query history",
)
async def get_history(session_id: str) -> HistoryResponse:
    """Return all natural language queries executed in this session."""
    _require_session(session_id)
    return await _pipeline.get_history(session_id)


@router.get(
    "/audit/{session_id}",
    response_model=AuditResponse,
    summary="Security audit log",
)
async def get_audit(session_id: str) -> AuditResponse:
    """Return the full security audit trail (every query validated — safe or blocked)."""
    _require_session(session_id)
    return await _pipeline.get_audit(session_id)


@router.delete("/session/{session_id}", summary="Disconnect session")
async def disconnect(session_id: str) -> dict:
    """Disconnect the database connection and clean up session state."""
    _require_session(session_id)
    await _pipeline.disconnect(session_id)
    return {"success": True, "message": f"Session '{session_id}' disconnected."}


@router.post("/upload", response_model=ConnectResponse, summary="Upload a file as database")
async def upload(file: UploadFile = File(...)) -> ConnectResponse:
    """
    Upload a CSV, SQLite (.db/.sqlite), SQL dump, or JSON file.
    The agent will treat it as a queryable database.
    """
    try:
        content  = await file.read()
        filename = file.filename or "upload"

        def _make():
            connector = connector_factory("file", filename=filename, content=content)
            connector.connect()
            return connector

        import uuid
        from datetime import datetime, timezone

        connector = await asyncio.to_thread(_make)
        session_id = str(uuid.uuid4())
        proxy = MCPToolProxy(connector, session_id)
        schema_dict = await proxy.get_schema()
        schema_data = {"schema": schema_dict, "counts": {}, "samples": {}}
        SchemaManager.cache_set(session_id, schema_data)

        state = SessionState(
            session_id=session_id,
            connector=connector,
            proxy=proxy,
            db_type=f"file:{filename}",
            schema_cache=schema_data,
        )
        _pipeline._add_session(session_id, state)

        logger.info("upload | session=%s | file=%s | tables=%d", session_id, filename, len(schema_dict))
        return ConnectResponse(
            success=True,
            session_id=session_id,
            db_type=f"file:{filename}",
            table_count=len(schema_dict),
            tables=list(schema_dict.keys()),
        )
    except Exception as exc:
        logger.exception("upload failed | file=%s", getattr(file, "filename", "?"))
        return ConnectResponse(success=False, error=str(exc))


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health() -> HealthResponse:
    """Service health check — returns status and active session count."""
    return HealthResponse(
        status="healthy",
        service="ai-database-agent",
        port=agent_config.AI_AGENT_PORT,
        active_sessions=_pipeline.active_session_count(),
    )
