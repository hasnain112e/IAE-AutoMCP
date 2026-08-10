"""Pydantic v2 request schemas for the AI Agent API."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ConnectRequest(BaseModel):
    db_type: Literal["postgresql", "mongodb"]
    uri: str = ""
    host: str = "localhost"
    port: int = 27017
    dbname: str = ""
    username: str = ""
    password: str = ""


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class SampleRequest(BaseModel):
    table: str
    limit: int = Field(default=5, ge=1, le=100)
