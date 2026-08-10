"""
Phase 1 — Planner

Takes a user question and a live MCPToolProxy, then:
  1. Sanitizes input (strip prompt injection)
  2. Fetches live schema and summary via MCP
  3. LLM: understand intent
  4. LLM: select relevant tables/collections
  5. Builds focused schema context
  6. LLM: generate SQL SELECT or MongoDB filter
  7. LLM: explain the planned query in plain English

Returns a PlanResult. No security validation is performed here — that is
Phase 2's responsibility.
"""
from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.db_explorer.safety import ProductionQueryValidator
from agents.db_explorer.schema_manager import SchemaManager

from .reasoner import Reasoner
from ..mcp_client.proxy import MCPToolProxy
from ..models.responses import PlanResult, IntentResult

logger = logging.getLogger(__name__)


class Planner:
    """Stateless Phase 1 executor. Each call to plan() is independent."""

    def __init__(self, reasoner: Reasoner) -> None:
        self._reasoner = reasoner

    async def plan(
        self, question: str, proxy: MCPToolProxy, db_type: str
    ) -> PlanResult:
        logger.info("Planner.plan | db_type=%s | question=%.80s", db_type, question)

        # Step 1: Sanitize — strip prompt injection attempts from natural language
        sanitized = ProductionQueryValidator.strip_prompt_injection(question)

        # Step 2 + 3: Fetch schema and compact summary from MCP server
        schema_dict = await proxy.get_schema()
        schema_summary = await proxy.summarize_schema()

        # Step 4: LLM — understand user intent (wrapped in to_thread: sync OpenAI)
        intent: IntentResult = await asyncio.to_thread(
            self._reasoner.understand_intent, sanitized, schema_summary
        )
        logger.debug(
            "Planner: intent | op=%s | entities=%s | confidence=%.2f",
            intent.operation_type, intent.entities, intent.confidence,
        )

        # Step 5: LLM — select relevant tables/collections
        all_tables = list(schema_dict.keys())
        relevant_tables: list[str] = await asyncio.to_thread(
            self._reasoner.select_tables, sanitized, all_tables, schema_summary
        )
        if not relevant_tables:
            relevant_tables = all_tables[:3]
        logger.debug("Planner: relevant_tables=%s", relevant_tables)

        # Step 6: Build focused schema context (reuses existing SchemaManager utility)
        cached_schema = {"schema": schema_dict, "counts": {}, "samples": {}}
        relevant_schema = SchemaManager.build_context(cached_schema, relevant_tables)

        # Step 7: LLM — generate query
        if db_type == "mongodb":
            collection = relevant_tables[0] if relevant_tables else (all_tables[0] if all_tables else "")
            generated_query: str = await asyncio.to_thread(
                self._reasoner.generate_mongo_filter,
                sanitized, collection, relevant_schema, intent,
            )
        else:
            generated_query = await asyncio.to_thread(
                self._reasoner.generate_sql, sanitized, relevant_schema, intent
            )
        logger.debug("Planner: generated_query=%.120s", generated_query)

        # Step 8: LLM — explain the plan in plain English
        plan_explanation: str = await asyncio.to_thread(
            self._reasoner.explain_plan, sanitized, generated_query, intent
        )

        return PlanResult(
            question=question,
            sanitized_question=sanitized,
            intent=intent,
            relevant_tables=relevant_tables,
            generated_query=generated_query,
            db_type=db_type,
            plan_explanation=plan_explanation,
            schema_summary=schema_summary,
        )
