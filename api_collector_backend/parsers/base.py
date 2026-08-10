# api_collector_backend/parsers/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Iterable, List
from ..models import ToolDescription, SourceInput


class BaseSourceParser(ABC):
    """
    Base class for all parsers (Postman, OpenAPI, SDK, URL-scraper, etc.)
    """

    @abstractmethod
    def can_handle(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> bool:
        """
        Return True if this parser can handle the given combination of file/url/sdk.
        May be used both for auto-detection and explicit source_type.
        """

    @abstractmethod
    def parse(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> List[ToolDescription]:
        """
        Parse and return a list of tool descriptions.
        """


class ParserRegistry:
    """
    Simple dependency-injection style registry.
    You register parser instances and ask the registry to choose the right one.
    """

    def __init__(self, parsers: Iterable[BaseSourceParser]) -> None:
        self._parsers: List[BaseSourceParser] = list(parsers)

    def register(self, parser: BaseSourceParser) -> None:
        self._parsers.append(parser)

    def resolve(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> BaseSourceParser:
        # If source.source_type is set, prefer parsers that match that explicit type.
        matching: List[BaseSourceParser] = []
        for p in self._parsers:
            if p.can_handle(raw_bytes=raw_bytes, filename=filename, source=source):
                matching.append(p)

        if not matching:
            # Provide helpful error message
            source_info = []
            if source.url:
                source_info.append(f"URL: {source.url}")
            if source.sdk_name:
                source_info.append(f"SDK: {source.sdk_name}")
            if filename:
                source_info.append(f"File: {filename}")
            if source.source_type:
                source_info.append(f"Type: {source.source_type}")
            if not source_info:
                source_info.append("(no source provided)")
            
            available_parsers = [p.__class__.__name__ for p in self._parsers]
            raise ValueError(
                f"No parser found for provided source ({', '.join(source_info)}). "
                f"Available parsers: {', '.join(available_parsers)}. "
                f"Please provide a file (Postman/OpenAPI), URL, or SDK name."
            )

        # Simple heuristic: first match wins; you can add priorities later.
        return matching[0]
