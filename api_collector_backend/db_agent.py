"""
DB Agent — connects to a user's MongoDB, runs NL queries via the generated MCP tools.

Flow:
  POST /db-agent/connect  →  session_id + schema
  POST /db-agent/query    →  NL question → real MongoDB data + answer
"""
from __future__ import annotations
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient
from bson import ObjectId

# ── Session store (in-memory) ─────────────────────────────────────────────────
_sessions: dict[str, dict] = {}


def _serialize(docs: list) -> list[dict]:
    out = []
    for d in docs:
        row = {k: str(v) if isinstance(v, ObjectId) else v for k, v in d.items()}
        out.append(row)
    return out


# ── Connect ───────────────────────────────────────────────────────────────────

def create_session(uri: str, dbname: str) -> dict:
    """Connect to MongoDB, discover schema, create a session. Returns session info."""
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[dbname]

    schema: dict[str, list[dict]] = {}
    sample: dict[str, list[dict]] = {}
    for col in db.list_collection_names():
        doc = db[col].find_one()
        if doc:
            schema[col] = [{"name": k, "type": type(v).__name__} for k, v in doc.items() if k != "_id"]
            raw = list(db[col].find({}).limit(2))
            sample[col] = _serialize(raw)
        else:
            schema[col] = []
            sample[col] = []

    client.close()

    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "uri": uri,
        "dbname": dbname,
        "schema": schema,
        "sample": sample,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "session_id": session_id,
        "dbname": dbname,
        "collections": list(schema.keys()),
        "schema": schema,
    }


def get_session(session_id: str) -> dict | None:
    return _sessions.get(session_id)


# ── NL → Query ────────────────────────────────────────────────────────────────

def _run_mongo(uri: str, dbname: str, collection: str,
               filter_doc: dict, limit: int = 20) -> list[dict]:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    docs = list(client[dbname][collection].find(filter_doc).limit(limit))
    client.close()
    return _serialize(docs)


def _count_mongo(uri: str, dbname: str, collection: str, filter_doc: dict) -> int:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    n = client[dbname][collection].count_documents(filter_doc)
    client.close()
    return n


def _llm_parse(question: str, schema: dict, sample: dict) -> dict | None:
    """Ask LLM to convert NL question → {collection, filter, limit, intent}."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        return None
    try:
        import httpx
        from openai import OpenAI
        http = httpx.Client(timeout=12.0)
        client = OpenAI(api_key=api_key, base_url=base_url or None, http_client=http)

        schema_str = json.dumps(
            {col: [f["name"] for f in fields] for col, fields in schema.items()}, indent=2
        )
        sample_str = json.dumps(
            {col: docs[:1] for col, docs in sample.items()}, indent=2
        )

        system = (
            "You are a MongoDB query assistant. Given a database schema and a natural language question, "
            "return a JSON object with these fields:\n"
            "  collection: string  (which collection to query)\n"
            "  filter: object      (MongoDB filter document, use {} for all)\n"
            "  limit: integer      (max results, default 10)\n"
            "  intent: string      (one of: 'find', 'count', 'aggregate')\n\n"
            "IMPORTANT: For string filter values (like status, category, etc.), use the EXACT case "
            "from the sample data. For example if sample shows 'active' use 'active' not 'Active'.\n\n"
            "Return ONLY valid JSON. No explanation.\n\n"
            f"Schema:\n{schema_str}\n\nSample data:\n{sample_str}"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Strip markdown fences if present
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        return json.loads(raw)
    except Exception:
        return None


def _keyword_parse(question: str, schema: dict) -> dict:
    """Fallback: keyword-based NL → collection + filter (no LLM needed)."""
    q = question.lower()
    collections = list(schema.keys())

    # Detect collection
    collection = collections[0] if collections else "data"
    for col in collections:
        if col.lower() in q or col.lower().rstrip("s") in q:
            collection = col
            break

    # Detect intent
    intent = "count" if any(w in q for w in ("how many", "count", "total number")) else "find"

    # Detect simple filters from field values
    filter_doc: dict[str, Any] = {}
    fields = [f["name"] for f in schema.get(collection, [])]

    # Common status filters
    for status in ("active", "inactive", "pending", "completed", "cancelled", "shipped"):
        if status in q:
            for f in fields:
                if "status" in f.lower():
                    filter_doc[f] = status   # keep lowercase to match real data
                    break
            if not filter_doc:
                filter_doc["status"] = status

    # Common department/category filters — grab quoted or capitalised words
    quoted = re.findall(r'"([^"]+)"', question) + re.findall(r"'([^']+)'", question)
    for val in quoted:
        for f in fields:
            if any(k in f.lower() for k in ("department", "category", "type", "role")):
                filter_doc[f] = val
                break

    limit = 10
    m = re.search(r"\b(\d+)\b", q)
    if m and int(m.group(1)) <= 100:
        limit = int(m.group(1))

    return {"collection": collection, "filter": filter_doc, "limit": limit, "intent": intent}


def answer_question(session_id: str, question: str) -> dict:
    """
    Main entry point: NL question → real MongoDB data + human-readable answer.
    """
    session = _sessions.get(session_id)
    if not session:
        return {"error": "Session not found. Please connect first."}

    uri = session["uri"]
    dbname = session["dbname"]
    schema = session["schema"]
    sample = session["sample"]

    # Parse: try LLM first, fallback to keyword
    parsed = _llm_parse(question, schema, sample) or _keyword_parse(question, schema)

    collection = parsed.get("collection", list(schema.keys())[0] if schema else "data")
    filter_doc = parsed.get("filter", {})

    # Normalize status-like string values to lowercase (LLMs often capitalize them)
    _STATUS_FIELDS = {"status", "state", "type", "role", "category"}
    filter_doc = {
        k: (v.lower() if isinstance(v, str) and any(s in k.lower() for s in _STATUS_FIELDS) else v)
        for k, v in filter_doc.items()
    }
    limit = min(int(parsed.get("limit", 10)), 50)
    intent = parsed.get("intent", "find")

    # Execute
    try:
        if intent == "count":
            count = _count_mongo(uri, dbname, collection, filter_doc)
            answer = f"Found **{count}** document(s) in `{collection}`"
            if filter_doc:
                answer += f" matching filter `{json.dumps(filter_doc)}`"
            answer += "."
            return {
                "answer": answer,
                "collection": collection,
                "filter": filter_doc,
                "intent": intent,
                "count": count,
                "data": [],
            }
        else:
            docs = _run_mongo(uri, dbname, collection, filter_doc, limit)
            if docs:
                answer = f"Found **{len(docs)}** result(s) from `{collection}`"
                if filter_doc:
                    answer += f" where `{json.dumps(filter_doc)}`"
                answer += "."
            else:
                answer = f"No results found in `{collection}`"
                if filter_doc:
                    answer += f" for filter `{json.dumps(filter_doc)}`"
                answer += "."
            return {
                "answer": answer,
                "collection": collection,
                "filter": filter_doc,
                "intent": intent,
                "count": len(docs),
                "data": docs,
            }
    except Exception as e:
        return {"error": str(e), "collection": collection, "filter": filter_doc}
