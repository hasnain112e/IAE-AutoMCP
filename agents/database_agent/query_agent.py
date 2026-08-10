"""
AI Database Query Agent — two-phase workflow
Phase 1: explore_schema (mandatory first step)
Phase 2: write + execute SELECT/find queries via MCP tool functions
Safety Layer 1: system prompt forbids write operations
Safety Layer 2: QueryValidator blocks destructive queries at execution
"""
import os
import re
import json
import sys
from pathlib import Path
from typing import Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from openai import OpenAI
from agents.database_agent.mock_databases import DatabaseManager
from agents.database_agent.safety_checks import QueryValidator

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Database Query Agent. You have access to a company database with employees, payrolls, and departments data in both PostgreSQL and MongoDB.

## TWO-PHASE WORKFLOW — ALWAYS FOLLOW THIS ORDER:

### PHASE 1 — EXPLORATION (mandatory first step)
- Call explore_schema() IMMEDIATELY as your FIRST action, every session.
- This reveals available tables, columns, and record counts.
- Do not write any queries until you have seen the schema.

### PHASE 2 — QUERYING
- Write precise SQL SELECT queries for PostgreSQL data.
- Write MongoDB find() queries with JSON filters for MongoDB data.
- If the first query returns incomplete results, refine and try again.
- Cross-reference multiple tables when needed (e.g., employees + payrolls).

## ABSOLUTE SAFETY RULES — NEVER VIOLATE:
- SQL: ONLY write SELECT statements. NEVER write DELETE, DROP, UPDATE, INSERT, TRUNCATE, ALTER, CREATE, EXEC.
- MongoDB: ONLY use find(). NEVER use deleteOne, deleteMany, updateOne, updateMany, insertOne, insertMany, drop, replaceOne.
- If a query gets blocked by the safety system, find a different SELECT approach.
- You are READ-ONLY. Any attempt at a write operation will be blocked and logged.

## DATA AVAILABLE:
- employees: id, name, department_id, position, email, salary, hire_date, status
- payrolls: id, emp_id, month, base_salary, bonus, deductions, net_salary, status
- departments: id, name, budget, manager_id

## QUERY STRATEGY:
- For employee + salary: query employees table, then payrolls filtered by emp_id
- For department members: query employees WHERE department_id = <id>
- For payroll details: query payrolls WHERE emp_id = <id>
- After getting data, explain findings clearly with specific numbers

Always end with a clear, formatted answer summarizing what you found."""

# ── Tool definitions for OpenAI function calling ──────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "explore_schema",
            "description": "PHASE 1 — Discover all PostgreSQL tables (with column names) and MongoDB collections. Call this FIRST before writing any queries. Returns schema, record counts, and sample data structure.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql_query",
            "description": "PHASE 2 — Execute a safe SELECT query on PostgreSQL. Only SELECT is allowed; DELETE/DROP/UPDATE/INSERT are blocked by safety layer. Supports WHERE clause filtering.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT statement. Examples: 'SELECT * FROM employees', 'SELECT * FROM employees WHERE department_id = 1', 'SELECT * FROM payrolls WHERE emp_id = 2', 'SELECT * FROM employees WHERE status = active'"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_mongo_find",
            "description": "PHASE 2 — Execute a find() query on MongoDB. Only find() is allowed; destructive operations are blocked. Use JSON filter to narrow results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": "Collection name: 'employees', 'payrolls', or 'departments'"
                    },
                    "filter_json": {
                        "type": "string",
                        "description": "JSON filter string. Use '{}' for all documents. Examples: '{\"status\": \"active\"}', '{\"department_id\": \"dept_001\"}', '{\"emp_id\": \"emp_001\"}'"
                    }
                },
                "required": ["collection", "filter_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_safety_report",
            "description": "Get the complete audit trail of all queries executed in this session, including any blocked attempts.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    }
]


# ── Agent class ───────────────────────────────────────────────────────────────

class DatabaseQueryAgent:
    """
    AI agent that translates natural language → database queries.
    Uses OpenAI function calling to autonomously explore schema and write queries.
    """

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set. Add it to your .env file.")
        _kwargs = dict(api_key=api_key, timeout=30.0, max_retries=1)
        if os.getenv("OPENAI_BASE_URL"):
            _kwargs["base_url"] = os.getenv("OPENAI_BASE_URL")
        self._client = OpenAI(**_kwargs)
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self._db = DatabaseManager()
        self._validator = QueryValidator()
        self._explored = False
        self._queries_run = 0
        self._blocked_attempts = 0

    # ── Tool implementations ─────────────────────────────────────────────────

    def _tool_explore_schema(self) -> dict:
        pg_schema = self._db.postgresql.get_schema()
        mongo_cols = list(self._db.mongodb.collections.keys())
        counts = {t: len(rows) for t, rows in self._db.postgresql.tables.items()}
        self._explored = True
        self._db.log_query("system", "explore_schema", {"phase": "1_exploration"})
        return {
            "success": True,
            "phase": "exploration_complete",
            "postgresql": {
                "tables": pg_schema,
                "record_counts": counts,
            },
            "mongodb": {
                "collections": mongo_cols,
                "record_counts": {c: len(docs) for c, docs in self._db.mongodb.collections.items()}
            },
            "note": "Schema exploration complete. You may now write queries in Phase 2."
        }

    def _tool_execute_sql(self, query: str) -> dict:
        # Safety Layer 2: validate before execution
        is_safe, reason = self._validator.is_safe_sql_query(query)
        if not is_safe:
            self._blocked_attempts += 1
            self._db.log_query("postgresql", "BLOCKED", {"query": query, "reason": reason})
            return {
                "success": False,
                "blocked": True,
                "reason": reason,
                "query": query,
                "safety_message": "Query blocked by safety layer. Only SELECT is allowed."
            }

        # Parse table name
        table_match = re.search(r'\bFROM\s+(\w+)', query, re.IGNORECASE)
        if not table_match:
            return {"success": False, "error": "Cannot parse table name. Use format: SELECT * FROM <table>"}

        table = table_match.group(1).lower()
        if table not in self._db.postgresql.tables:
            available = list(self._db.postgresql.tables.keys())
            return {"success": False, "error": f"Table '{table}' not found. Available: {available}"}

        # Get all rows then apply WHERE filter
        all_rows = list(self._db.postgresql.tables[table])

        # Parse WHERE clause: col = val  or  col = 'val'
        where_match = re.search(
            r'\bWHERE\s+(\w+)\s*=\s*[\'"]?(\w+)[\'"]?',
            query, re.IGNORECASE
        )
        if where_match:
            col, val = where_match.group(1), where_match.group(2)
            # Match both string and numeric
            rows = [r for r in all_rows if str(r.get(col, '')) == val]
        else:
            rows = all_rows

        self._queries_run += 1
        self._db.log_query("postgresql", "SELECT", {"query": query, "rows_returned": len(rows)})
        return {
            "success": True,
            "query": query,
            "table": table,
            "data": rows,
            "count": len(rows),
            "note": f"Returned {len(rows)} rows from {table}"
        }

    def _tool_execute_mongo_find(self, collection: str, filter_json: str) -> dict:
        if collection not in self._db.mongodb.collections:
            available = list(self._db.mongodb.collections.keys())
            return {"success": False, "error": f"Collection '{collection}' not found. Available: {available}"}

        try:
            filter_dict = json.loads(filter_json) if filter_json.strip() else {}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON filter: {e}. Use valid JSON like {{\"key\": \"value\"}}"}

        self._queries_run += 1
        self._db.log_query("mongodb", "find", {"collection": collection, "filter": filter_dict})
        results = self._db.mongodb.find(collection, filter_dict if filter_dict else None)
        return {
            "success": True,
            "collection": collection,
            "filter": filter_dict,
            "data": results,
            "count": len(results),
            "note": f"Returned {len(results)} documents from {collection}"
        }

    def _tool_get_safety_report(self) -> dict:
        trail = self._db.get_audit_trail()
        return {
            "total_operations": len(trail),
            "queries_run": self._queries_run,
            "blocked_attempts": self._blocked_attempts,
            "schema_explored": self._explored,
            "audit_trail": trail
        }

    def _dispatch(self, tool_name: str, args: dict) -> dict:
        if tool_name == "explore_schema":
            return self._tool_explore_schema()
        elif tool_name == "execute_sql_query":
            return self._tool_execute_sql(args.get("query", ""))
        elif tool_name == "execute_mongo_find":
            return self._tool_execute_mongo_find(
                args.get("collection", ""),
                args.get("filter_json", "{}")
            )
        elif tool_name == "get_safety_report":
            return self._tool_get_safety_report()
        return {"error": f"Unknown tool: {tool_name}"}

    # ── Keyword fallback (no LLM needed) ─────────────────────────────────────

    def _run_fallback(self, question: str) -> dict:
        """Keyword-based execution when LLM is unavailable."""
        import re as _re
        q = question.lower()
        steps = []

        # Phase 1: always explore schema first
        schema = self._tool_explore_schema()
        steps.append({"tool": "explore_schema", "args": {}, "result": schema,
                      "blocked": False, "timestamp": datetime.now().isoformat()})

        # Destructive intent check
        for bad in ("delete", "drop", "update", "insert", "truncate", "alter"):
            if bad in q:
                res = {"success": False, "blocked": True,
                       "reason": f"Destructive operation not allowed: {bad.upper()}", "query": bad}
                steps.append({"tool": "execute_sql_query", "args": {"query": bad},
                              "result": res, "blocked": True, "timestamp": datetime.now().isoformat()})
                return {"success": True,
                        "answer": f"BLOCKED: '{bad.upper()}' is a destructive operation. This system is read-only.",
                        "steps": steps,
                        "phase_log": {"explored": True, "queries_run": 0, "blocked_attempts": 1}}

        # Choose query by keyword
        m = _re.search(r'emp[_\s]?id[\s:=]+(\d+)', q) or _re.search(r'\bid\s*[=:]\s*(\d+)', q)
        if ("payroll" in q or "net_salary" in q or "bonus" in q) and m:
            sql = f"SELECT * FROM payrolls WHERE emp_id = {m.group(1)}"
        elif "payroll" in q or "net_salary" in q or "bonus" in q:
            sql = "SELECT * FROM payrolls"
        elif "department" in q or "dept" in q or "budget" in q:
            sql = "SELECT * FROM departments"
        elif "salary" in q and m:
            sql = f"SELECT * FROM employees WHERE id = {m.group(1)}"
        else:
            sql = "SELECT * FROM employees"

        res = self._tool_execute_sql(sql)
        steps.append({"tool": "execute_sql_query", "args": {"query": sql},
                      "result": res, "blocked": False, "timestamp": datetime.now().isoformat()})

        rows = res.get("data", [])
        if rows:
            answer = f"Found {len(rows)} record(s). Query: `{sql}`\n"
            answer += "\n".join(
                "  " + ", ".join(f"{k}: {v}" for k, v in list(r.items())[:6])
                for r in rows[:5]
            )
            if len(rows) > 5:
                answer += f"\n  ... and {len(rows)-5} more rows."
        else:
            answer = f"No records found. Query used: `{sql}`"

        return {"success": True, "answer": answer, "steps": steps,
                "phase_log": {"explored": True, "queries_run": self._queries_run,
                              "blocked_attempts": self._blocked_attempts}}

    # ── Main entry point ─────────────────────────────────────────────────────

    def run(self, question: str) -> dict:
        """
        Run the two-phase agent loop to answer a natural language question.
        Falls back to keyword-based execution if LLM is unavailable.
        Returns: {success, answer, steps, phase_log}
        """
        # Quick LLM availability check — if it fails immediately fall back
        try:
            self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
        except Exception:
            return self._run_fallback(question)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": question}
        ]
        steps = []
        max_iterations = 8

        for _ in range(max_iterations):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.1,
                )
            except Exception:
                return self._run_fallback(question)
            msg = response.choices[0].message

            # Build serialisable assistant message
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_msg)

            # No tool calls → agent finished
            if not msg.tool_calls:
                return {
                    "success": True,
                    "answer": msg.content or "Query complete.",
                    "steps": steps,
                    "phase_log": {
                        "explored": self._explored,
                        "queries_run": self._queries_run,
                        "blocked_attempts": self._blocked_attempts
                    }
                }

            # Execute each tool call
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                result = self._dispatch(tool_name, args)
                steps.append({
                    "tool":      tool_name,
                    "args":      args,
                    "result":    result,
                    "blocked":   result.get("blocked", False),
                    "timestamp": datetime.now().isoformat()
                })
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      json.dumps(result, default=str)
                })

        return {
            "success": False,
            "answer": "Agent reached the iteration limit without completing. Try a simpler question.",
            "steps": steps,
            "phase_log": {
                "explored": self._explored,
                "queries_run": self._queries_run,
                "blocked_attempts": self._blocked_attempts
            }
        }
