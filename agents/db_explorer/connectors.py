"""
Synchronous database connectors — works cleanly from asyncio.to_thread().
PostgreSQL: SQLAlchemy (sync), MongoDB: pymongo (sync), SQLite: sqlite3, File: pandas+sqlite3.
"""
from __future__ import annotations
import io
import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseConnector(ABC):
    db_type: str = "base"

    @abstractmethod
    def connect(self) -> bool: ...
    @abstractmethod
    def disconnect(self): ...
    @abstractmethod
    def get_schema(self) -> dict[str, list[dict]]: ...
    @abstractmethod
    def get_row_counts(self) -> dict[str, int]: ...
    @abstractmethod
    def sample(self, table: str, limit: int = 5) -> list[dict]: ...
    @abstractmethod
    def execute_sql(self, query: str) -> list[dict]: ...

    def execute_find(self, collection: str, filter_doc: dict,
                     projection: dict | None = None) -> list[dict]:
        raise NotImplementedError("execute_find only supported on MongoDB")

    # Async wrappers so async code can still call them
    async def aconnect(self): return self.connect()
    async def adisconnect(self): return self.disconnect()
    async def aget_schema(self): return self.get_schema()
    async def aget_row_counts(self): return self.get_row_counts()
    async def asample(self, table, limit=5): return self.sample(table, limit)
    async def aexecute_sql(self, query): return self.execute_sql(query)
    async def aexecute_find(self, col, f, p=None): return self.execute_find(col, f, p)


# ── PostgreSQL (SQLAlchemy sync) ──────────────────────────────────────────────

class PostgreSQLConnector(BaseConnector):
    db_type = "postgresql"

    def __init__(self, uri: str = "", host: str = "localhost", port: int = 5432,
                 dbname: str = "", username: str = "", password: str = ""):
        if uri:
            # Replace asyncpg scheme if present
            self._uri = uri.replace("postgresql+asyncpg://", "postgresql://").replace(
                "postgresql+psycopg2://", "postgresql://")
        else:
            self._uri = f"postgresql://{username}:{password}@{host}:{port}/{dbname}"
        self._engine = None

    def connect(self) -> bool:
        try:
            from sqlalchemy import create_engine, text
            self._engine = create_engine(self._uri, pool_pre_ping=True)
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            raise ConnectionError(f"PostgreSQL connection failed: {e}")

    def disconnect(self):
        if self._engine:
            self._engine.dispose()

    def _tables(self) -> list[str]:
        from sqlalchemy import text
        with self._engine.connect() as conn:
            r = conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
            ))
            return [row[0] for row in r]

    def get_schema(self) -> dict[str, list[dict]]:
        from sqlalchemy import text
        schema: dict[str, list[dict]] = {}
        with self._engine.connect() as conn:
            for table in self._tables():
                r = conn.execute(text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"
                ), {"t": table})
                schema[table] = [{"name": row[0], "type": row[1]} for row in r]
        return schema

    def get_row_counts(self) -> dict[str, int]:
        from sqlalchemy import text
        counts: dict[str, int] = {}
        with self._engine.connect() as conn:
            for table in self._tables():
                r = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                counts[table] = r.scalar()
        return counts

    def sample(self, table: str, limit: int = 5) -> list[dict]:
        from sqlalchemy import text
        with self._engine.connect() as conn:
            r = conn.execute(text(f'SELECT * FROM "{table}" LIMIT :n'), {"n": limit})
            cols = list(r.keys())
            return [dict(zip(cols, row)) for row in r]

    def execute_sql(self, query: str) -> list[dict]:
        from sqlalchemy import text
        with self._engine.connect() as conn:
            r = conn.execute(text(query))
            cols = list(r.keys())
            return [dict(zip(cols, row)) for row in r]


# ── MongoDB (pymongo sync) ────────────────────────────────────────────────────

class MongoDBConnector(BaseConnector):
    db_type = "mongodb"

    def __init__(self, uri: str = "", host: str = "localhost", port: int = 27017,
                 dbname: str = "", username: str = "", password: str = ""):
        if uri:
            self._uri = uri
            # Extract database name from URI path (e.g. mongodb://host:27017/demo → demo)
            from urllib.parse import urlparse
            db_from_uri = urlparse(uri).path.lstrip("/").split("?")[0]
            self._dbname = dbname or db_from_uri or "admin"
        elif username:
            self._uri = f"mongodb://{username}:{password}@{host}:{port}/{dbname}"
            self._dbname = dbname or "admin"
        else:
            self._uri = f"mongodb://{host}:{port}/{dbname}" if dbname else f"mongodb://{host}:{port}"
            self._dbname = dbname or "admin"
        self._client = None
        self._db = None

    def connect(self) -> bool:
        try:
            import pymongo
            self._client = pymongo.MongoClient(self._uri, serverSelectionTimeoutMS=5000)
            self._client.admin.command("ping")
            self._db = self._client[self._dbname]
            return True
        except Exception as e:
            raise ConnectionError(f"MongoDB connection failed: {e}")

    def disconnect(self):
        if self._client:
            self._client.close()

    def get_schema(self) -> dict[str, list[dict]]:
        schema: dict[str, list[dict]] = {}
        for col in self._db.list_collection_names():
            doc = self._db[col].find_one()
            if doc:
                schema[col] = [{"name": k, "type": type(v).__name__} for k, v in doc.items()]
            else:
                schema[col] = []
        return schema

    def get_row_counts(self) -> dict[str, int]:
        return {col: self._db[col].estimated_document_count()
                for col in self._db.list_collection_names()}

    def sample(self, table: str, limit: int = 5) -> list[dict]:
        return self._serialize(list(self._db[table].find({}).limit(limit)))

    def execute_sql(self, query: str) -> list[dict]:
        raise NotImplementedError("Use execute_find() for MongoDB")

    def execute_find(self, collection: str, filter_doc: dict,
                     projection: dict | None = None) -> list[dict]:
        proj = None
        if projection:
            proj = {k: 1 for k in projection}
            proj.setdefault("_id", 0)
        return self._serialize(list(self._db[collection].find(filter_doc, proj).limit(1000)))

    @staticmethod
    def _serialize(docs: list) -> list[dict]:
        return [{k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v)
                 for k, v in doc.items()} for doc in docs]


# ── SQLite (sqlite3 sync) ─────────────────────────────────────────────────────

class SQLiteConnector(BaseConnector):
    db_type = "sqlite"

    def __init__(self, path: str = ":memory:"):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> bool:
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        return True

    def disconnect(self):
        if self._conn:
            self._conn.close()

    def _tables(self) -> list[str]:
        cur = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return [r[0] for r in cur.fetchall()]

    def get_schema(self) -> dict[str, list[dict]]:
        schema: dict[str, list[dict]] = {}
        for table in self._tables():
            cur = self._conn.execute(f"PRAGMA table_info('{table}')")
            schema[table] = [{"name": r["name"], "type": r["type"]} for r in cur.fetchall()]
        return schema

    def get_row_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in self._tables():
            cur = self._conn.execute(f"SELECT COUNT(*) FROM '{table}'")
            counts[table] = cur.fetchone()[0]
        return counts

    def sample(self, table: str, limit: int = 5) -> list[dict]:
        cur = self._conn.execute(f"SELECT * FROM '{table}' LIMIT ?", (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute_sql(self, query: str) -> list[dict]:
        cur = self._conn.execute(query)
        if not cur.description:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── File Connector ────────────────────────────────────────────────────────────

class FileConnector(BaseConnector):
    db_type = "file"

    def __init__(self, filename: str, content: bytes):
        self._filename = filename
        self._content = content
        self._ext = Path(filename).suffix.lower()
        self._sqlite: SQLiteConnector | None = None
        self._docs: dict[str, list[dict]] = {}

    def connect(self) -> bool:
        if self._ext == ".csv":
            self._load_csv()
        elif self._ext in (".sqlite", ".db"):
            self._load_sqlite_file()
        elif self._ext == ".sql":
            self._load_sql_dump()
        elif self._ext == ".json":
            self._load_json()
        else:
            raise ValueError(f"Unsupported file type: {self._ext}. Supported: .csv .sqlite .sql .json")
        return True

    def _load_csv(self):
        import pandas as pd
        df = pd.read_csv(io.BytesIO(self._content))
        tname = Path(self._filename).stem.replace(" ", "_").lower()
        self._sqlite = SQLiteConnector(":memory:")
        self._sqlite.connect()
        col_defs = ", ".join(
            f'"{c}" {"REAL" if df[c].dtype.kind in "fiu" else "TEXT"}' for c in df.columns
        )
        self._sqlite._conn.execute(f'CREATE TABLE IF NOT EXISTS "{tname}" ({col_defs})')
        import math
        for _, row in df.iterrows():
            vals = [None if (isinstance(v, float) and math.isnan(v)) else v for v in row]
            ph = ", ".join(["?"] * len(df.columns))
            self._sqlite._conn.execute(f'INSERT INTO "{tname}" VALUES ({ph})', vals)
        self._sqlite._conn.commit()

    def _load_sqlite_file(self):
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
        tmp.write(self._content); tmp.flush(); tmp.close()
        self._sqlite = SQLiteConnector(tmp.name)
        self._sqlite.connect()

    def _load_sql_dump(self):
        text = self._content.decode("utf-8", errors="replace")
        self._sqlite = SQLiteConnector(":memory:")
        self._sqlite.connect()
        for stmt in text.split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            upper = stmt.upper().lstrip()
            if any(upper.startswith(k) for k in ("CREATE", "INSERT", "DROP", "ALTER")):
                try:
                    self._sqlite._conn.execute(stmt)
                except Exception:
                    pass
        self._sqlite._conn.commit()

    def _load_json(self):
        data = json.loads(self._content.decode("utf-8"))
        if isinstance(data, list):
            tname = Path(self._filename).stem.replace(" ", "_").lower()
            self._docs = {tname: data}
        elif isinstance(data, dict):
            first = next(iter(data.values()), None)
            self._docs = data if isinstance(first, list) else {"data": [data]}

    def disconnect(self):
        if self._sqlite:
            self._sqlite.disconnect()

    def get_schema(self) -> dict[str, list[dict]]:
        if self._sqlite:
            return self._sqlite.get_schema()
        return {
            col: ([{"name": k, "type": type(v).__name__} for k, v in self._docs[col][0].items()]
                  if self._docs.get(col) else [])
            for col in self._docs
        }

    def get_row_counts(self) -> dict[str, int]:
        if self._sqlite:
            return self._sqlite.get_row_counts()
        return {col: len(docs) for col, docs in self._docs.items()}

    def sample(self, table: str, limit: int = 5) -> list[dict]:
        if self._sqlite:
            return self._sqlite.sample(table, limit)
        return self._docs.get(table, [])[:limit]

    def execute_sql(self, query: str) -> list[dict]:
        if self._sqlite:
            return self._sqlite.execute_sql(query)
        raise NotImplementedError("SQL not supported on JSON document store — use execute_find()")

    def execute_find(self, collection: str, filter_doc: dict,
                     projection: dict | None = None) -> list[dict]:
        docs = self._docs.get(collection, [])
        if filter_doc:
            docs = [d for d in docs if all(str(d.get(k)) == str(v) for k, v in filter_doc.items())]
        return docs[:1000]


# ── Factory ───────────────────────────────────────────────────────────────────

def connector_factory(db_type: str, **kwargs) -> BaseConnector:
    mapping = {
        "postgresql": PostgreSQLConnector,
        "mongodb":    MongoDBConnector,
        "sqlite":     SQLiteConnector,
        "file":       FileConnector,
    }
    cls = mapping.get(db_type)
    if not cls:
        raise ValueError(f"Unknown db_type '{db_type}'. Choose: {list(mapping)}")
    return cls(**kwargs)
