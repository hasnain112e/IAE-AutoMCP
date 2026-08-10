# api_collector_backend/models.py
from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, HttpUrl, Field


class SourceType(str):
    """Optional explicit override: 'postman', 'openapi', 'sdk', 'url'."""
    POSTMAN = "postman"
    OPENAPI = "openapi"
    SDK = "sdk"
    URL = "url"


class SourceInput(BaseModel):
    # Exactly one of these should be provided per request.
    source_type: Optional[str] = Field(
        default=None,
        description="Optional explicit type: postman | openapi | sdk | url. "
                    "If omitted, backend will try to auto-detect from content/extension."
    )
    # 1) Uploaded file: handled via /collect-tools endpoint (Form + UploadFile)
    # 2) URL: docs endpoint or swagger.json URL
    url: Optional[HttpUrl] = Field(
        default=None,
        description="Documentation URL or raw OpenAPI/JSON URL."
    )
    # 3) SDK name: python module (e.g. 'fmpsdk', 'pycoingecko')
    sdk_name: Optional[str] = Field(
        default=None,
        description="Python SDK/module to introspect (e.g. 'fmpsdk', 'pycoingecko')."
    )


class ToolParameter(BaseModel):
    name: str
    type: str = Field(default="string", description="JSON-schema-ish type name.")
    required: bool = False
    description: Optional[str] = None
    default: Optional[str] = None


class ToolDescription(BaseModel):
    name: str
    description: str
    method: Optional[str] = None         # for HTTP-based parsers
    path: Optional[str] = None           # for HTTP-based parsers
    tags: List[str] = []
    parameters: List[ToolParameter] = []
    # Raw / extra metadata (e.g. base_url, full_url, sdk_function_name, etc.)
    metadata: dict = {}


class CollectToolsRequest(BaseModel):
    source: SourceInput
    output_format: Literal["json", "csv"] = "json"
    # Optional hint for file extension when we cannot see original filename
    file_extension_hint: Optional[str] = None


class CollectToolsResponse(BaseModel):
    source_type: str
    tools: List[ToolDescription]
    output_format: str
    # If output_format == "csv", backend can also return a text CSV payload here
    csv_content: Optional[str] = None
