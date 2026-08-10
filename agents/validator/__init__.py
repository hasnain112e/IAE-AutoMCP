"""
Validator Agent Module

Provides code validation with multi-phase checks:
- Phase 0: Ruff autofix and fix_instructions generation
- Phase 1: Syntax and execution viability checks
- Phase 2: Quality scoring with MCP compliance

Exports:
- ValidatorAgent: Main validator agent class
- check_mcp_compliance: MCP Inspector function
- MCPInspector: Full MCP compliance checker class
"""

from .mcp_compliance import check_mcp_compliance, MCPInspector
from .validator_agent import ValidatorAgent

__all__ = [
    "ValidatorAgent",
    "check_mcp_compliance",
    "MCPInspector",
]
