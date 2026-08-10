# Edited by Dr. Wasim
"""
Routes that wrap System A (generator-only) to produce drafts for System B.

POST /draft/generate
- Calls mcp-generator/agent_mcp_generator.py to generate a draft
- Requires tools (with base_url + path) to be supplied
- Returns a draft payload; no validation is performed here.
"""
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Ensure mcp-generator is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MCP_GEN_DIR = os.path.join(_PROJECT_ROOT, "mcp-generator")
if _MCP_GEN_DIR not in sys.path:
    sys.path.insert(0, _MCP_GEN_DIR)

# Lazy import: System A generator (do not re-implement).
def _load_generator():
    try:
        from agent_mcp_generator import generate_mcp_code  # type: ignore
        return generate_mcp_code
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail="System A generator dependency missing (e.g., google.genai). Ensure requirements are installed.",
        ) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Failed to load System A generator: {exc}") from exc

router = APIRouter(prefix="/api")


class DraftGenerateRequest(BaseModel):
    context_id: str
    prompt: Optional[str] = None
    tools: List[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]] = None


class DraftGenerateResponse(BaseModel):
    context_id: str
    draft_id: str
    generated_output: str
    tools_used: List[Dict[str, Any]]
    source: str = Field(default="generator-only")
    validated: bool = Field(default=False)
    metadata: Dict[str, Any]


def _validate_tools(tools: List[Dict[str, Any]]) -> None:
    if not tools:
        raise HTTPException(status_code=400, detail="Tools are required before generation.")
    for t in tools:
        if not t.get("base_url"):
            raise HTTPException(status_code=400, detail=f"Tool '{t.get('name', '<unknown>')}' missing base_url.")
        if not t.get("path"):
            raise HTTPException(status_code=400, detail=f"Tool '{t.get('name', '<unknown>')}' missing path.")


@router.post("/draft/generate", response_model=DraftGenerateResponse)
async def generate_draft(payload: DraftGenerateRequest) -> DraftGenerateResponse:
    _validate_tools(payload.tools)

    draft_id = str(uuid.uuid4())
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mcp_root = os.path.join(project_root, "mcp-generator")
    drafts_dir = os.path.join(mcp_root, "drafts")
    os.makedirs(drafts_dir, exist_ok=True)

    # Write tools to a temporary spec file for System A generator
    spec_path = os.path.join(drafts_dir, f"tools_{draft_id}.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(payload.tools, f, indent=2)

    # Use System A generator to create draft code
    try:
        generate_mcp_code = _load_generator()
        output_path = os.path.join(drafts_dir, f"draft_{draft_id}.py")
        generated_output = await generate_mcp_code(spec_path, output_path=output_path, incremental=False)
        if generated_output is None and os.path.exists(output_path):
            with open(output_path, "r", encoding="utf-8") as outf:
                generated_output = outf.read()
        if not generated_output:
            raise RuntimeError("System A generator returned empty output.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Draft generation failed: {exc}") from exc

    meta = payload.metadata or {}
    meta.update(
        {
            "confidence": meta.get("confidence", 0.72),
            "assumptions": meta.get("assumptions", []),
            "created_at": datetime.utcnow().isoformat(),
        }
    )

    return DraftGenerateResponse(
        context_id=payload.context_id,
        draft_id=draft_id,
        generated_output=generated_output,
        tools_used=payload.tools,
        metadata=meta,
    )
