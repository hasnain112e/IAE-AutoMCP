"""
AI Database Exploration Agent — Streamlit UI
Connects to the FastAPI agent running on port 8010.
"""
from __future__ import annotations
import json
import requests
import streamlit as st

AGENT_URL = "http://127.0.0.1:8010"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Database Explorer",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.block-safe   { background:#e8f5e9; border-left:4px solid #43a047; padding:8px 12px; border-radius:4px; margin:4px 0; }
.block-danger { background:#ffebee; border-left:4px solid #e53935; padding:8px 12px; border-radius:4px; margin:4px 0; }
.block-info   { background:#e3f2fd; border-left:4px solid #1e88e5; padding:8px 12px; border-radius:4px; margin:4px 0; }
.block-warn   { background:#fff8e1; border-left:4px solid #f9a825; padding:8px 12px; border-radius:4px; margin:4px 0; }
.phase-label  { font-weight:700; font-size:13px; letter-spacing:.5px; text-transform:uppercase; color:#555; }
code { background:#f4f4f4; padding:2px 6px; border-radius:3px; font-size:13px; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def api(method: str, path: str, **kwargs) -> dict | None:
    try:
        resp = requests.request(method, f"{AGENT_URL}{path}", timeout=120, **kwargs)
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the AI Agent service at port 8010. Start it with `_start_ai_agent.bat`.")
        return None
    except Exception as exc:
        st.error(f"Request error: {exc}")
        return None


def badge(text: str, color: str = "#1e88e5") -> str:
    return f'<span style="background:{color};color:#fff;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600">{text}</span>'


# ── Sidebar: Connection panel ─────────────────────────────────────────────────

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=60)
    st.title("AI DB Explorer")

    # Health check
    health = api("GET", "/ai-agent/health")
    if health and health.get("status") == "healthy":
        st.markdown(
            f'🟢 **Agent Online** &nbsp; '
            f'<span style="color:#888;font-size:12px">{health.get("active_sessions",0)} session(s)</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown("🔴 **Agent Offline** — run `_start_ai_agent.bat`")

    st.divider()

    # ── Connect form ──────────────────────────────────────────────────────
    st.subheader("Connect Database")
    db_type = st.selectbox("Database type", ["postgresql", "mongodb"])

    with st.expander("Connection settings", expanded=True):
        uri = st.text_input("URI (optional)", placeholder="postgresql://user:pass@host/db")
        if not uri:
            host     = st.text_input("Host", value="localhost")
            port_def = 5432 if db_type == "postgresql" else 27017
            port     = st.number_input("Port", value=port_def, step=1)
            dbname   = st.text_input("Database name")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
        else:
            host = port = dbname = username = password = ""

    if st.button("🔌 Connect", use_container_width=True, type="primary"):
        payload = {"db_type": db_type}
        if uri:
            payload["uri"] = uri
        else:
            payload.update({
                "host": host, "port": int(port),
                "dbname": dbname, "username": username, "password": password,
            })
        with st.spinner("Connecting and loading schema…"):
            result = api("POST", "/ai-agent/connect", json=payload)
        if result and result.get("success"):
            st.session_state["session_id"] = result["session_id"]
            st.session_state["db_type"]    = result["db_type"]
            st.session_state["tables"]     = result.get("tables", [])
            st.session_state["messages"]   = []
            st.success(f"Connected! {result.get('table_count', 0)} table(s)/collection(s) found.")
            st.rerun()
        elif result:
            st.error(result.get("error", "Connection failed"))

    # ── Session info ──────────────────────────────────────────────────────
    if "session_id" in st.session_state:
        sid = st.session_state["session_id"]
        st.divider()
        st.markdown(f"**Session:** `{sid[:16]}…`")
        st.markdown(f"**DB type:** `{st.session_state.get('db_type','')}`")

        tables = st.session_state.get("tables", [])
        if tables:
            with st.expander(f"📋 Tables / Collections ({len(tables)})", expanded=False):
                for t in tables:
                    st.markdown(f"- `{t}`")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📊 Schema", use_container_width=True):
                st.session_state["show_schema"] = True
        with col2:
            if st.button("🔒 Audit", use_container_width=True):
                st.session_state["show_audit"] = True

        if st.button("❌ Disconnect", use_container_width=True):
            api("DELETE", f"/ai-agent/session/{sid}")
            for k in ["session_id", "db_type", "tables", "messages", "show_schema", "show_audit"]:
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()
    st.caption("Powered by vLLM · FastMCP · FastAPI")


# ── Main content ──────────────────────────────────────────────────────────────

st.title("🤖 AI Database Exploration Agent")

if "session_id" not in st.session_state:
    # Landing page
    st.markdown("""
    **Connect a database in the sidebar to get started.**

    This agent lets you explore any PostgreSQL or MongoDB database using plain English:

    | Ask | Agent does |
    |-----|-----------|
    | "Show me the top 10 customers by revenue" | Generates optimized SQL, executes safely, summarizes results |
    | "Find all active orders placed this month" | Builds MongoDB filter, queries, explains findings |
    | "How many products are in each category?" | Writes GROUP BY query, presents counts |
    | "Get employee details for the sales team" | Identifies tables, JOINs as needed, returns data |

    ### How it works
    1. **Phase 1 — Planner** · Understands your intent · Picks relevant tables · Generates a safe query
    2. **Phase 2 — Executor** · Validates security (read-only enforced) · Optimizes · Runs via MCP · Summarizes

    > **Security** · Only `SELECT` / `find` operations are allowed. `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE` are blocked at multiple layers.
    """)
    st.stop()


sid = st.session_state["session_id"]

# ── Schema panel ──────────────────────────────────────────────────────────────
if st.session_state.get("show_schema"):
    with st.expander("📊 Live Database Schema", expanded=True):
        data = api("GET", f"/ai-agent/schema/{sid}")
        if data and data.get("success"):
            st.markdown(f"**Summary:** {data.get('summary','')}")
            for table, cols in (data.get("db_schema") or {}).items():
                st.markdown(f"**`{table}`**")
                if isinstance(cols, list):
                    col_text = " · ".join(f"`{c.get('name','?')}` ({c.get('type','?')})" for c in cols)
                    st.markdown(col_text)
        st.button("Close schema", on_click=lambda: st.session_state.pop("show_schema", None))

# ── Audit panel ───────────────────────────────────────────────────────────────
if st.session_state.get("show_audit"):
    with st.expander("🔒 Security Audit Log", expanded=True):
        data = api("GET", f"/ai-agent/audit/{sid}")
        if data and data.get("success"):
            entries = data.get("audit", [])
            if not entries:
                st.info("No queries logged yet.")
            for e in entries:
                icon = "✅" if e.get("safe") else "🚫"
                color = "block-safe" if e.get("safe") else "block-danger"
                st.markdown(
                    f'<div class="{color}">{icon} <code>{e.get("query","")[:120]}</code>'
                    f'<br><small>{e.get("reason","")} · {e.get("timestamp","")}</small></div>',
                    unsafe_allow_html=True,
                )
        st.button("Close audit", on_click=lambda: st.session_state.pop("show_audit", None))

# ── Chat history ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = []

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"], avatar=("🧑" if msg["role"] == "user" else "🤖")):
        st.markdown(msg["content"], unsafe_allow_html=True)
        if msg.get("data"):
            with st.expander(f"📄 {msg.get('row_count', len(msg['data']))} row(s) returned"):
                st.dataframe(msg["data"], use_container_width=True)
        if msg.get("plan"):
            with st.expander("🔍 Phase 1 — Plan details"):
                plan = msg["plan"]
                intent = plan.get("intent", {})
                st.markdown(
                    f'<div class="block-info">'
                    f'<span class="phase-label">Intent</span><br>'
                    f'Operation: <code>{intent.get("operation_type","")}</code> · '
                    f'Entities: <code>{intent.get("entities","")}</code> · '
                    f'Confidence: <code>{intent.get("confidence", 0):.0%}</code>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Relevant tables:** {', '.join(f'`{t}`' for t in plan.get('relevant_tables', []))}")
                st.markdown(f"**Plan:** {plan.get('plan_explanation','')}")
                st.code(plan.get("generated_query", ""), language="sql")
        if msg.get("execution"):
            ex = msg["execution"]
            if ex.get("blocked"):
                st.markdown(
                    f'<div class="block-danger">🚫 <b>Blocked by security guard</b><br>'
                    f'{ex.get("block_reason","")}</div>',
                    unsafe_allow_html=True,
                )
            elif ex.get("retried"):
                st.markdown('<div class="block-warn">⚠️ Query failed on first attempt — auto-retried with fix.</div>', unsafe_allow_html=True)


# ── Chat input ────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask anything about your database…"):
    # Show user message immediately
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    # Call AI agent
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking… (Phase 1: Planning → Phase 2: Executing)"):
            result = api("POST", f"/ai-agent/query/{sid}", json={"question": prompt})

        if not result:
            st.error("No response from agent.")
            st.stop()

        plan = result.get("plan")
        execution = result.get("execution")
        success = result.get("success", False)

        if not success and result.get("error"):
            st.error(result["error"])
            st.session_state["messages"].append({
                "role": "assistant",
                "content": f"❌ {result['error']}",
            })
            st.stop()

        # Summary
        summary = (execution or {}).get("summary", "")
        blocked = (execution or {}).get("blocked", False)
        row_count = (execution or {}).get("row_count", 0)
        data_rows = (execution or {}).get("data", [])

        if blocked:
            answer = f'🚫 **Blocked:** {(execution or {}).get("block_reason", "")}'
            st.markdown(f'<div class="block-danger">{answer}</div>', unsafe_allow_html=True)
        elif not success:
            error_msg = (execution or {}).get("error", result.get("error", "Unknown error"))
            answer = f"❌ **Error:** {error_msg}"
            st.warning(answer)
        else:
            answer = summary or f"Query returned {row_count} row(s)."
            st.markdown(answer)

        # Results table
        if data_rows and not blocked:
            with st.expander(f"📄 {row_count} row(s) returned"):
                st.dataframe(data_rows, use_container_width=True)

        # Plan details
        if plan:
            with st.expander("🔍 Phase 1 — Plan details"):
                intent = plan.get("intent", {})
                st.markdown(
                    f'<div class="block-info">'
                    f'<span class="phase-label">Intent analysis</span><br>'
                    f'Operation: <code>{intent.get("operation_type","")}</code> · '
                    f'Entities: <code>{intent.get("entities","")}</code> · '
                    f'Confidence: <code>{intent.get("confidence", 0):.0%}</code>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Relevant tables:** {', '.join(f'`{t}`' for t in plan.get('relevant_tables', []))}")
                st.markdown(f"**Plan:** {plan.get('plan_explanation','')}")
                final_q = (execution or {}).get("query") or plan.get("generated_query", "")
                lang = "json" if result.get("db_type") == "mongodb" else "sql"
                st.code(final_q, language=lang)

        if (execution or {}).get("retried"):
            st.markdown('<div class="block-warn">⚠️ First attempt failed — auto-retried with corrected query.</div>', unsafe_allow_html=True)

    st.session_state["messages"].append({
        "role": "assistant",
        "content": answer,
        "plan": plan,
        "execution": execution,
        "data": data_rows,
        "row_count": row_count,
    })
