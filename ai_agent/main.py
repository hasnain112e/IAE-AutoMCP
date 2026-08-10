"""
AI Database Exploration Agent — FastAPI entry point.

Starts on port 8010 (configurable via AI_AGENT_PORT env var).
Run with:  python -m uvicorn ai_agent.main:app --host 127.0.0.1 --port 8010 --workers 1

IMPORTANT: Use --workers 1 only. The session store and MCP global lock are
in-process state that cannot be shared across multiple worker processes.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Project root must be on sys.path before any agents.* or shared.* imports
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .logger import configure_logging
from .config import agent_config
from .api.routes import router

configure_logging()

import logging
_logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Database Exploration Agent",
    description=(
        "An AI-powered agent that understands natural language queries, "
        "analyzes database schemas, generates safe read-only queries, "
        "and returns summarized results. "
        "Backed by a vLLM-hosted model and the existing MCP server tools."
    ),
    version="1.0.0",
    docs_url="/ai-agent/docs",
    redoc_url="/ai-agent/redoc",
    openapi_url="/ai-agent/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def _startup() -> None:
    _logger.info(
        "AI Database Agent started | host=%s | port=%s | model=%s | vllm_url=%s",
        agent_config.AI_AGENT_HOST,
        agent_config.AI_AGENT_PORT,
        agent_config.OPENAI_MODEL,
        agent_config.OPENAI_BASE_URL or "(default OpenAI)",
    )
    _logger.info("Docs available at http://%s:%s/ai-agent/docs",
                 agent_config.AI_AGENT_HOST, agent_config.AI_AGENT_PORT)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "ai_agent.main:app",
        host=agent_config.AI_AGENT_HOST,
        port=agent_config.AI_AGENT_PORT,
        workers=1,
        reload=False,
    )
