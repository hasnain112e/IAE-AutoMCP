"""AI Agent configuration — extends shared ServiceConfig with agent-specific knobs."""
from __future__ import annotations
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path before importing shared modules
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from shared.config import ServiceConfig


class AgentConfig(ServiceConfig):
    AI_AGENT_PORT: int = int(os.getenv("AI_AGENT_PORT", "8010"))
    AI_AGENT_HOST: str = os.getenv("AI_AGENT_HOST", "127.0.0.1")

    OPENAI_BASE_URL: str | None = os.getenv("OPENAI_BASE_URL")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "qwen3.5-9b")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "EMPTY")

    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "600"))
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "60.0"))

    MAX_RETRY_ATTEMPTS: int = int(os.getenv("MAX_RETRY_ATTEMPTS", "1"))
    MAX_RESULT_ROWS: int = int(os.getenv("MAX_RESULT_ROWS", "500"))
    SESSION_TTL_HOURS: int = int(os.getenv("SESSION_TTL_HOURS", "24"))


agent_config = AgentConfig()
