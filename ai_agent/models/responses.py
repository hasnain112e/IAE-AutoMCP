"""Pydantic v2 response schemas for the AI Agent API."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class ConnectResponse(BaseModel):
    success: bool
    session_id: str = ""
    db_type: str = ""
    table_count: int = 0
    tables: list[str] = Field(default_factory=list)
    error: str = ""


class IntentResult(BaseModel):
    operation_type: str = "lookup"       # aggregate | filter | lookup | count | sample
    entities: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    output_format: str = "table"         # table | count | list
    confidence: float = 0.0


class PlanResult(BaseModel):
    question: str
    sanitized_question: str
    intent: IntentResult
    relevant_tables: list[str] = Field(default_factory=list)
    generated_query: str
    db_type: str
    plan_explanation: str
    schema_summary: str


class ExecutionResult(BaseModel):
    success: bool
    query: str
    data: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    summary: str = ""
    blocked: bool = False
    block_reason: str = ""
    error: str = ""
    retried: bool = False


class QueryResponse(BaseModel):
    success: bool
    session_id: str
    question: str
    plan: PlanResult | None = None
    execution: ExecutionResult | None = None
    error: str = ""


class SchemaResponse(BaseModel):
    success: bool
    session_id: str
    db_schema: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    error: str = ""


class HistoryEntry(BaseModel):
    question: str
    query: str
    row_count: int
    success: bool
    timestamp: str


class HistoryResponse(BaseModel):
    success: bool
    session_id: str
    history: list[HistoryEntry] = Field(default_factory=list)


class AuditEntry(BaseModel):
    query: str
    safe: bool
    reason: str
    timestamp: str


class AuditResponse(BaseModel):
    success: bool
    session_id: str
    audit: list[AuditEntry] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    service: str
    port: int
    active_sessions: int
