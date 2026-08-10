"""
Session orchestration for the AI Agent.
Manages creation of connectors, MCP proxy, planner, executor, and session state.
Provides async methods to connect, run a query, fetch schema, history, audit, and cleanup.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import AgentConfig
from ..models.requests import ConnectRequest, QueryRequest
from ..models.responses import (
    ConnectResponse,
    QueryResponse,
    SchemaResponse,
    HistoryResponse,
    AuditResponse,
    HealthResponse,
)
from ..mcp_client.proxy import MCPToolProxy
from ..security.guard import SecurityGuard
from ..agent.planner import Planner
from ..agent.executor import Executor
from ..agent.reasoner import Reasoner
from agents.db_explorer.connectors import BaseConnector, connector_factory

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    session_id: str
    connector: BaseConnector
    proxy: MCPToolProxy
    db_type: str
    schema_cache: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Pipeline:
    """Core service handling session lifecycle and query processing."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._sessions: Dict[str, SessionState] = {}
        self._reasoner = Reasoner(config)
        self._planner = Planner(self._reasoner)
        self._executor = Executor(self._reasoner, config)

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Return the session state for session_id, or None if not found."""
        return self._sessions.get(session_id)

    def _add_session(self, session_id: str, state: SessionState) -> None:
        """Register an externally-constructed session (e.g. file upload)."""
        self._sessions[session_id] = state

    def active_session_count(self) -> int:
        return len(self._sessions)

    async def connect(self, req: ConnectRequest) -> ConnectResponse:
        """Establish a connector to the requested DB and create a session."""
        try:
            connector: BaseConnector = connector_factory(
                req.db_type,
                uri=req.uri or "",
                host=req.host or "localhost",
                port=req.port or (27017 if req.db_type == "mongodb" else 5432),
                dbname=req.dbname or "",
                username=req.username or "",
                password=req.password or "",
            )
            await asyncio.to_thread(connector.connect)
            session_id = str(uuid.uuid4())
            proxy = MCPToolProxy(connector, session_id)
            schema = await proxy.get_schema()
            state = SessionState(
                session_id=session_id,
                connector=connector,
                proxy=proxy,
                db_type=req.db_type,
                schema_cache={"schema": schema},
            )
            self._sessions[session_id] = state
            tables = list(schema.keys())
            return ConnectResponse(
                success=True,
                session_id=session_id,
                db_type=req.db_type,
                table_count=len(tables),
                tables=tables,
            )
        except Exception as exc:
            logger.exception("Pipeline.connect failed")
            return ConnectResponse(success=False, error=str(exc))

    async def run_query(self, session_id: str, question: str) -> QueryResponse:
        """Convenience wrapper: accepts a plain string instead of QueryRequest."""
        return await self.query(session_id, QueryRequest(question=question))

    async def query(self, session_id: str, req: QueryRequest) -> QueryResponse:
        """Run the full two-phase pipeline for a user question."""
        state = self._sessions.get(session_id)
        if not state:
            return QueryResponse(
                success=False, session_id=session_id,
                question="", error="Invalid session_id",
            )
        plan = await self._planner.plan(req.question, state.proxy, state.db_type)
        execution = await self._executor.execute(plan, state.proxy, session_id)
        state.history.append({
            "question": req.question,
            "query": plan.generated_query,
            "row_count": execution.row_count,
            "success": execution.success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return QueryResponse(
            success=True,
            session_id=session_id,
            question=req.question,
            plan=plan,
            execution=execution,
        )

    async def get_schema(self, session_id: str) -> SchemaResponse:
        state = self._sessions.get(session_id)
        if not state:
            return SchemaResponse(success=False, session_id=session_id)
        schema = await state.proxy.get_schema()
        summary = await state.proxy.summarize_schema()
        return SchemaResponse(
            success=True,
            session_id=session_id,
            db_schema=schema,
            summary=summary,
        )

    async def get_history(self, session_id: str) -> HistoryResponse:
        state = self._sessions.get(session_id)
        if not state:
            return HistoryResponse(success=False, session_id=session_id)
        return HistoryResponse(
            success=True,
            session_id=session_id,
            history=state.history,
        )

    async def get_audit(self, session_id: str) -> AuditResponse:
        audit = SecurityGuard.get_audit(session_id)
        return AuditResponse(success=True, session_id=session_id, audit=audit)

    async def disconnect(self, session_id: str) -> dict:
        state = self._sessions.pop(session_id, None)
        if state:
            await asyncio.to_thread(state.connector.disconnect)
            return {"success": True}
        return {"success": False, "error": "Invalid session_id"}

    async def health(self) -> HealthResponse:
        return HealthResponse(
            status="healthy",
            service="ai_agent",
            port=self._config.AI_AGENT_PORT,
            active_sessions=len(self._sessions),
        )
