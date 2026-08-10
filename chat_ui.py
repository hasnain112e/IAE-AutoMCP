# // Edited by Dr. Wasim
#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import csv
import io
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
import streamlit as st
from dotenv import load_dotenv

try:
    from openai import OpenAI
except Exception as e:
    raise SystemExit(
        "Missing openai SDK. Install with: pip install openai\n"
        f"Import error: {e}"
    )

# ------------------------ Helpers: config + tools ------------------------ #

def load_config_from_json_bytes(b: bytes) -> Dict[str, Any]:
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:
        return {}


def load_tools_from_json_bytes(b: bytes) -> List[Dict[str, Any]]:
    data = json.loads(b.decode("utf-8"))

    # Could be CollectToolsResponse or just a list
    if isinstance(data, dict) and "tools" in data:
        tools = data["tools"]
    else:
        tools = data

    if not isinstance(tools, list):
        raise ValueError("JSON does not contain a tools list")

    return tools


def load_tools_from_csv_bytes(b: bytes) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    text = b.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        params_raw = row.get("parameters_json") or "[]"
        try:
            params = json.loads(params_raw)
        except Exception:
            params = []
        tool = {
            "name": row.get("name") or "",
            "description": row.get("description") or "",
            "method": row.get("method") or None,
            "path": row.get("path") or None,
            "tags": (row.get("tags") or "").split("|") if row.get("tags") else [],
            "parameters": params,
            "metadata": {},  # CSV didn't preserve metadata here
        }
        out.append(tool)
    return out


def load_tools_from_uploaded(file) -> List[Dict[str, Any]]:
    name = (file.name or "").lower()
    data = file.read()
    if name.endswith(".json"):
        return load_tools_from_json_bytes(data)
    if name.endswith(".csv"):
        return load_tools_from_csv_bytes(data)
    raise ValueError("Unsupported tools file type. Use .json or .csv")


# ------------------------ OpenAI tools schema ------------------------ #

def tool_to_openai_schema(t: Dict[str, Any]) -> Dict[str, Any]:
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


# ------------------------ Tool executors ------------------------ #

def _http_call(
    tool: Dict[str, Any],
    args: Dict[str, Any],
    global_config: Dict[str, Any] | None = None,
) -> Any:
    """
    Very simple HTTP executor for tools coming from Postman/OpenAPI.
    Uses:
      - tool.metadata.base_url or metadata.url
      - or global_config["default_base_url"]
      - and global_config["http_headers"] for auth, etc.
    """
    if global_config is None:
        global_config = {}

    method = (tool.get("method") or "GET").upper()
    path = tool.get("path") or "/"
    meta = tool.get("metadata") or {}

    base_url = (
        meta.get("base_url")
        or meta.get("url")
        or global_config.get("default_base_url")
        or ""
    )

    if base_url:
        url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    else:
        # Fallback: maybe path is full URL
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            return {
                "error": "No base_url in metadata or config; cannot perform HTTP call.",
                "method": method,
                "path": path,
                "args": args,
            }

    headers = global_config.get("http_headers") or {}

    if method == "GET":
        resp = requests.get(url, params=args, headers=headers, timeout=30)
    else:
        resp = requests.request(method, url, json=args, headers=headers, timeout=30)

    try:
        return resp.json()
    except Exception:
        return resp.text


def _sdk_call(tool: Dict[str, Any], args: Dict[str, Any]) -> Any:
    """
    For tools generated from Python SDKs (metadata.source == 'python_sdk').
    Expects metadata.sdk_module and metadata.sdk_function.
    """
    meta = tool.get("metadata") or {}
    sdk_module = meta.get("sdk_module")
    sdk_func = meta.get("sdk_function")
    if not sdk_module or not sdk_func:
        raise ValueError("SDK metadata missing (sdk_module / sdk_function)")

    import importlib

    mod = importlib.import_module(sdk_module)
    fn = getattr(mod, sdk_func)
    return fn(**args)


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

    meta = t.get("metadata") or {}
    source = meta.get("source")  # e.g. 'postman_collection', 'openapi', 'python_sdk'

    try:
        if source in {"postman_collection", "openapi", "url"}:
            result = _http_call(t, args, global_config)
        elif source == "python_sdk":
            result = _sdk_call(t, args)
        else:
            # Generic fallback: just echo args
            result = {
                "tool": name,
                "args": args,
                "info": "No executor configured for this source; returning args only.",
            }
    except Exception as e:
        result = {"error": str(e), "tool": name, "args": args}

    return json.dumps(result, ensure_ascii=False)[:4000]


# ------------------------ Streamlit UI helpers ------------------------ #

def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages: List[Dict[str, Any]] = []
    if "tools" not in st.session_state:
        st.session_state.tools: List[Dict[str, Any]] = []
    if "openai_tools" not in st.session_state:
        st.session_state.openai_tools: List[Dict[str, Any]] = []
    if "tools_index" not in st.session_state:
        st.session_state.tools_index: Dict[str, Dict[str, Any]] = {}
    if "global_config" not in st.session_state:
        st.session_state.global_config: Dict[str, Any] = {}
    if "client" not in st.session_state:
        st.session_state.client = None
    if "model_name" not in st.session_state:
        st.session_state.model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def build_client(api_key: str | None) -> OpenAI | None:
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    kwargs = {"api_key": key}
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


# ------------------------ Main Streamlit app ------------------------ #

def main():
    load_dotenv()
    init_session_state()

    st.set_page_config(
        page_title="AutoMCP Tool Chat",
        page_icon="🧰",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # -------- Sidebar: config & tools -------- #
    with st.sidebar:
        st.markdown(
            "<h2 style='margin-bottom: 0.3rem;'>🧰 AutoMCP Tool Chat</h2>"
            "<p style='font-size: 0.8rem; color: #9ca3af;'>"
            "Chat with APIs/SDKs via your collected tools."
            "</p>",
            unsafe_allow_html=True,
        )

        st.markdown("### 1. Tools file")
        tools_file = st.file_uploader(
            "Upload tools.json or tools.csv from the collector",
            type=["json", "csv"],
        )

        if tools_file is not None:
            try:
                tools = load_tools_from_uploaded(tools_file)
                st.session_state.tools = tools
                st.session_state.openai_tools = [
                    tool_to_openai_schema(t) for t in tools
                ]
                st.session_state.tools_index = {t["name"]: t for t in tools}
                st.success(f"Loaded {len(tools)} tools.")
            except Exception as e:
                st.error(f"Failed to load tools file: {e}")

        with st.expander("Preview loaded tools", expanded=False):
            if st.session_state.tools:
                st.caption(f"{len(st.session_state.tools)} tools loaded.")
                for t in st.session_state.tools[:20]:
                    st.markdown(
                        f"- **{t['name']}**  "
                        f"<span style='font-size: 0.75rem; color:#9ca3af;'>{t.get('description','')}</span>",
                        unsafe_allow_html=True,
                    )
                if len(st.session_state.tools) > 20:
                    st.caption(f"... and {len(st.session_state.tools) - 20} more")
            else:
                st.caption("No tools loaded yet.")

        st.markdown("---")
        st.markdown("### 2. Config (optional)")

        config_file = st.file_uploader(
            "Config JSON (API key, model, base URLs, headers...)",
            type=["json"],
            key="config_uploader",
        )

        if config_file is not None:
            try:
                cfg = load_config_from_json_bytes(config_file.read())
                st.session_state.global_config = cfg
                st.success("Config loaded.")
                with st.expander("Config preview", expanded=False):
                    st.json(cfg)
            except Exception as e:
                st.error(f"Failed to parse config: {e}")

        st.markdown("### 3. OpenAI settings")

        # API key override
        api_key_input = st.text_input(
            "OpenAI API key (optional override)",
            type="password",
            value="",
            help="If empty, the app will use OPENAI_API_KEY from your .env / environment.",
        )

        # Model override
        model_input = st.text_input(
            "Model name",
            value=st.session_state.model_name,
            help="Example: gpt-4o-mini.",
        )
        st.session_state.model_name = model_input.strip() or "gpt-4o-mini"

        # Build client
        if st.button("Initialize chat session", use_container_width=True):
            client = build_client(api_key_input)
            if client is None:
                st.error(
                    "No API key found. Set it in .env as OPENAI_API_KEY "
                    "or enter it above."
                )
            else:
                st.session_state.client = client
                st.session_state.messages = []
                st.success("Chat session initialized.")

        st.markdown("---")
        st.caption(
            "Tip: use the collector frontend to generate tools.json/csv, "
            "then upload it here."
        )

    # -------- Main chat area -------- #
    st.markdown(
        """
        <style>
        .chat-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.5rem;
        }
        .chat-header-title {
            font-size: 1.1rem;
            font-weight: 600;
        }
        .chat-header-sub {
            font-size: 0.8rem;
            color: #9ca3af;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='chat-header'>"
        "<div>"
        "<div class='chat-header-title'>Real-time chat with your tools</div>"
        "<div class='chat-header-sub'>Ask questions that require calling APIs or SDKs.</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Show current status
    cols = st.columns(3)
    with cols[0]:
        st.metric("Tools loaded", len(st.session_state.tools))
    with cols[1]:
        st.metric(
            "OpenAI client",
            "Ready" if st.session_state.client else "Not initialized",
        )
    with cols[2]:
        st.metric("Model", st.session_state.model_name)

    # Render chat history
    for msg in st.session_state.messages:
        role = msg["role"]
        if role == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        elif role == "assistant":
            with st.chat_message("assistant"):
                st.markdown(msg["content"])
        elif role == "tool":
            # Optional: show tool outputs in a lighter style
            with st.chat_message("assistant"):
                st.markdown(
                    f"**[Tool `{msg.get('name','')}` result]**\n\n"
                    f"```json\n{msg.get('content','')}\n```"
                )

    # Chat input
    user_input = st.chat_input("Ask something about your APIs / SDKs...")

    if user_input:
        if not st.session_state.client:
            st.error("Initialize chat session and API key in the sidebar first.")
        elif not st.session_state.tools:
            st.error("Upload a tools file in the sidebar first.")
        else:
            # Append user message
            st.session_state.messages.append(
                {"role": "user", "content": user_input}
            )

            # First call: let the model decide whether to call tools
            try:
                resp = st.session_state.client.chat.completions.create(
                    model=st.session_state.model_name,
                    messages=[
                        {"role": "system",
                         "content": (
                             "You are an API assistant. You have tools representing HTTP endpoints "
                             "and SDK functions. Use the tool-calling interface when you need live "
                             "data. Pick the most relevant tool, call it with sensible parameters, "
                             "and then summarize the result for the user."
                         )},
                        *[
                            m
                            for m in st.session_state.messages
                            if m["role"] in {"user", "assistant"}
                        ],
                    ],
                    tools=st.session_state.openai_tools,
                    tool_choice="auto",
                )
            except Exception as e:
                st.error(f"OpenAI error: {e}")
                return

            msg = resp.choices[0].message
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                # Just a normal answer
                assistant_text = msg.content or ""
                st.session_state.messages.append(
                    {"role": "assistant", "content": assistant_text}
                )
                with st.chat_message("assistant"):
                    st.markdown(assistant_text)
                return

            # Add assistant's tool_calls stub to messages (for context)
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
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

            # Execute tools
            tool_messages: List[Dict[str, Any]] = []
            for tc in tool_calls:
                result_text = run_tool_call(
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    },
                    st.session_state.tools_index,
                    st.session_state.global_config,
                )
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": result_text,
                }
                st.session_state.messages.append(tool_msg)
                tool_messages.append(tool_msg)

            # Show tool outputs in UI (optional but nice)
            for tm in tool_messages:
                with st.chat_message("assistant"):
                    st.markdown(
                        f"**[Tool `{tm['name']}` result]**\n\n"
                        f"```json\n{tm['content']}\n```"
                    )

            # Second call: give model the tool responses to produce final answer
            try:
                resp2 = st.session_state.client.chat.completions.create(
                    model=st.session_state.model_name,
                    messages=[
                        {"role": "system",
                         "content": (
                             "You are an API assistant. You have tools representing HTTP endpoints "
                             "and SDK functions. Use previous tool results to answer clearly."
                         )},
                        *[
                            m
                            for m in st.session_state.messages
                            if m["role"] in {"user", "assistant", "tool"}
                        ],
                    ],
                )
            except Exception as e:
                st.error(f"OpenAI error (second phase): {e}")
                return

            final_msg = resp2.choices[0].message
            final_text = final_msg.content or ""
            st.session_state.messages.append(
                {"role": "assistant", "content": final_text}
            )
            with st.chat_message("assistant"):
                st.markdown(final_text)


if __name__ == "__main__":
    main()
