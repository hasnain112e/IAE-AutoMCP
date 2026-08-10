# api_collector_backend/parsers/openapi_parser.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import json

from .base import BaseSourceParser
from ..models import ToolDescription, ToolParameter, SourceInput
from ..utils.filetype_detection import guess_extension

try:
    import yaml
except Exception:
    yaml = None


class OpenAPISpecParser(BaseSourceParser):
    TYPE_NAME = "openapi"

    def can_handle(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> bool:
        if source.source_type and source.source_type.lower() != self.TYPE_NAME:
            return False

        ext = guess_extension(filename, None)
        if not raw_bytes:
            return False

        if ext in {"yaml", "yml"} and yaml is not None:
            try:
                data = yaml.safe_load(raw_bytes.decode("utf-8", errors="ignore"))
                return isinstance(data, dict) and "paths" in data
            except Exception:
                return False
        if ext in {"json", ""}:
            try:
                data = json.loads(raw_bytes.decode("utf-8", errors="ignore") or "{}")
                return isinstance(data, dict) and "paths" in data
            except Exception:
                return False
        return False

    def parse(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> List[ToolDescription]:
        if not raw_bytes:
            raise ValueError("OpenAPI parser requires file bytes.")

        text = raw_bytes.decode("utf-8", errors="ignore")
        ext = guess_extension(filename, None)

        if ext in {"yaml", "yml"} and yaml is not None:
            spec = yaml.safe_load(text)
        else:
            spec = json.loads(text)

        servers = spec.get("servers") or []
        base_url = servers[0].get("url") if servers else None

        tools: List[ToolDescription] = []
        for path, methods in (spec.get("paths") or {}).items():
            for method, op in (methods or {}).items():
                if method.lower() not in {"get", "post", "put", "delete", "patch"}:
                    continue
                tools.append(
                    self._tool_from_operation(
                        method=method.upper(),
                        path=path,
                        op=op,
                        base_url=base_url,
                    )
                )
        return tools

    def _tool_from_operation(
        self,
        *,
        method: str,
        path: str,
        op: Dict[str, Any],
        base_url: Optional[str],
    ) -> ToolDescription:
        name = op.get("operationId") or f"{method} {path}"
        summary = op.get("summary") or op.get("description") or ""
        tags = op.get("tags") or []

        params: List[ToolParameter] = []
        for p in op.get("parameters", []):
            params.append(
                ToolParameter(
                    name=p.get("name", "param"),
                    type=(p.get("schema") or {}).get("type") or "string",
                    required=bool(p.get("required")),
                    description=p.get("description"),
                )
            )

        request_body = op.get("requestBody")
        if isinstance(request_body, dict):
            # very light: treat JSON body properties as params
            content = request_body.get("content") or {}
            app_json = content.get("application/json") or {}
            schema = app_json.get("schema") or {}
            if schema.get("type") == "object":
                for pname, prop in (schema.get("properties") or {}).items():
                    params.append(
                        ToolParameter(
                            name=pname,
                            type=prop.get("type", "string"),
                            required=pname in (schema.get("required") or []),
                            description=prop.get("description"),
                        )
                    )

        return ToolDescription(
            name=self._normalize_name(name),
            description=summary or f"OpenAPI {method} {path}",
            method=method,
            path=path,
            tags=tags,
            parameters=params,
            metadata={
                "base_url": base_url,
                "source": "openapi",
            },
        )

    def _normalize_name(self, name: str) -> str:
        sanitized = "".join(
            ch if ch.isalnum() else "_" for ch in name.lower()
        ).strip("_")
        if sanitized and sanitized[0].isdigit():
            sanitized = "e_" + sanitized
        return sanitized[:64]
