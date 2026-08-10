"""
LangGraph-based two-phase database exploration agent.
Fully synchronous — designed to run inside asyncio.to_thread() from the API layer.

Phase 1  explore_schema(): extract → summarize → cache
Phase 2  query(): select_tables → generate_query → validate_safety
                 → optimize_query → execute_query → explain_result
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict
from openai import OpenAI

from .schema_manager import SchemaManager
from .safety import ProductionQueryValidator
from .query_optimizer import QueryOptimizer

if TYPE_CHECKING:
    from .connectors import BaseConnector


# ── State ─────────────────────────────────────────────────────────────────────

class ExplorerState(TypedDict):
    question: str
    db_type: str
    schema_data: dict
    schema_summary: str
    relevant_tables: list
    schema_context: str
    generated_query: str
    query_explanation: str
    safety_ok: bool
    safety_reason: str
    execution_result: list
    optimization_notes: str
    retry_count: int
    error_msg: str
    final_answer: str
    steps: list


# ── Prompts ───────────────────────────────────────────────────────────────────

_SQL_PROMPT = """\
You are an expert SQL analyst. Write a precise SQL SELECT query to answer the question.

RULES:
- ONLY SELECT statements. NEVER DELETE, DROP, UPDATE, INSERT, ALTER, TRUNCATE, CREATE.
- Use exact table and column names from the schema.
- Add LIMIT 100 if no specific limit is asked.
- Output ONLY the raw SQL query — no markdown, no explanation, no code fences.

Schema (relevant tables):
{schema}

Question: {question}
"""

_MONGO_PROMPT = """\
You are a MongoDB expert. Write a JSON filter for db.{collection}.find(<filter>).

RULES:
- Output ONLY valid JSON object. Example: {{"status": "active"}}
- Use exact field names from the schema.
- For "all documents" output: {{}}
- Output ONLY the JSON filter — no explanation.

Schema:
{schema}

Question: {question}
"""

_EXPLAIN_PROMPT = """\
Summarize these database results in clear natural language. Be specific with numbers.
Use bullet points if listing multiple items.

Question: {question}
Query: {query}
Results (first 10 rows): {results}
Total rows: {count}

Answer:"""


# ── Agent ─────────────────────────────────────────────────────────────────────

class ExplorerAgent:

    def __init__(self, connector: "BaseConnector", session_id: str):
        self._conn = connector
        self._sid = session_id
        self._db_type = connector.db_type
        _kwargs = dict(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=30.0,
            max_retries=1,
        )
        if os.getenv("OPENAI_BASE_URL"):
            _kwargs["base_url"] = os.getenv("OPENAI_BASE_URL")
        self._openai = OpenAI(**_kwargs)
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._optimizer = QueryOptimizer()
        self._schema_data: dict = {}
        self._graph = self._build_graph()

    # ── LLM helper ────────────────────────────────────────────────────────

    def _llm(self, prompt: str, max_tokens: int = 500) -> str:
        try:
            resp = self._openai.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            return f"[LLM error: {e}]"

    # ── Phase 1: schema exploration (sync) ────────────────────────────────

    def explore_schema(self) -> dict:
        """Sync — extract schema from connector, cache, return summary dict."""
        data = SchemaManager.extract_sync(self._conn)
        self._schema_data = data
        SchemaManager.cache_set(self._sid, data)
        schema = data.get("schema", {})
        counts = data.get("counts", {})
        return {
            "success": True,
            "db_type": self._db_type,
            "table_count": len(schema),
            "tables": list(schema.keys()),
            "column_count": sum(len(cols) for cols in schema.values()),
            "row_counts": counts,
            "summary": SchemaManager.summarize(data),
            "schema": schema,
        }

    # ── LangGraph nodes ────────────────────────────────────────────────────

    def _select_tables(self, state: ExplorerState) -> ExplorerState:
        cached = SchemaManager.cache_get(self._sid) or self._schema_data
        relevant = SchemaManager.select_relevant_tables(cached, state["question"])
        context = SchemaManager.build_context(cached, relevant)
        return {**state,
                "schema_data": cached,
                "relevant_tables": relevant,
                "schema_context": context,
                "steps": state.get("steps", []) + [{"node": "select_tables", "tables": relevant}]}

    def _generate_query(self, state: ExplorerState) -> ExplorerState:
        db = self._db_type
        schema_ctx = state["schema_context"]
        question = state["question"]

        if db == "mongodb":
            collection = state["relevant_tables"][0] if state["relevant_tables"] else "data"
            raw = self._llm(_MONGO_PROMPT.format(
                schema=schema_ctx, question=question, collection=collection))
        else:
            raw = self._llm(_SQL_PROMPT.format(schema=schema_ctx, question=question))

        # Strip markdown fences
        query = raw.replace("```sql", "").replace("```json", "").replace("```", "").strip()

        return {**state,
                "generated_query": query,
                "error_msg": "",
                "steps": state.get("steps", []) + [{"node": "generate_query", "query": query,
                                                     "retry": state.get("retry_count", 0)}]}

    def _validate_safety(self, state: ExplorerState) -> ExplorerState:
        query = state["generated_query"]
        if self._db_type == "mongodb":
            safe, reason = ProductionQueryValidator.validate_mongo(self._sid, "find", {})
        else:
            safe, reason = ProductionQueryValidator.validate_sql(self._sid, query)
        return {**state,
                "safety_ok": safe,
                "safety_reason": reason,
                "steps": state.get("steps", []) + [{"node": "validate_safety",
                                                     "safe": safe, "reason": reason}]}

    def _optimize_query(self, state: ExplorerState) -> ExplorerState:
        res = self._optimizer.optimize(
            state["generated_query"], state["schema_context"], state["question"])
        return {**state,
                "generated_query": res["optimized"],
                "optimization_notes": res["notes"],
                "steps": state.get("steps", []) + [{"node": "optimize_query",
                                                     "notes": res["notes"],
                                                     "changed": res["changed"]}]}

    def _execute_query(self, state: ExplorerState) -> ExplorerState:
        query = state["generated_query"]
        results: list = []
        error_msg = ""
        try:
            if self._db_type == "mongodb":
                try:
                    filt = json.loads(query) if query.strip().startswith("{") else {}
                except json.JSONDecodeError:
                    filt = {}
                col = state["relevant_tables"][0] if state["relevant_tables"] else "data"
                results = self._conn.execute_find(col, filt)
            else:
                results = self._conn.execute_sql(query)
        except Exception as e:
            error_msg = str(e)

        return {**state,
                "execution_result": results,
                "error_msg": error_msg,
                "retry_count": state.get("retry_count", 0) + (1 if error_msg else 0),
                "steps": state.get("steps", []) + [{"node": "execute_query",
                                                     "count": len(results),
                                                     "error": error_msg}]}

    def _retry(self, state: ExplorerState) -> ExplorerState:
        fixed = self._optimizer.fix_on_error(
            state["generated_query"],
            state.get("error_msg") or state.get("safety_reason", "unknown error"),
            state["schema_context"],
            state["question"])
        return {**state,
                "generated_query": fixed,
                "retry_count": state.get("retry_count", 0) + 1,
                "steps": state.get("steps", []) + [{"node": "retry", "fixed_query": fixed}]}

    def _explain_result(self, state: ExplorerState) -> ExplorerState:
        results = state["execution_result"]
        if not results and state.get("error_msg"):
            answer = f"Could not retrieve results: {state['error_msg']}"
        elif not results:
            answer = "The query returned no matching records."
        else:
            prompt = _EXPLAIN_PROMPT.format(
                question=state["question"],
                query=state["generated_query"],
                results=json.dumps(results[:10], default=str)[:2000],
                count=len(results)
            )
            answer = self._llm(prompt, max_tokens=400)

        return {**state,
                "final_answer": answer,
                "query_explanation": answer,
                "steps": state.get("steps", []) + [{"node": "explain_result"}]}

    # ── Graph assembly ────────────────────────────────────────────────────

    def _build_graph(self):
        g = StateGraph(ExplorerState)
        g.add_node("select_tables",   self._select_tables)
        g.add_node("generate_query",  self._generate_query)
        g.add_node("validate_safety", self._validate_safety)
        g.add_node("optimize_query",  self._optimize_query)
        g.add_node("execute_query",   self._execute_query)
        g.add_node("explain_result",  self._explain_result)
        g.add_node("retry",           self._retry)

        g.set_entry_point("select_tables")
        g.add_edge("select_tables", "generate_query")
        g.add_edge("generate_query", "validate_safety")

        g.add_conditional_edges("validate_safety", lambda s: (
            "optimize_query" if s["safety_ok"]
            else ("retry" if s.get("retry_count", 0) < 2 else "explain_result")
        ))

        g.add_edge("optimize_query", "execute_query")

        g.add_conditional_edges("execute_query", lambda s: (
            "explain_result" if not s["error_msg"]
            else ("retry" if s.get("retry_count", 0) < 3 else "explain_result")
        ))

        g.add_edge("retry", "generate_query")
        g.add_edge("explain_result", END)
        return g.compile()

    # ── Phase 2 entry (sync) ──────────────────────────────────────────────

    def query(self, question: str) -> dict:
        """Fully synchronous — call from asyncio.to_thread()."""
        safe_q = ProductionQueryValidator.strip_prompt_injection(question)
        initial: ExplorerState = {
            "question": safe_q,
            "db_type": self._db_type,
            "schema_data": self._schema_data,
            "schema_summary": SchemaManager.summarize(self._schema_data),
            "relevant_tables": [],
            "schema_context": "",
            "generated_query": "",
            "query_explanation": "",
            "safety_ok": True,
            "safety_reason": "",
            "execution_result": [],
            "optimization_notes": "",
            "retry_count": 0,
            "error_msg": "",
            "final_answer": "",
            "steps": [],
        }
        final: ExplorerState = self._graph.invoke(initial)
        return {
            "success": not (final.get("error_msg") and not final.get("execution_result")),
            "question": question,
            "generated_query": final["generated_query"],
            "query_explanation": final["final_answer"],
            "optimization_notes": final.get("optimization_notes", ""),
            "safety_ok": final["safety_ok"],
            "safety_reason": final.get("safety_reason", ""),
            "results": final["execution_result"],
            "row_count": len(final["execution_result"]),
            "relevant_tables": final["relevant_tables"],
            "steps": final["steps"],
            "timestamp": datetime.now().isoformat(),
        }
