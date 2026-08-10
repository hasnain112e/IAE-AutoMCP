# api_collector_backend/parsers/postman_parser.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import json

from .base import BaseSourceParser
from ..models import ToolDescription, ToolParameter, SourceInput
from ..utils.filetype_detection import guess_extension


class PostmanCollectionParser(BaseSourceParser):
    TYPE_NAME = "postman"

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
        if ext in {"postman_collection", "postman", "json"} and raw_bytes:
            try:
                data = json.loads(raw_bytes.decode("utf-8", errors="ignore") or "{}")
            except Exception:
                return False
            # heuristic: Postman has 'info' + 'item'
            return isinstance(data, dict) and "item" in data and "info" in data
        return False

    def parse(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> List[ToolDescription]:
        if not raw_bytes:
            raise ValueError("Postman parser requires file bytes.")

        data = json.loads(raw_bytes.decode("utf-8", errors="ignore"))

        tools: List[ToolDescription] = []
        collection_info = data.get("info", {})
        default_tag = collection_info.get("name") or "postman"

        def walk_items(items: List[Dict[str, Any]], parent_tags: List[str]) -> None:
            for it in items:
                name = it.get("name") or "unnamed"
                request = it.get("request")
                children = it.get("item")
                current_tags = parent_tags + [name]

                if request:
                    tools.append(self._tool_from_request(name, request, current_tags))
                if children:
                    walk_items(children, current_tags)

        walk_items(data.get("item", []), [default_tag])
        return tools

    def _tool_from_request(
        self,
        name: str,
        request: Dict[str, Any],
        tags: List[str],
    ) -> ToolDescription:
        method = (request.get("method") or "GET").upper()
        # URL may be either a dict or raw string
        url = request.get("url")
        path = None
        base_url = None
        if isinstance(url, dict):
            raw = url.get("raw") or ""
            path = "/" + "/".join(url.get("path") or [])
            base_url = raw.replace(path, "") if path and raw.endswith(path) else None
        elif isinstance(url, str):
            path = url
            base_url = None

        # Very light parsing of body for parameters
        body_params: List[ToolParameter] = []
        body = request.get("body")
        if isinstance(body, dict) and body.get("mode") == "raw":
            raw = body.get("raw")
            if isinstance(raw, str):
                try:
                    payload = json.loads(raw)
                    if isinstance(payload, dict):
                        for k, v in payload.items():
                            body_params.append(
                                ToolParameter(
                                    name=k,
                                    type=type(v).__name__,
                                    required=True,
                                    default=None,
                                )
                            )
                except Exception:
                    pass

        return ToolDescription(
            name=self._normalize_name(name, method, path),
            description=f"HTTP {method} {path or ''} from Postman collection.",
            method=method,
            path=path,
            tags=tags,
            parameters=body_params,
            metadata={
                "base_url": base_url,
                "source": "postman_collection",
            },
        )

    def _normalize_name(self, name: str, method: str, path: Optional[str]) -> str:
        raw = f"{name} {method} {path or ''}"
        sanitized = "".join(
            ch if ch.isalnum() else "_" for ch in raw.lower()
        ).strip("_")
        if sanitized and sanitized[0].isdigit():
            sanitized = "e_" + sanitized
        return sanitized[:64]
