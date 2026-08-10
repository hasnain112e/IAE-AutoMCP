"""
Reasoner — all LLM calls for the AI agent, backed by the vLLM API.

Uses the synchronous openai.OpenAI client (matching the existing codebase pattern)
wrapped in asyncio.to_thread() by callers to avoid blocking the event loop.

Every method is a plain synchronous function — callers are responsible for
running them via asyncio.to_thread().
"""
from __future__ import annotations
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ai_agent.models.responses import IntentResult

logger = logging.getLogger(__name__)


# ── Prompt templates ──────────────────────────────────────────────────────────

_INTENT_SYSTEM = """\
You are a database analyst. Analyze the user's question and output a JSON object with these exact keys:
- "operation_type": one of "aggregate", "filter", "lookup", "count", "sample"
- "entities": JSON array of table/collection names or domain concepts mentioned
- "filters": JSON object of filter conditions (empty object if none)
- "output_format": one of "table", "count", "list"
- "confidence": float 0.0-1.0

Output ONLY valid JSON. No markdown, no explanation."""

_INTENT_USER = """\
Question: {question}

Available schema summary:
{schema_summary}"""

_TABLES_SYSTEM = """\
You are a database expert. Given a question and list of available tables/collections,
identify which are needed to answer the question.
Output ONLY a JSON array of table names from the provided list.
Example: ["users", "orders"]
Output ONLY the JSON array. No markdown, no explanation."""

_TABLES_USER = """\
Question: {question}

Available tables/collections:
{table_list}

Schema summary:
{schema_summary}"""

_SQL_SYSTEM = """\
You are an expert SQL analyst. Write a precise SQL SELECT query to answer the question.

RULES — STRICTLY ENFORCED:
1. ONLY SELECT statements. NEVER use DELETE, DROP, UPDATE, INSERT, ALTER, TRUNCATE, CREATE, EXEC.
2. Use exact table and column names from the schema provided.
3. Add LIMIT 100 if no specific limit is requested.
4. Output ONLY the raw SQL query — no markdown fences, no explanation."""

_SQL_USER = """\
Question: {question}

Relevant schema:
{schema}

User intent: {intent_summary}"""

_MONGO_SYSTEM = """\
You are a MongoDB expert. Write a filter document for db.{collection}.find(<filter>).

RULES — STRICTLY ENFORCED:
1. Output ONLY a valid JSON object (the filter argument to find()).
2. Use exact field names from the schema.
3. For all documents, output: {{}}
4. Never use $where, $function, or $accumulator.
5. Output ONLY the JSON filter. No explanation, no markdown."""

_MONGO_USER = """\
Question: {question}

Collection: {collection}
Schema:
{schema}

User intent: {intent_summary}"""

_PLAN_EXPLAIN_SYSTEM = """\
You are a helpful assistant. Explain in 2-3 clear sentences what the following database query
will do to answer the user's question. Write for a non-technical audience."""

_PLAN_EXPLAIN_USER = """\
Question: {question}
Query: {query}"""

_SUMMARIZE_SYSTEM = """\
You are a data analyst. Summarize the database query results clearly and concisely.
Be specific with numbers. Use bullet points when listing multiple items.
Do not repeat the raw data — interpret it."""

_SUMMARIZE_USER = """\
Question: {question}
Query executed: {query}
Total rows returned: {count}
Sample results (first 10 rows):
{results}"""

_FIX_SYSTEM = """\
You are a SQL/MongoDB expert debugging a failed query. Given the original query, the error,
the schema, and the original question — output a corrected query.

For SQL: output ONLY the corrected SQL SELECT statement, no explanation.
For MongoDB filters: output ONLY the corrected JSON filter object, no explanation."""

_FIX_USER = """\
Original query: {query}
Error: {error}
Schema: {schema}
Original question: {question}"""


# ── Reasoner class ────────────────────────────────────────────────────────────

class Reasoner:
    """
    Synchronous LLM interface. All methods are blocking — callers must use
    asyncio.to_thread() to avoid stalling the FastAPI event loop.
    """

    def __init__(self, config) -> None:
        kwargs: dict[str, Any] = {
            "api_key": config.OPENAI_API_KEY,
            "timeout": config.LLM_TIMEOUT,
            "max_retries": 1,
        }
        if config.OPENAI_BASE_URL:
            kwargs["base_url"] = config.OPENAI_BASE_URL
        self._client = OpenAI(**kwargs)
        self._model = config.OPENAI_MODEL
        self._temperature = config.LLM_TEMPERATURE
        self._max_tokens = config.LLM_MAX_TOKENS

    def _call(
        self,
        user: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens or self._max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.error("Reasoner._call failed | model=%s | error=%s", self._model, exc)
            return ""

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove markdown code fences (```json ... ```, ```sql ... ```, etc.)."""
        text = re.sub(r"^```\w*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text.strip())
        return text.strip()

    @staticmethod
    def _parse_json(text: str, default: Any) -> Any:
        """Parse JSON from LLM output with fence stripping and graceful fallback."""
        cleaned = Reasoner._strip_fences(text)
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Reasoner JSON parse failed | raw=%s", text[:200])
            return default

    # ── Public methods (synchronous) ──────────────────────────────────────────

    def understand_intent(self, question: str, schema_summary: str) -> IntentResult:
        raw = self._call(
            user=_INTENT_USER.format(question=question, schema_summary=schema_summary),
            system=_INTENT_SYSTEM,
            max_tokens=300,
            temperature=0.1,
        )
        parsed = self._parse_json(raw, {})
        try:
            return IntentResult(**{k: parsed[k] for k in IntentResult.model_fields if k in parsed})
        except Exception:
            logger.warning("Reasoner.understand_intent: IntentResult parse failed, using defaults")
            return IntentResult()

    def select_tables(
        self, question: str, table_list: list[str], schema_summary: str
    ) -> list[str]:
        raw = self._call(
            user=_TABLES_USER.format(
                question=question,
                table_list="\n".join(f"- {t}" for t in table_list),
                schema_summary=schema_summary,
            ),
            system=_TABLES_SYSTEM,
            max_tokens=200,
            temperature=0.1,
        )
        parsed = self._parse_json(raw, [])
        if isinstance(parsed, list):
            valid = [t for t in parsed if t in table_list]
            return valid if valid else table_list[:5]
        return table_list[:5]

    def generate_sql(
        self, question: str, relevant_schema: str, intent: IntentResult
    ) -> str:
        intent_summary = (
            f"operation={intent.operation_type}, "
            f"entities={intent.entities}, "
            f"filters={intent.filters}"
        )
        raw = self._call(
            user=_SQL_USER.format(
                question=question,
                schema=relevant_schema,
                intent_summary=intent_summary,
            ),
            system=_SQL_SYSTEM,
            max_tokens=400,
            temperature=0.05,
        )
        return self._strip_fences(raw)

    def generate_mongo_filter(
        self,
        question: str,
        collection: str,
        schema: str,
        intent: IntentResult,
    ) -> str:
        intent_summary = (
            f"operation={intent.operation_type}, "
            f"filters={intent.filters}"
        )
        raw = self._call(
            user=_MONGO_USER.format(
                question=question,
                collection=collection,
                schema=schema,
                intent_summary=intent_summary,
            ),
            system=_MONGO_SYSTEM.format(collection=collection),
            max_tokens=300,
            temperature=0.05,
        )
        cleaned = self._strip_fences(raw)
        # Verify it is valid JSON; fall back to empty filter on failure
        try:
            json.loads(cleaned)
            return cleaned
        except json.JSONDecodeError:
            logger.warning("Reasoner.generate_mongo_filter: invalid JSON, using {}")
            return "{}"

    def explain_plan(self, question: str, query: str, intent: IntentResult) -> str:
        return self._call(
            user=_PLAN_EXPLAIN_USER.format(question=question, query=query),
            system=_PLAN_EXPLAIN_SYSTEM,
            max_tokens=200,
            temperature=0.2,
        ) or "Query generated successfully."

    def fix_query_on_error(
        self, query: str, error: str, schema: str, question: str
    ) -> str:
        """Attempt to fix a failed query using the existing QueryOptimizer when possible."""
        try:
            from agents.db_explorer.query_optimizer import QueryOptimizer
            opt = QueryOptimizer()
            fixed = opt.fix_on_error(query, error, schema, question)
            if fixed and fixed.strip() != query.strip():
                return fixed
        except Exception as exc:
            logger.warning("Reasoner.fix_query_on_error: QueryOptimizer failed (%s), using LLM", exc)

        # Fallback to direct LLM call
        raw = self._call(
            user=_FIX_USER.format(query=query, error=error, schema=schema, question=question),
            system=_FIX_SYSTEM,
            max_tokens=400,
            temperature=0.1,
        )
        return self._strip_fences(raw) or query

    def summarize_results(
        self, question: str, query: str, results: list[dict], count: int
    ) -> str:
        if not results:
            return "The query returned no matching records."

        sample = json.dumps(results[:10], default=str)[:2000]
        return self._call(
            user=_SUMMARIZE_USER.format(
                question=question, query=query, count=count, results=sample
            ),
            system=_SUMMARIZE_SYSTEM,
            max_tokens=400,
            temperature=0.2,
        ) or f"Query returned {count} record(s)."
