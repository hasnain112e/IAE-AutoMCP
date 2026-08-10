"""
Self-improving query system.
  Round 1: LLM reviews generated query for correctness and efficiency.
  Round 2: Applies suggestions if changes were needed.
  On error: feeds DB error message back to LLM for correction.
"""
from __future__ import annotations
from openai import OpenAI
import os


OPTIMIZE_PROMPT = """\
You are a database query optimizer. Review the SQL query below against the schema context and original question.
Check for:
1. Wrong table referenced (not in schema)
2. Wrong column name (not in table)
3. Missing JOIN that would give more complete results
4. Unnecessary SELECT * when specific columns suffice
5. Missing WHERE clause narrowing the result
6. Inefficiency (e.g. no LIMIT on huge tables)

If the query is already good, respond with: OPTIMIZED: <same query>
If you improve it, respond with: OPTIMIZED: <new query>
Always end with: NOTES: <one-line explanation of what you changed, or "No changes needed">

Schema context:
{schema}

Original question: {question}

Query to review:
{query}
"""

FIX_PROMPT = """\
The following SQL/MongoDB query failed with this error:
ERROR: {error}

Original question: {question}
Schema context:
{schema}

Failed query:
{query}

Fix the query so it works correctly. Output ONLY the corrected query, nothing else.
"""


class QueryOptimizer:

    def __init__(self, api_key: str | None = None, model: str | None = None):
        _kwargs = dict(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            timeout=30.0,
            max_retries=1,
        )
        if os.getenv("OPENAI_BASE_URL"):
            _kwargs["base_url"] = os.getenv("OPENAI_BASE_URL")
        self._client = OpenAI(**_kwargs)
        self._model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def optimize(self, query: str, schema_context: str, question: str) -> dict:
        """
        Up to 2 rounds of optimization.
        Returns {original, optimized, notes, changed}.
        """
        original = query
        notes = "No changes needed"
        current = query

        for _ in range(2):
            prompt = OPTIMIZE_PROMPT.format(
                schema=schema_context[:3000],
                question=question,
                query=current
            )
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=600
                )
                text = resp.choices[0].message.content or ""
                optimized_line = ""
                notes_line = "No changes needed"
                for line in text.splitlines():
                    if line.startswith("OPTIMIZED:"):
                        optimized_line = line[len("OPTIMIZED:"):].strip()
                    if line.startswith("NOTES:"):
                        notes_line = line[len("NOTES:"):].strip()

                if optimized_line and optimized_line.upper() != current.upper():
                    current = optimized_line
                    notes = notes_line
                else:
                    break  # no further change needed
            except Exception:
                break

        return {
            "original": original,
            "optimized": current,
            "notes": notes,
            "changed": current.strip().upper() != original.strip().upper()
        }

    def fix_on_error(self, query: str, error_msg: str, schema_context: str, question: str) -> str:
        """Ask LLM to correct a query that failed at execution."""
        prompt = FIX_PROMPT.format(
            error=error_msg[:500],
            question=question,
            schema=schema_context[:3000],
            query=query
        )
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=400
            )
            fixed = (resp.choices[0].message.content or "").strip()
            return fixed if fixed else query
        except Exception:
            return query
