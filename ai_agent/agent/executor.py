"""
Phase 2 — Executor

Takes a PlanResult and:
  1. Security gate — block unsafe queries before any execution
  2. Optimize SQL via MCP Tool 9 (skipped for MongoDB)
  3. Re-validate after optimization (defense-in-depth)
  4. Execute via MCP Tool 5 (SQL) or Tool 6 (MongoDB)
  5. Retry once on error with LLM-guided fix + re-validation
  6. LLM — summarize results in natural language

Returns an ExecutionResult.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any

from .reasoner import Reasoner
from ..mcp_client.proxy import MCPToolProxy
from ..security.guard import SecurityGuard
from ..models.responses import PlanResult, ExecutionResult
from ..config import AgentConfig

logger = logging.getLogger(__name__)


class Executor:
    """Stateless Phase 2 executor."""



    def __init__(self, reasoner: Reasoner, config: AgentConfig) -> None:
        self._reasoner = reasoner
        self._config = config

    async def execute(
        self, plan: PlanResult, proxy: MCPToolProxy, session_id: str
    ) -> ExecutionResult:
        query = plan.generated_query
        db_type = plan.db_type

        # Step 1: Security gate — hard block before any network/DB call
        is_safe, reason = SecurityGuard.validate(query, db_type, session_id)
        if not is_safe:
            logger.warning(
                "Executor: query BLOCKED | session=%s | reason=%s", session_id, reason
            )
            return ExecutionResult(
                success=False,
                query=query,
                data=[],
                row_count=0,
                summary=f"Query blocked by security guard: {reason}",
                blocked=True,
                block_reason=reason,
            )

        # Step 2: Optimize SQL (skip for MongoDB — no SQL AST to optimize)
        if db_type != "mongodb":
            try:
                opt_result = await proxy.optimize_query(query)
                optimized = opt_result.get("optimized", query)

                # Step 3: Re-validate optimized query
                is_safe2, reason2 = SecurityGuard.validate(optimized, db_type, session_id)
                if is_safe2:
                    if optimized.strip() != query.strip():
                        logger.debug("Executor: query optimized | session=%s", session_id)
                    query = optimized
                else:
                    logger.warning(
                        "Executor: optimized query failed re-validation, using original | session=%s",
                        session_id,
                    )
            except Exception as exc:
                logger.warning("Executor: optimize_query failed (%s), continuing", exc)

        # Step 4: Execute via MCP proxy
        rows, error = await self._run_query(plan, query, proxy)

        # Step 5: Retry once on error
        retried = False
        if error and self._config.MAX_RETRY_ATTEMPTS > 0:
            logger.info("Executor: retrying after error | session=%s | error=%.100s", session_id, error)
            fixed_query: str = await asyncio.to_thread(
                self._reasoner.fix_query_on_error,
                query, error, plan.schema_summary, plan.sanitized_question,
            )
            is_safe3, _ = SecurityGuard.validate(fixed_query, db_type, session_id)
            if is_safe3 and fixed_query.strip() != query.strip():
                rows, error = await self._run_query(plan, fixed_query, proxy)
                query = fixed_query
                retried = True

        if error and not rows:
            return ExecutionResult(
                success=False,
                query=query,
                data=[],
                row_count=0,
                summary=f"Execution failed: {error}",
                error=error,
                retried=retried,
            )

        # Step 6: LLM summarize results
        capped_rows = rows[: self._config.MAX_RESULT_ROWS]
        summary: str = await asyncio.to_thread(
            self._reasoner.summarize_results,
            plan.sanitized_question, query, capped_rows, len(rows),
        )

        return ExecutionResult(
            success=True,
            query=query,
            data=capped_rows,
            row_count=len(rows),
            summary=summary,
            retried=retried,
        )

    async def _run_query(
        self, plan: PlanResult, query: str, proxy: MCPToolProxy
    ) -> tuple[list[dict[str, Any]], str]:
        """Execute query via MCP. Returns (rows, error_message)."""
        try:
            if plan.db_type == "mongodb":
                collection = plan.relevant_tables[0] if plan.relevant_tables else ""
                if not collection:
                    return [], "No collection identified for MongoDB query"
                result = await proxy.run_mongo_query(collection, query)
            else:
                result = await proxy.run_sql_query(query)

            if result.get("blocked"):
                return [], result.get("reason", "Query blocked by MCP server")
            if not result.get("success"):
                return [], result.get("error", "Unknown execution error from MCP server")

            return result.get("data", []), ""

        except Exception as exc:
            logger.exception("Executor._run_query raised | query=%.80s", query)
            return [], str(exc)
