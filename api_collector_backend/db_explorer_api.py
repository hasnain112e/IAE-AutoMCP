"""
Production DB Explorer API Routes — /db-explorer/*
Session-based: each connect/upload gets a session_id.
Agent is fully synchronous — wrapped in asyncio.to_thread for FastAPI.
"""
from __future__ import annotations
import asyncio
import csv
import io
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.db_explorer.connectors import connector_factory
from agents.db_explorer.explorer_agent import ExplorerAgent
from agents.db_explorer.schema_manager import SchemaManager
from agents.db_explorer.safety import ProductionQueryValidator

router = APIRouter(prefix="/db-explorer", tags=["db-explorer"])

# ── Session store ─────────────────────────────────────────────────────────────
_sessions: dict[str, dict] = {}


def _sess(session_id: str) -> dict:
    s = _sessions.get(session_id)
    if not s:
        raise KeyError(f"Session '{session_id}' not found. Connect or upload first.")
    return s


# ── Models ────────────────────────────────────────────────────────────────────

class ConnectBody(BaseModel):
    db_type: str
    uri: str = ""
    host: str = "localhost"
    port: int = 5432
    dbname: str = ""
    username: str = ""
    password: str = ""

class QueryBody(BaseModel):
    question: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session(connector, db_type_label: str) -> tuple[str, dict, dict]:
    """Connect, explore schema, register session. Returns (session_id, schema_result, session)."""
    connector.connect()
    session_id = str(uuid.uuid4())
    agent = ExplorerAgent(connector, session_id)
    schema_result = agent.explore_schema()      # sync
    sess = {
        "connector": connector,
        "agent": agent,
        "db_type": db_type_label,
        "history": [],
        "created_at": datetime.now().isoformat(),
    }
    _sessions[session_id] = sess
    return session_id, schema_result, sess


# ── 1. Connect via URI / credentials ─────────────────────────────────────────

@router.post("/connect")
async def connect(body: ConnectBody):
    try:
        kwargs = body.model_dump(exclude={"db_type"})
        def _do():
            connector = connector_factory(body.db_type, **kwargs)
            sid, result, _ = _make_session(connector, body.db_type)
            return sid, result
        sid, result = await asyncio.to_thread(_do)
        return {"success": True, "session_id": sid, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 2. Upload file ────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    try:
        content = await file.read()
        filename = file.filename or "upload"
        def _do():
            connector = connector_factory("file", filename=filename, content=content)
            sid, result, _ = _make_session(connector, f"file:{filename}")
            return sid, result
        sid, result = await asyncio.to_thread(_do)
        return {"success": True, "session_id": sid, "filename": filename, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 3. Re-explore schema ──────────────────────────────────────────────────────

@router.post("/explore/{session_id}")
async def explore_schema(session_id: str):
    try:
        sess = _sess(session_id)
        agent: ExplorerAgent = sess["agent"]
        result = await asyncio.to_thread(agent.explore_schema)
        return {"success": True, **result}
    except KeyError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 4. Natural language query ─────────────────────────────────────────────────

@router.post("/query/{session_id}")
async def query(session_id: str, body: QueryBody):
    try:
        sess = _sess(session_id)
        agent: ExplorerAgent = sess["agent"]
        result = await asyncio.to_thread(agent.query, body.question)
        sess["history"].append({
            "question": body.question,
            "query": result.get("generated_query", ""),
            "row_count": result.get("row_count", 0),
            "timestamp": result.get("timestamp", datetime.now().isoformat()),
        })
        return result
    except KeyError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 5. Query history ──────────────────────────────────────────────────────────

@router.get("/history/{session_id}")
async def get_history(session_id: str):
    try:
        return {"success": True, "history": _sess(session_id)["history"]}
    except KeyError as e:
        return {"success": False, "error": str(e)}


# ── 6. Export CSV ─────────────────────────────────────────────────────────────

@router.post("/export/{session_id}")
async def export_results(session_id: str, body: QueryBody):
    try:
        sess = _sess(session_id)
        agent: ExplorerAgent = sess["agent"]
        result = await asyncio.to_thread(agent.query, body.question)
        rows = result.get("results", [])
        if not rows:
            return {"success": False, "error": "No data to export"}
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows([{k: str(v) for k, v in row.items()} for row in rows])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="export_{session_id[:8]}.csv"'}
        )
    except KeyError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 7. Disconnect / cleanup ───────────────────────────────────────────────────

@router.delete("/session/{session_id}")
async def disconnect(session_id: str):
    try:
        sess = _sessions.pop(session_id, None)
        if sess:
            def _do():
                sess["connector"].disconnect()
                ProductionQueryValidator.clear_audit(session_id)
                SchemaManager.cache_clear(session_id)
            await asyncio.to_thread(_do)
        return {"success": True, "message": "Session closed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 8. List sessions (debug) ──────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions():
    return {
        "count": len(_sessions),
        "sessions": [
            {"id": sid, "db_type": s["db_type"],
             "created_at": s["created_at"], "queries": len(s["history"])}
            for sid, s in _sessions.items()
        ]
    }
