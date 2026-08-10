"""
Schema extraction, summarization, relevant-table selection, and in-memory caching.
"""
from __future__ import annotations
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connectors import BaseConnector

# In-memory cache: session_id → {schema, summary, counts}
_cache: dict[str, dict] = {}


class SchemaManager:

    # ── Sync extraction (used by ExplorerAgent) ────────────────────────────

    @staticmethod
    def extract_sync(connector: "BaseConnector") -> dict:
        """Sync version — call from sync context or asyncio.to_thread."""
        schema = connector.get_schema()
        counts = connector.get_row_counts()
        samples: dict[str, list] = {}
        for table in list(schema)[:20]:
            try:
                samples[table] = connector.sample(table, limit=3)
            except Exception:
                samples[table] = []
        return {"schema": schema, "counts": counts, "samples": samples}

    # ── Async extraction (legacy) ──────────────────────────────────────────

    @staticmethod
    async def extract(connector: "BaseConnector") -> dict:
        """Return {schema, counts, samples} for the connected database."""
        schema = await connector.get_schema()
        counts = await connector.get_row_counts()
        samples: dict[str, list] = {}
        for table in list(schema)[:20]:   # sample only first 20 tables
            try:
                samples[table] = await connector.sample(table, limit=3)
            except Exception:
                samples[table] = []
        return {"schema": schema, "counts": counts, "samples": samples}

    # ── Summarization ──────────────────────────────────────────────────────

    @staticmethod
    def summarize(data: dict, max_chars: int = 6000) -> str:
        """Compact human-readable schema string for LLM context."""
        schema  = data.get("schema", {})
        counts  = data.get("counts", {})
        samples = data.get("samples", {})
        lines: list[str] = []

        for table, cols in schema.items():
            row_count = counts.get(table, "?")
            col_names = ", ".join(f"{c['name']}({c['type']})" for c in cols[:20])
            lines.append(f"TABLE {table} [{row_count} rows]: {col_names}")
            sample_rows = samples.get(table, [])
            if sample_rows:
                for row in sample_rows[:2]:
                    preview = {k: v for k, v in list(row.items())[:6]}
                    lines.append(f"  sample: {preview}")

        summary = "\n".join(lines)
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "\n... (schema truncated)"
        return summary

    # ── Relevant table selection ───────────────────────────────────────────

    @staticmethod
    def select_relevant_tables(schema_data: dict, question: str, top_k: int = 8) -> list[str]:
        """
        Keyword overlap between the user question and table+column names.
        Returns top_k most relevant table names.
        """
        schema = schema_data.get("schema", {})
        if not schema:
            return []

        question_tokens = set(re.findall(r'\w+', question.lower()))
        # common stop words to ignore
        stopwords = {"the", "a", "an", "is", "in", "on", "of", "and", "or", "to",
                     "for", "with", "by", "all", "me", "show", "give", "get", "list",
                     "find", "what", "which", "how", "many", "where", "who", "from"}
        question_tokens -= stopwords

        scores: dict[str, int] = {}
        for table, cols in schema.items():
            table_tokens = set(re.findall(r'\w+', table.lower()))
            col_tokens: set[str] = set()
            for c in cols:
                col_tokens.update(re.findall(r'\w+', c["name"].lower()))
            all_tokens = table_tokens | col_tokens
            scores[table] = len(question_tokens & all_tokens)

        # Sort by score desc, return top_k; always include at least something
        ranked = sorted(scores, key=lambda t: scores[t], reverse=True)
        result = ranked[:top_k]
        if not result:
            result = list(schema.keys())[:top_k]
        return result

    @staticmethod
    def build_context(schema_data: dict, relevant_tables: list[str], max_chars: int = 4000) -> str:
        """Compact schema string for only the relevant tables."""
        schema  = schema_data.get("schema", {})
        counts  = schema_data.get("counts", {})
        samples = schema_data.get("samples", {})
        lines: list[str] = []

        for table in relevant_tables:
            if table not in schema:
                continue
            cols = schema[table]
            row_count = counts.get(table, "?")
            col_names = ", ".join(f"{c['name']}({c['type']})" for c in cols)
            lines.append(f"TABLE {table} [{row_count} rows]: {col_names}")
            for row in samples.get(table, [])[:2]:
                preview = {k: v for k, v in list(row.items())[:6]}
                lines.append(f"  sample: {preview}")

        ctx = "\n".join(lines)
        if len(ctx) > max_chars:
            ctx = ctx[:max_chars] + "\n..."
        return ctx

    # ── Cache ──────────────────────────────────────────────────────────────

    @staticmethod
    def cache_set(session_id: str, data: dict):
        _cache[session_id] = data

    @staticmethod
    def cache_get(session_id: str) -> dict | None:
        return _cache.get(session_id)

    @staticmethod
    def cache_clear(session_id: str):
        _cache.pop(session_id, None)
