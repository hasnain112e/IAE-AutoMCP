"""
Shared utilities for the IAE-AutoMCP integrated agentic system.

Exports:
- a2a_protocol: A2A (Agent-to-Agent) Protocol utilities
- message_types: Pydantic models for message types
- config: Centralized configuration
- constants: Centralized constants
- sample_queries: Diverse sample query generator
"""

from .config import ServiceConfig, config
from .constants import (
    ScoreThresholds,
    ScoreDeductions,
    InputLimits,
    Timeouts,
    DefaultPorts,
    RuffErrorCodes,
    MCPComplianceCodes,
    IssueCategories,
    Priority,
    Severity,
)
from .sample_queries import (
    DiverseQueryGenerator,
    QueryType,
    SampleQuery,
    get_sample_queries,
    get_sample_queries_with_metadata,
    STATIC_DIVERSE_EXAMPLES,
)

__all__ = [
    # Config
    "ServiceConfig",
    "config",
    # Constants
    "ScoreThresholds",
    "ScoreDeductions",
    "InputLimits",
    "Timeouts",
    "DefaultPorts",
    "RuffErrorCodes",
    "MCPComplianceCodes",
    "IssueCategories",
    "Priority",
    "Severity",
    # Sample Queries
    "DiverseQueryGenerator",
    "QueryType",
    "SampleQuery",
    "get_sample_queries",
    "get_sample_queries_with_metadata",
    "STATIC_DIVERSE_EXAMPLES",
]
