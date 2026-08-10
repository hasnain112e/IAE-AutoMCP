# api_collector_backend/parsers/tools_json_parser.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import json

from .base import BaseSourceParser
from ..models import ToolDescription, ToolParameter, SourceInput
from ..utils.filetype_detection import guess_extension


class ToolsJSONParser(BaseSourceParser):
    """
    Parser for tools JSON files exported from this system.
    These are arrays of tool objects, not OpenAPI specs or Postman collections.
    """
    TYPE_NAME = "tools_json"

    def can_handle(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> bool:
        # Don't handle if explicitly set to another type (like 'openapi', 'postman', etc.)
        if source.source_type and source.source_type.lower() in {"openapi", "postman", "sdk", "url"}:
            return False

        ext = guess_extension(filename, None)
        if ext not in {"json", ""}:
            return False
            
        if not raw_bytes:
            return False

        try:
            data = json.loads(raw_bytes.decode("utf-8", errors="ignore") or "{}")
            
            # Handle CollectToolsResponse format (has "tools" key)
            if isinstance(data, dict) and "tools" in data:
                tools_list = data["tools"]
                if isinstance(tools_list, list) and len(tools_list) > 0:
                    first_item = tools_list[0]
                    if isinstance(first_item, dict) and "name" in first_item and "description" in first_item:
                        return True
            
            # Check if it's an array of tool objects (exported tools format)
            if isinstance(data, list) and len(data) > 0:
                # Check if first item looks like a tool object
                first_item = data[0]
                if isinstance(first_item, dict):
                    # Tools exported from this system have: name, description, method, path, parameters, etc.
                    # But NOT "paths" (OpenAPI) or "info"+"item" (Postman)
                    if "name" in first_item and "description" in first_item:
                        # Make sure it's not OpenAPI or Postman format by checking for their distinctive keys
                        if "paths" not in first_item and not ("info" in first_item and "item" in first_item):
                            return True
            
            # Also check if it's a single tool object (but not OpenAPI/Postman)
            if isinstance(data, dict):
                # Must have name+description (tool object) but NOT paths (OpenAPI) or info+item (Postman)
                if "name" in data and "description" in data:
                    # Definitely not OpenAPI (has "paths") or Postman (has "info"+"item")
                    if "paths" not in data and not ("info" in data and "item" in data):
                        return True
                
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
            raise ValueError("Tools JSON parser requires file bytes.")

        text = raw_bytes.decode("utf-8", errors="ignore")
        data = json.loads(text)

        # Handle CollectToolsResponse format (has "tools" key)
        if isinstance(data, dict) and "tools" in data:
            tools_data = data["tools"]
            if not isinstance(tools_data, list):
                raise ValueError("Invalid tools JSON format. 'tools' key must contain an array.")
        # Handle array of tools
        elif isinstance(data, list):
            tools_data = data
        # Handle single tool object
        elif isinstance(data, dict) and "name" in data:
            tools_data = [data]
        else:
            raise ValueError("Invalid tools JSON format. Expected array of tool objects, single tool object, or CollectToolsResponse with 'tools' key.")

        tools: List[ToolDescription] = []
        for tool_dict in tools_data:
            # Convert dict to ToolDescription
            tool = ToolDescription(
                name=tool_dict.get("name", ""),
                description=tool_dict.get("description", ""),
                method=tool_dict.get("method"),
                path=tool_dict.get("path"),
                parameters=[
                    ToolParameter(
                        name=param.get("name", ""),
                        type=param.get("type", "string"),
                        required=param.get("required", False),
                        description=param.get("description"),
                        default=param.get("default"),
                    )
                    for param in tool_dict.get("parameters", [])
                ],
                tags=tool_dict.get("tags", []),
                metadata=tool_dict.get("metadata", {}),
            )
            tools.append(tool)

        return tools

