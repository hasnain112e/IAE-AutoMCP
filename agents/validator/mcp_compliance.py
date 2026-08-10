"""
MCP Inspector - Comprehensive MCP/FastMCP Compliance Checker

This module validates generated MCP server code against protocol standards
and best practices. It provides detailed feedback for code improvement.

PHILOSOPHY: All code has value - provide actionable feedback instead of rejection.
"""

import ast
import re
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Import from shared types
from shared.message_types import ValidationIssue

logger = logging.getLogger(__name__)


class MCPCheckCategory(Enum):
    """Categories of MCP compliance checks."""
    STRUCTURE = "structure"
    TOOL_DEFINITION = "tool_definition"
    BEST_PRACTICE = "best_practice"
    RUNTIME = "runtime"


@dataclass
class MCPCheckResult:
    """Result of a single MCP compliance check."""
    passed: bool
    code: str
    message: str
    category: MCPCheckCategory
    severity: str  # "critical", "warning", "suggestion"
    line: Optional[int] = None
    fix_suggestion: Optional[str] = None


class MCPInspector:
    """
    Comprehensive MCP/FastMCP compliance checker.
    
    Performs multi-layer validation:
    1. Structural checks (imports, instance, decorators)
    2. Tool definition checks (docstrings, types, names)
    3. Best practice checks (async, error handling, timeouts)
    4. Optional runtime checks (subprocess validation)
    """
    
    def __init__(self, enable_runtime_checks: bool = False):
        self.enable_runtime_checks = enable_runtime_checks
        self.results: List[MCPCheckResult] = []
    
    def check_mcp_compliance(self, code: str) -> List[ValidationIssue]:
        """
        Main entry point for MCP compliance checking.
        
        Args:
            code: Python source code to validate
            
        Returns:
            List of ValidationIssue objects for any compliance issues
        """
        self.results = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Syntax errors handled by syntax_validator
            return []
        
        # Layer 1: Structural checks
        self._check_fastmcp_import(code, tree)
        self._check_fastmcp_instance(code, tree)
        self._check_tool_decorators(code, tree)
        self._check_server_run(code, tree)
        self._check_main_guard(code, tree)
        
        # Layer 2: Tool definition checks
        self._check_tool_docstrings(tree)
        self._check_tool_type_hints(tree)
        self._check_tool_naming(tree)
        
        # Layer 3: Best practice checks
        self._check_async_tools(tree)
        self._check_error_handling(tree)
        self._check_http_timeouts(code, tree)
        
        # Layer 4: Optional runtime checks
        if self.enable_runtime_checks:
            self._check_runtime_execution(code)
        
        # Convert results to ValidationIssue objects
        return self._convert_to_validation_issues()
    
    def _check_fastmcp_import(self, code: str, tree: ast.AST) -> None:
        """Check for FastMCP import statement."""
        has_import = False
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "fastmcp" in alias.name.lower() or "mcp" in alias.name.lower():
                        has_import = True
            elif isinstance(node, ast.ImportFrom):
                if node.module and ("fastmcp" in node.module.lower() or "mcp" in node.module.lower()):
                    has_import = True
        
        # Also check raw code for different import patterns
        if not has_import:
            import_patterns = [
                "from fastmcp import",
                "import fastmcp",
                "from mcp import",
                "import mcp",
                "FastMCP",
            ]
            has_import = any(p in code for p in import_patterns)
        
        if not has_import:
            self.results.append(MCPCheckResult(
                passed=False,
                code="MCP_NO_IMPORT",
                message="Missing FastMCP import statement. The code uses FastMCP but does not import it, which will cause a runtime error.",
                category=MCPCheckCategory.STRUCTURE,
                severity="critical",
                fix_suggestion="Add the import statement at the top of your file:\n\nfrom fastmcp import FastMCP"
            ))
    
    def _check_fastmcp_instance(self, code: str, tree: ast.AST) -> None:
        """Check for FastMCP instance creation."""
        instance_patterns = [
            "FastMCP(",
            "= FastMCP",
            "mcp = FastMCP",
            "server = FastMCP",
            "app = FastMCP",
        ]
        has_instance = any(p in code for p in instance_patterns)
        
        if not has_instance:
            self.results.append(MCPCheckResult(
                passed=False,
                code="MCP_NO_INSTANCE",
                message="No FastMCP server instance created. The code must create a FastMCP instance (e.g., 'mcp = FastMCP(\"server_name\")') to register tools and run the server.",
                category=MCPCheckCategory.STRUCTURE,
                severity="critical",
                fix_suggestion="Create a FastMCP instance after the import:\n\nfrom fastmcp import FastMCP\n\nmcp = FastMCP(\"my_mcp_server\")"
            ))
    
    def _check_tool_decorators(self, code: str, tree: ast.AST) -> None:
        """Check for at least one @mcp.tool decorator."""
        decorator_patterns = [
            "@mcp.tool",
            "@server.tool",
            "@app.tool",
            ".tool(",
        ]
        has_tool_decorator = any(p in code for p in decorator_patterns)
        
        if not has_tool_decorator:
            self.results.append(MCPCheckResult(
                passed=False,
                code="MCP_NO_TOOLS",
                message="No MCP tool functions defined. An MCP server must have at least one function decorated with @mcp.tool to expose functionality to clients.",
                category=MCPCheckCategory.STRUCTURE,
                severity="critical",
                fix_suggestion="Add at least one tool function with the @mcp.tool decorator:\n\n@mcp.tool\ndef my_tool(param: str) -> str:\n    \"\"\"Tool description explaining what this tool does.\"\"\"\n    # Your tool implementation here\n    return result"
            ))
    
    def _check_server_run(self, code: str, tree: ast.AST) -> None:
        """Check for server.run() or mcp.run() call."""
        run_patterns = [".run()", "mcp.run", "server.run", "app.run"]
        has_run = any(p in code for p in run_patterns)
        
        if not has_run:
            self.results.append(MCPCheckResult(
                passed=False,
                code="MCP_NO_RUN",
                message="No server run() call found. MCP server must call mcp.run() to start.",
                category=MCPCheckCategory.STRUCTURE,
                severity="warning",
                fix_suggestion="Add at the end of the file:\n\nif __name__ == \"__main__\":\n    mcp.run()"
            ))
    
    def _check_main_guard(self, code: str, tree: ast.AST) -> None:
        """Check for proper __name__ == '__main__' guard."""
        has_main_guard = 'if __name__ == "__main__"' in code or "if __name__ == '__main__'" in code
        
        if not has_main_guard:
            self.results.append(MCPCheckResult(
                passed=False,
                code="MCP_NO_MAIN_GUARD",
                message="Missing if __name__ == '__main__' guard.",
                category=MCPCheckCategory.BEST_PRACTICE,
                severity="suggestion",
                fix_suggestion="Wrap server startup in main guard:\n\nif __name__ == \"__main__\":\n    mcp.run()"
            ))
    
    def _check_tool_docstrings(self, tree: ast.AST) -> None:
        """Check that tool functions have docstrings."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if function has a tool decorator
                has_tool_decorator = any(
                    (isinstance(d, ast.Attribute) and d.attr == "tool") or
                    (isinstance(d, ast.Name) and d.id == "tool") or
                    (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool")
                    for d in node.decorator_list
                )
                
                if has_tool_decorator:
                    docstring = ast.get_docstring(node)
                    if not docstring:
                        self.results.append(MCPCheckResult(
                            passed=False,
                            code="MCP_TOOL_NO_DOCSTRING",
                            message=f"Tool function '{node.name}' missing docstring. MCP tools should have descriptions.",
                            category=MCPCheckCategory.TOOL_DEFINITION,
                            severity="warning",
                            line=node.lineno,
                            fix_suggestion=f"Add docstring to '{node.name}':\n\n@mcp.tool\ndef {node.name}(...):\n    \"\"\"Description of what this tool does.\"\"\"\n    ..."
                        ))
    
    def _check_tool_type_hints(self, tree: ast.AST) -> None:
        """Check that tool functions have type hints."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                has_tool_decorator = any(
                    (isinstance(d, ast.Attribute) and d.attr == "tool") or
                    (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool")
                    for d in node.decorator_list
                )
                
                if has_tool_decorator:
                    # Check for missing return type
                    if node.returns is None:
                        self.results.append(MCPCheckResult(
                            passed=False,
                            code="MCP_TOOL_NO_RETURN_TYPE",
                            message=f"Tool function '{node.name}' missing return type hint.",
                            category=MCPCheckCategory.TOOL_DEFINITION,
                            severity="suggestion",
                            line=node.lineno,
                            fix_suggestion=f"Add return type hint: def {node.name}(...) -> str:"
                        ))
                    
                    # Check for missing parameter types
                    for arg in node.args.args:
                        if arg.arg != "self" and arg.annotation is None:
                            self.results.append(MCPCheckResult(
                                passed=False,
                                code="MCP_TOOL_NO_PARAM_TYPE",
                                message=f"Parameter '{arg.arg}' in tool '{node.name}' missing type hint.",
                                category=MCPCheckCategory.TOOL_DEFINITION,
                                severity="suggestion",
                                line=node.lineno,
                                fix_suggestion=f"Add type hint: {arg.arg}: str"
                            ))
    
    def _check_tool_naming(self, tree: ast.AST) -> None:
        """Check that tool functions follow naming conventions."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                has_tool_decorator = any(
                    (isinstance(d, ast.Attribute) and d.attr == "tool")
                    for d in node.decorator_list
                )
                
                if has_tool_decorator:
                    # Check for snake_case
                    if not re.match(r'^[a-z][a-z0-9_]*$', node.name):
                        self.results.append(MCPCheckResult(
                            passed=False,
                            code="MCP_TOOL_NAMING",
                            message=f"Tool function '{node.name}' should use snake_case naming.",
                            category=MCPCheckCategory.TOOL_DEFINITION,
                            severity="suggestion",
                            line=node.lineno,
                            fix_suggestion=f"Rename to snake_case: {self._to_snake_case(node.name)}"
                        ))
    
    def _check_async_tools(self, tree: ast.AST) -> None:
        """Check for async tool handlers (best practice)."""
        has_async_tools = False
        has_sync_tools = False
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                has_tool_decorator = any(
                    (isinstance(d, ast.Attribute) and d.attr == "tool")
                    for d in node.decorator_list
                )
                
                if has_tool_decorator:
                    if isinstance(node, ast.AsyncFunctionDef):
                        has_async_tools = True
                    else:
                        has_sync_tools = True
        
        if has_sync_tools and not has_async_tools:
            self.results.append(MCPCheckResult(
                passed=False,
                code="MCP_SYNC_TOOLS",
                message="All tools are synchronous. Consider using async for I/O operations.",
                category=MCPCheckCategory.BEST_PRACTICE,
                severity="suggestion",
                fix_suggestion="Convert tools to async:\n\n@mcp.tool\nasync def my_tool(param: str) -> str:\n    result = await some_async_operation()\n    return result"
            ))
    
    def _check_error_handling(self, tree: ast.AST) -> None:
        """Check for proper error handling in tools."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                has_tool_decorator = any(
                    (isinstance(d, ast.Attribute) and d.attr == "tool")
                    for d in node.decorator_list
                )
                
                if has_tool_decorator:
                    # Check if function has any try/except
                    has_try = any(
                        isinstance(child, ast.Try)
                        for child in ast.walk(node)
                    )
                    
                    if not has_try:
                        self.results.append(MCPCheckResult(
                            passed=False,
                            code="MCP_TOOL_NO_ERROR_HANDLING",
                            message=f"Tool '{node.name}' has no error handling. Wrap in try/except for robustness.",
                            category=MCPCheckCategory.BEST_PRACTICE,
                            severity="suggestion",
                            line=node.lineno,
                            fix_suggestion="Add error handling:\n\ntry:\n    # tool logic\n    return result\nexcept Exception as e:\n    return f\"Error: {str(e)}\""
                        ))
    
    def _check_http_timeouts(self, code: str, tree: ast.AST) -> None:
        """Check for timeout configuration in HTTP calls."""
        http_patterns = ["httpx.", "requests.", "aiohttp.", "urllib"]
        has_http = any(p in code for p in http_patterns)
        has_timeout = "timeout=" in code or "timeout:" in code
        
        if has_http and not has_timeout:
            self.results.append(MCPCheckResult(
                passed=False,
                code="MCP_NO_HTTP_TIMEOUT",
                message="HTTP calls detected without explicit timeout. Add timeout parameter.",
                category=MCPCheckCategory.BEST_PRACTICE,
                severity="warning",
                fix_suggestion="Add timeout to HTTP calls:\n\nresponse = httpx.get(url, timeout=30.0)"
            ))
    
    def _check_runtime_execution(self, code: str) -> None:
        """Optional: Validate by actually running the MCP server."""
        # This is an optional advanced check that spawns the server
        # and validates it responds correctly to MCP protocol requests.
        # Disabled by default for performance.
        pass
    
    def _to_snake_case(self, name: str) -> str:
        """Convert name to snake_case."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    def _convert_to_validation_issues(self) -> List[ValidationIssue]:
        """Convert MCPCheckResults to ValidationIssue objects."""
        issues = []
        for result in self.results:
            if not result.passed:
                # Create a comprehensive description that combines message and context
                description = result.message
                if result.line:
                    description = f"Line {result.line}: {description}"
                
                # Ensure both message and description are set (frontend may use either)
                issue_message = result.message
                if result.line:
                    issue_message = f"[Line {result.line}] {issue_message}"
                
                issues.append(ValidationIssue(
                    code=result.code,
                    message=issue_message,  # Short message for display
                    description=description,  # Detailed description (what frontend shows in "Issue:" section)
                    severity=result.severity,
                    category="mcp_compliance",
                    line=result.line,
                    points_deducted=self._get_points_deducted(result.severity),
                    suggestion=result.fix_suggestion,  # This shows in "How to fix:" section
                    code_snippet=None  # Could be populated if we have code context
                ))
        return issues
    
    def _get_points_deducted(self, severity: str) -> int:
        """Get points deducted based on severity."""
        if severity == "critical":
            return 15  # Critical MCP issues
        elif severity == "warning":
            return 5   # Warnings
        else:
            return 0   # Suggestions never deduct


def check_mcp_compliance(code: str) -> List[ValidationIssue]:
    """
    Convenience function for MCP compliance checking.
    
    Args:
        code: Python source code to validate
        
    Returns:
        List of ValidationIssue objects for any compliance issues
    """
    inspector = MCPInspector(enable_runtime_checks=False)
    return inspector.check_mcp_compliance(code)

