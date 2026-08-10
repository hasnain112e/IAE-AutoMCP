# // Edited by Dr. Wasim
"""
Chat endpoint for interacting with tools via OpenAI API.

OPENAI_API_KEY is read exclusively from backend environment (.env).
Frontend must never see or supply the key; it only sends user messages.
"""
import os
import json
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


# ------------------------ Tool schema conversion ------------------------ #

def tool_to_openai_schema(t: Dict[str, Any]) -> Dict[str, Any]:
    """Convert tool dict to OpenAI function calling schema"""
    params_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    required: List[str] = []

    for p in t.get("parameters", []) or []:
        pname = p.get("name")
        if not pname:
            continue
        ptype = p.get("type", "string")
        desc = p.get("description")
        prop: Dict[str, Any] = {"type": ptype}
        if desc:
            prop["description"] = desc
        params_schema["properties"][pname] = prop
        if p.get("required"):
            required.append(pname)

    if required:
        params_schema["required"] = required

    return {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description") or "",
            "parameters": params_schema,
        },
    }


def _is_sdk_tool(tool: Dict[str, Any]) -> bool:
    meta = tool.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    source = (meta.get("source") or "").strip().lower()
    return source == "python_sdk" or bool(meta.get("sdk_module")) or bool(meta.get("sdk_function"))


def _should_list_all_tools(message: str) -> bool:
    lowered = message.lower()
    wants_list = "list" in lowered or "show" in lowered or "all" in lowered
    targets_tools = "endpoint" in lowered or "endpoints" in lowered or "tools" in lowered or "apis" in lowered
    return wants_list and targets_tools and "first" not in lowered and "top" not in lowered


def _format_tool_list(tools: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for t in tools:
        name = t.get("name") or "<unnamed>"
        method = (t.get("method") or "").upper()
        path = t.get("path") or ""
        meta = t.get("metadata") or {}
        if method and path:
            signature = f"{method} {path}"
        elif meta.get("sdk_module") and meta.get("sdk_function"):
            signature = f"{meta.get('sdk_module')}.{meta.get('sdk_function')}"
        else:
            signature = "N/A"
        lines.append(f"- {name} ({signature})")
    return "\n".join(lines)


# ------------------------ Tool execution ------------------------ #

def _http_call(tool: Dict[str, Any], args: Dict[str, Any], global_config: Dict[str, Any] | None = None) -> Any:
    """Execute HTTP tool call"""
    import httpx
    
    meta = tool.get("metadata", {}) or {}
    base_url = tool.get("base_url") or meta.get("base_url") or ""
    path = tool.get("path", "")
    method = tool.get("method", "GET").upper()
    
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            if method == "GET":
                resp = client.get(url, params=args)
            elif method == "POST":
                resp = client.post(url, json=args)
            elif method == "PUT":
                resp = client.put(url, json=args)
            elif method == "PATCH":
                resp = client.patch(url, json=args)
            elif method == "DELETE":
                resp = client.delete(url, params=args)
            else:
                return {"error": f"Unsupported method: {method}"}
            
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _sdk_call(tool: Dict[str, Any], args: Dict[str, Any]) -> Any:
    """Execute Python SDK tool call"""
    meta = tool.get("metadata", {})
    sdk_module = meta.get("sdk_module")
    sdk_function = meta.get("sdk_function")
    
    if not sdk_module or not sdk_function:
        return {"error": "SDK module or function not specified"}
    
    try:
        import importlib
        mod = importlib.import_module(sdk_module)
        fn = getattr(mod, sdk_function)
        return fn(**args)
    except Exception as e:
        return {"error": str(e)}


def run_tool_call(
    tool_call: Dict[str, Any],
    tools_index: Dict[str, Dict[str, Any]],
    global_config: Dict[str, Any] | None = None,
) -> str:
    fn = tool_call.get("function") or {}
    name = fn.get("name")
    argstr = fn.get("arguments") or "{}"

    try:
        args = json.loads(argstr)
    except Exception:
        args = {}

    t = tools_index.get(name)
    if not t:
        return json.dumps({"error": f"Tool {name} not found."}, ensure_ascii=False)

    meta_raw = t.get("metadata")
    if isinstance(meta_raw, dict):
        meta = meta_raw
    else:
        meta = {}
    
    source = meta.get("source")

    try:
        if source in {"postman_collection", "openapi", "url"}:
            result = _http_call(t, args, global_config)
        elif source == "python_sdk":
            result = _sdk_call(t, args)
        else:
            result = {
                "tool": name,
                "args": args,
                "info": "No executor configured for this source; returning args only.",
            }
    except Exception as e:
        result = {"error": str(e), "tool": name, "args": args}

    return json.dumps(result, ensure_ascii=False)


# --- Helpers ---

def _build_openai_client() -> OpenAI:
    """
    Create an OpenAI client with environment configuration.
    Raises a clear HTTPException if the API key is missing so the frontend
    can surface a user-friendly error instead of a generic 500.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Log the precise issue server-side; return generic error to client
        logger.error("OPENAI_API_KEY missing in backend .env")
        raise HTTPException(
            status_code=500,
            detail="Chat service unavailable. Please contact admin.",
        )

    client_kwargs = {"api_key": api_key}

    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        client_kwargs["base_url"] = base_url

    org_id = os.getenv("OPENAI_ORG_ID")
    if org_id:
        client_kwargs["organization"] = org_id

    project_id = os.getenv("OPENAI_PROJECT_ID")
    if project_id:
        client_kwargs["project"] = project_id

    return OpenAI(**client_kwargs)


def _select_model() -> str:
    """Select model from env with default."""
    env_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    logger.info(f"Using OpenAI model: {env_model}")
    return env_model


# --- New Chat Endpoint ---

class ChatRequest(BaseModel):
    message: str
    tools: List[Dict[str, Any]] | None = None


class ChatResponse(BaseModel):
    reply: str


@router.post("", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Chat entrypoint.
    Frontend sends only the user message; backend handles OpenAI using env key.
    """
    try:
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="Message is required.")
        if request.tools:
            for t in request.tools:
                if not isinstance(t, dict):
                    continue
                if _is_sdk_tool(t):
                    continue
                method = (t.get("method") or "").strip()
                path = (t.get("path") or "").strip()
                if method and not path:
                    raise HTTPException(status_code=400, detail=f"Tool '{t.get('name', '<unknown>')}' missing path")
                if path:
                    base_url = t.get("base_url") or (t.get("metadata") or {}).get("base_url")
                    if not base_url:
                        logger.warning(f"Tool '{t.get('name', '<unknown>')}' missing base_url; HTTP calls may fail.")

        # Build OpenAI client with clearer error handling
        try:
            client = _build_openai_client()
            model_name = _select_model()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client or select model: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Chat service unavailable. Please contact admin.",
            )

        tools = request.tools or []
        tools_index = {t["name"]: t for t in tools if isinstance(t, dict) and "name" in t}
        openai_tools = [tool_to_openai_schema(t) for t in tools if isinstance(t, dict) and "name" in t]
        logger.info(f"Chat tools received: {len(tools_index)} -> {list(tools_index.keys())}")

        if tools and _should_list_all_tools(request.message):
            reply = (
                f"Available tools ({len(tools)}):\n"
                f"{_format_tool_list(tools)}"
            )
            return ChatResponse(reply=reply)

        tool_summaries = [
            f"- {t.get('name')} ({(t.get('method') or '').upper()} {t.get('path') or ''}) params: {[p.get('name') for p in (t.get('parameters') or [])]}"
            for t in tools
        ]

        system_prompt = (
            "You are an API assistant with access to concrete API tools.\n"
            "RULES:\n"
            "- ALWAYS use tools when they match the user request.\n"
            "- If multiple tools match, list them.\n"
            "- When listing all tools/endpoints, include the FULL list with no truncation.\n"
            "- NEVER ask for clarification if tools already match.\n"
            "- Only answer generically if NO tools exist.\n\n"
            "AVAILABLE TOOLS:\n" + "\n".join(tool_summaries) + "\n\n"
            "FULL TOOLS SCHEMA (JSON):\n" + json.dumps(tools, ensure_ascii=False)
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message},
        ]

        try:
            logger.info(f"Calling OpenAI chat.completions (model={model_name}, tools={len(openai_tools)})...")
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=openai_tools if openai_tools else None,
                tool_choice="auto" if openai_tools else None,
            )
        except Exception as e:
            logger.error(f"OpenAI chat.completions call failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Chat service unavailable. Please contact admin.",
            )

        choice = response.choices[0]
        message = choice.message
        response_message_content = message.content or ""
        tool_calls = message.tool_calls or []

        if tool_calls:
            logger.info(f"Tool calls returned: {len(tool_calls)}")
            messages.append(
                {
                    "role": "assistant",
                    "content": response_message_content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for call in tool_calls:
                try:
                    result = run_tool_call(
                        {
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            }
                        },
                        tools_index,
                        None,
                    )
                except Exception as e:
                    logger.error(f"Tool execution failed: {e}", exc_info=True)
                    result = json.dumps({"error": str(e)}, ensure_ascii=False)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "content": result,
                    }
                )
            try:
                logger.info(f"Calling OpenAI follow-up completion (model={model_name}) with tool results...")
                followup = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                )
                final_choice = followup.choices[0]
                content = final_choice.message.content or "No response generated"
                return ChatResponse(reply=content)
            except Exception as e:
                logger.error(f"OpenAI follow-up completion call failed: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail="Chat service unavailable. Please contact admin.",
                )

        if openai_tools:
            logger.info("No tool_call returned; listing available tools instead of clarifying.")
            get_like = []
            for t in tools:
                method = (t.get("method") or "").upper()
                path = t.get("path") or ""
                if method and "GET" in method:
                    get_like.append(f"{method} {path} ({t.get('name')})")
            summary = get_like if get_like else [f"{(t.get('method') or '').upper()} {t.get('path') or ''} ({t.get('name')})" for t in tools]
            content = "Available tools:\n" + "\n".join(summary)
            return ChatResponse(reply=content)

        content = response_message_content or "No response generated"
        return ChatResponse(reply=content)

    except HTTPException as e:
        logger.error(f"Chat endpoint error: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Chat service unavailable. Please contact admin.",
        )


class MCPQueryRequest(BaseModel):
    question: str


@router.post("/mcp-servers/query", response_model=ChatResponse)
async def query_mcp_servers(request: MCPQueryRequest):
    """
    Ask natural language questions about MCP servers stored in MongoDB.
    Example: "List all MCPs", "Which MCP has the most tools?", "Show me the petstore MCP"
    """
    try:
        from ..mongo_store import list_mcp_servers, get_mcp_server
    except ImportError:
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from api_collector_backend.mongo_store import list_mcp_servers, get_mcp_server
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {e}")

    try:
        servers = list_mcp_servers(limit=50)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {e}")

    if not servers:
        return ChatResponse(reply="No MCP servers stored in MongoDB yet. Generate one via /create-mcp-server first.")

    # Build context summary for the LLM
    summary_lines = [f"Total stored MCP servers: {len(servers)}\n"]
    for s in servers:
        summary_lines.append(
            f"- ID: {s['_id']}"
            f" | Source: {s.get('source_name', 'unknown')}"
            f" | Type: {s.get('source_type', '?')}"
            f" | Tools: {s.get('tools_count', 0)}"
            f" | Lines: {s.get('code_lines', '?')}"
            f" | Created: {s.get('created_at', '')[:19]}"
        )
    context = "\n".join(summary_lines)

    # Smart keyword-based fallback (works without LLM) — specific checks first
    q = request.question.lower()
    if "most tool" in q or "largest" in q or "biggest" in q:
        top = max(servers, key=lambda s: s.get("tools_count", 0))
        return ChatResponse(reply=(
            f"The MCP with the most tools is '{top['source_name']}' "
            f"({top['source_type']}) with {top['tools_count']} tools (ID: {top['_id'][:8]}...)."
        ))
    if "latest" in q or "recent" in q or ("last" in q and "tool" not in q) or "newest" in q:
        latest = servers[0]
        return ChatResponse(reply=(
            f"Latest MCP: '{latest['source_name']}' ({latest['source_type']}), "
            f"{latest['tools_count']} tools, created {latest['created_at'][:19]}."
        ))
    if any(w in q for w in ("list", "show", "all", "what", "how many")):
        return ChatResponse(reply=context)

    # Try LLM if available (with short timeout)
    try:
        from openai import OpenAI as _OAI
        import httpx as _httpx
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "")
        model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        _http = _httpx.Client(timeout=10.0)
        _client = _OAI(api_key=api_key, base_url=base_url or None, http_client=_http) if api_key else None
        if _client:
            system_prompt = (
                "Answer questions about stored MCP servers. Data:\n" + context
                + "\nBe concise."
            )
            resp = _client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": request.question},
                ],
                temperature=0.3,
                max_tokens=400,
            )
            reply = (resp.choices[0].message.content or "").strip()
            if reply:
                return ChatResponse(reply=reply)
    except Exception as e:
        logger.debug(f"LLM unavailable for MCP query, using fallback: {e}")

    # Default fallback
    return ChatResponse(reply=f"Here are your stored MCP servers:\n\n{context}")
