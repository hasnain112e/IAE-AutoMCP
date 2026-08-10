"""
Centralized Constants Module

All magic numbers, timeouts, limits, and constant values used across
the MCPValidator3 system are defined here.
"""

from enum import Enum


# =============================================================================
# Scoring Constants
# =============================================================================

class ScoreThresholds:
    """Score thresholds for validation decisions."""
    MIN_SCORE = 10  # Minimum score (never 0 - allows learning gradient)
    APPROVAL_THRESHOLD = 80  # Minimum score for approval
    PERFECT_SCORE = 100  # Maximum achievable score
    WARNING_THRESHOLD = 70  # Below this triggers warnings


class ScoreDeductions:
    """Points deducted for various issues."""
    # Fatal errors
    SYNTAX_ERROR = 30
    UNDEFINED_NAME = 20
    MISSING_IMPORT = 15
    
    # Critical issues
    CRITICAL_DEFAULT = 15
    MISSING_FASTMCP = 50
    REGRESSION_IMPORT_REMOVED = 30
    
    # Warnings
    WARNING_DEFAULT = 5
    MAX_WARNING_TOTAL = 20
    
    # Categories
    MAX_SYNTAX_DEDUCTION = 40
    MAX_REGRESSION_DEDUCTION = 30
    MAX_IMPORT_DEDUCTION = 50
    MAX_RUNTIME_DEDUCTION = 30
    MAX_MCP_COMPLIANCE_DEDUCTION = 20


# =============================================================================
# Input Limits
# =============================================================================

class InputLimits:
    """Input size limits for DoS prevention."""
    MAX_CODE_SIZE = 1_000_000  # 1MB maximum code size
    MAX_LINES = 10_000  # Maximum lines of code
    MAX_TOOLS = 100  # Maximum number of tools per request
    MAX_ITERATION = 10  # Maximum iterations per pipeline


# =============================================================================
# Timeouts
# =============================================================================

class Timeouts:
    """Timeout values in seconds."""
    HTTP_DEFAULT = 30.0
    LLM_CALL = 120.0
    VALIDATION = 120.0
    RUFF = 30.0
    RUFF_INSTALL = 120.0
    SUBPROCESS = 60.0
    WEBSOCKET = 5.0
    HEALTH_CHECK = 5.0


# =============================================================================
# Service Ports
# =============================================================================

class DefaultPorts:
    """Default service ports."""
    BACKEND = 8000
    VALIDATOR = 8002
    ORCHESTRATOR = 8100
    GENERATOR = 8101
    UI_CONTROLLER = 8102


# =============================================================================
# Ruff Error Codes
# =============================================================================

class RuffErrorCodes:
    """Ruff error codes by category."""
    # Fatal errors that require fix_instructions
    FATAL = {
        "E999",  # SyntaxError
        "F821",  # Undefined name
        "F822",  # Undefined name in __all__
        "F823",  # Local variable referenced before assignment
        "F831",  # Duplicate argument name
    }
    
    # Safe to auto-fix
    SAFE_TO_FIX = {
        "E",     # pycodestyle errors
        "W",     # pycodestyle warnings
        "F401",  # Unused import
        "F403",  # Star import
        "F405",  # Name may be undefined
        "I",     # isort
        "N",     # pep8-naming
        "UP",    # pyupgrade
        "B",     # flake8-bugbear
        "C4",    # flake8-comprehensions
        "PIE",   # flake8-pie
        "SIM",   # flake8-simplify
        "T20",   # flake8-print
        "PT",    # flake8-pytest-style
        "Q",     # flake8-quotes
        "RUF",   # Ruff-specific
    }


# =============================================================================
# MCP Compliance Codes
# =============================================================================

class MCPComplianceCodes:
    """MCP compliance check codes."""
    NO_IMPORT = "MCP_NO_IMPORT"
    NO_INSTANCE = "MCP_NO_INSTANCE"
    NO_TOOLS = "MCP_NO_TOOLS"
    NO_RUN = "MCP_NO_RUN"
    NO_MAIN_GUARD = "MCP_NO_MAIN_GUARD"
    TOOL_NO_DOCSTRING = "MCP_TOOL_NO_DOCSTRING"
    TOOL_NO_RETURN_TYPE = "MCP_TOOL_NO_RETURN_TYPE"
    TOOL_NO_PARAM_TYPE = "MCP_TOOL_NO_PARAM_TYPE"
    TOOL_NAMING = "MCP_TOOL_NAMING"
    SYNC_TOOLS = "MCP_SYNC_TOOLS"
    TOOL_NO_ERROR_HANDLING = "MCP_TOOL_NO_ERROR_HANDLING"
    NO_HTTP_TIMEOUT = "MCP_NO_HTTP_TIMEOUT"


# =============================================================================
# Issue Categories
# =============================================================================

class IssueCategories:
    """Validation issue categories."""
    SYNTAX = "syntax"
    RUNTIME = "runtime"
    IMPORT = "import"
    EXECUTION = "execution"
    REGRESSION = "regression"
    MCP_COMPLIANCE = "mcp_compliance"
    SECURITY = "security"
    INPUT = "input"
    RUFF = "ruff"


# =============================================================================
# Pipeline States (for reference)
# =============================================================================

class PipelineStateNames:
    """Pipeline state names (matches PipelineState enum)."""
    INITIAL = "initial"
    INPUT_RECEIVED = "input_received"
    COLLECTING_TOOLS = "collecting_tools"
    TOOLS_READY = "tools_ready"
    GENERATING_CODE = "generating_code"
    AWAITING_VALIDATION = "awaiting_validation"
    VALIDATING_CODE = "validating_code"
    VALIDATION_RESULT = "validation_result"
    AWAITING_REGEN = "awaiting_regen"
    REGENERATING_CODE = "regenerating_code"
    DONE = "done"
    FAILED_FINAL = "failed_final"


# =============================================================================
# Priority Levels
# =============================================================================

class Priority:
    """Priority levels for fix instructions."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# =============================================================================
# Severity Levels
# =============================================================================

class Severity:
    """Severity levels for validation issues."""
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"

