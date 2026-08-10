# Edited by Dr. Wasim
"""
APICollector - Main service for collecting tools from various sources.
"""
from __future__ import annotations
from typing import Optional

from ..models import CollectToolsRequest, CollectToolsResponse, SourceInput
from ..parsers.base import ParserRegistry
from ..parsers.openapi_parser import OpenAPISpecParser
from ..parsers.postman_parser import PostmanCollectionParser
from ..parsers.sdk_parser import PythonSDKParser
from ..parsers.url_parser import URLDocsParser
from ..parsers.tools_json_parser import ToolsJSONParser


class APICollector:
    """
    Main service for collecting tools from various sources (Postman, OpenAPI, SDKs, URLs).
    
    Uses a parser registry to automatically select the appropriate parser based on
    the source type and content.
    """
    
    def __init__(self):
        """Initialize the collector with all available parsers."""
        # Create parser instances
        parsers = [
            OpenAPISpecParser(),
            PostmanCollectionParser(),
            PythonSDKParser(),
            URLDocsParser(),
            ToolsJSONParser(),
        ]
        
        # Create registry with all parsers
        self.registry = ParserRegistry(parsers)
    
    def collect_tools(
        self,
        *,
        request: CollectToolsRequest,
        raw_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
    ) -> CollectToolsResponse:
        """
        Collect tools from the provided source.
        
        Args:
            request: The collection request containing source information
            raw_bytes: Raw file content (if file was uploaded)
            filename: Original filename (if file was uploaded)
            
        Returns:
            CollectToolsResponse with parsed tools
            
        Raises:
            ValueError: If no parser can handle the source
            Exception: If parsing fails
        """
        # Resolve the appropriate parser for this source
        parser = self.registry.resolve(
            raw_bytes=raw_bytes,
            filename=filename,
            source=request.source,
        )
        
        # Parse tools using the selected parser
        tools = parser.parse(
            raw_bytes=raw_bytes,
            filename=filename,
            source=request.source,
        )
        
        # Determine source type from parser or request
        source_type = request.source.source_type
        if not source_type:
            # Try to infer from parser type
            if hasattr(parser, 'TYPE_NAME'):
                source_type = parser.TYPE_NAME
            else:
                source_type = "unknown"
        
        # Build response
        response = CollectToolsResponse(
            source_type=source_type,
            tools=tools,
            output_format=request.output_format,
        )
        
        # If CSV format requested, generate CSV content
        if request.output_format == "csv":
            response.csv_content = self._generate_csv(tools)
        
        return response
    
    def _generate_csv(self, tools: list) -> str:
        """
        Generate CSV content from tools list.
        
        Args:
            tools: List of ToolDescription objects
            
        Returns:
            CSV string
        """
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "Name",
            "Description",
            "Method",
            "Path",
            "Tags",
            "Parameters",
        ])
        
        # Write tool rows
        for tool in tools:
            params_str = "; ".join([
                f"{p.name}({p.type})" for p in tool.parameters
            ])
            tags_str = ", ".join(tool.tags) if tool.tags else ""
            
            writer.writerow([
                tool.name,
                tool.description or "",
                tool.method or "",
                tool.path or "",
                tags_str,
                params_str,
            ])
        
        return output.getvalue()
