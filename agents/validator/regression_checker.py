# Edited by Dr. Wasim – regression scoring safety
"""
Regression Checker

Simple regression detection to prevent removal of critical features.

Regression issues are mostly stylistic/convention checks and should be warnings.
Only execution-blocking regressions (runtime failures) should be critical.

SCORING RULES:
- WARNING regressions: deduct max 10 total (not per issue)
- CRITICAL regression: only if ImportError/runtime failure
- If iteration == 1: NO regression scoring at all
- If previous_code is None: return [] (no scoring)
"""
import ast
import logging
from typing import List, Optional

from shared.message_types import ValidationIssue
from .utils import parse_code

logger = logging.getLogger(__name__)


def check_regression(
    current_code: str,
    previous_code: Optional[str],
    iteration: int
) -> List[ValidationIssue]:
    """
    Check for regression (removal of critical features).
    
    Edited by Dr. Wasim:
    - If no previous_code exists: do not emit critical issues
    - Non-execution regressions: emit as warnings
    - Only execution-blocking regressions: emit as critical
    
    CRITICAL regression only for:
    - Removal of required imports (causes ImportError at runtime)
    - Runtime failures (code cannot execute)
    
    WARNING regression for:
    - Removal of FastMCP instance (convention/style)
    - Removal of tool functions (API change, but code still runs)
    - Removal of server run block (convention/style)
    
    NO regression scoring for:
    - Code length differences
    - Structural differences
    - Changed ordering
    - Style changes
    - Improved implementations
    - Formatting-only changes
    
    Args:
        current_code: Current code version
        previous_code: Previous code version (optional)
        iteration: Current iteration number
        
    Returns:
        List of regression issues (warnings for non-blocking, critical for runtime failures)
    """
    issues: List[ValidationIssue] = []
    
    # Edited by Dr. Wasim – regression scoring safety
    # Guard: If previous_code is None → return [] (no scoring)
    if previous_code is None:
        logger.debug(f"Skipping regression check: previous_code is None")
        return []
    
    # Guard: If iteration == 1 → NO regression scoring at all
    if iteration == 1:
        logger.debug(f"Skipping regression check: iteration={iteration} (first iteration, no baseline)")
        return []
    
    logger.info(f"🔍 Running regression check (iteration {iteration})...")
    
    current_tree = parse_code(current_code)
    previous_tree = parse_code(previous_code)
    
    if not current_tree or not previous_tree:
        logger.warning("Cannot perform regression check: AST parsing failed")
        return issues
    
    # Edited by Dr. Wasim – regression scoring safety
    # Check 1: FastMCP instance removal (WARNING - not critical, convention/style issue)
    if _has_fastmcp(previous_tree) and not _has_fastmcp(current_tree):
        issues.append(ValidationIssue(
            severity="warning",  # Convention issue, code still runs
            message="REGRESSION: FastMCP instance removed",
            description="FastMCP instance was present in previous version but is now missing",
            line=1,
            code="REGRESSION_FASTMCP_REMOVED",
            category="regression",
            suggestion="Restore FastMCP instance: mcp = FastMCP('ServerName')",
            points_deducted=5  # Will be capped at 10 total for all warnings
        ))
    
    # Edited by Dr. Wasim – regression scoring safety
    # Check 2: Tool function removal (WARNING - not critical, API change but code still runs)
    previous_tools = _extract_tool_functions(previous_tree)
    current_tools = _extract_tool_functions(current_tree)
    
    removed_tools = set(previous_tools) - set(current_tools)
    if removed_tools:
        for tool_name in removed_tools:
            issues.append(ValidationIssue(
                severity="warning",  # API change, but code still runs
                message=f"REGRESSION: Tool function '{tool_name}' removed",
                description=f"Tool function '{tool_name}' existed in previous version but is now missing",
                line=1,
                code="REGRESSION_TOOL_REMOVED",
                category="regression",
                suggestion=f"Restore tool function '{tool_name}'",
                points_deducted=5  # Will be capped at 10 total for all warnings
            ))
    
    # Edited by Dr. Wasim – regression scoring safety
    # Check 3: Server run block removal (WARNING - not critical, convention issue)
    if _has_server_run(previous_tree) and not _has_server_run(current_tree):
        issues.append(ValidationIssue(
            severity="warning",  # Convention issue, code still runs
            message="REGRESSION: Server entrypoint removed",
            description="Server entrypoint (mcp.run() or uvicorn.run()) was present but is now missing",
            line=1,
            code="REGRESSION_SERVER_RUN_REMOVED",
            category="regression",
            suggestion="Restore server entrypoint",
            points_deducted=5  # Will be capped at 10 total for all warnings
        ))
    
    # Edited by Dr. Wasim – regression scoring safety
    # Check 4: Required imports removal (CRITICAL - only if ImportError/runtime failure)
    # Only check for fastmcp - other imports may be optional or refactored
    critical_imports = ["fastmcp"]  # Only fastmcp is truly required (causes ImportError)
    previous_imports = _extract_imports(previous_tree)
    current_imports = _extract_imports(current_tree)
    
    for imp in critical_imports:
        if _has_import(previous_imports, imp) and not _has_import(current_imports, imp):
            issues.append(ValidationIssue(
                severity="critical",  # CRITICAL only if ImportError/runtime failure
                message=f"REGRESSION: Required import '{imp}' removed",
                description=f"Critical MCP import '{imp}' was present but is now missing. This will cause ImportError at runtime.",
                line=1,
                code="REGRESSION_IMPORT_REMOVED",
                category="regression",
                suggestion=f"Restore import: from fastmcp import FastMCP",
                points_deducted=10  # Critical issues handled separately
            ))
    
    # Edited by Dr. Wasim – regression scoring safety
    # Cap WARNING regression deductions at 10 total (not per issue)
    warning_issues = [issue for issue in issues if issue.severity == "warning"]
    if warning_issues:
        total_warning_deduction = sum(issue.points_deducted or 0 for issue in warning_issues)
        if total_warning_deduction > 10:
            # Distribute the 10 points proportionally among warning issues
            scale_factor = 10.0 / total_warning_deduction
            scaled_deductions = []
            for issue in warning_issues:
                original_deduction = issue.points_deducted or 0
                scaled = max(1, int(original_deduction * scale_factor))
                scaled_deductions.append((issue, scaled))
            
            # Apply scaled deductions
            for issue, scaled in scaled_deductions:
                issue.points_deducted = scaled
            
            # Ensure total is exactly 10 (adjust last issue if needed)
            final_total = sum(issue.points_deducted or 0 for issue in warning_issues)
            if final_total != 10 and warning_issues:
                diff = 10 - final_total
                warning_issues[-1].points_deducted = (warning_issues[-1].points_deducted or 0) + diff
                warning_issues[-1].points_deducted = max(1, warning_issues[-1].points_deducted)  # Ensure at least 1
            
            logger.debug(f"Capped warning regression deductions: {total_warning_deduction} → 10 total")
    
    if issues:
        logger.warning(f"⚠️ Found {len(issues)} regression issue(s) ({len([i for i in issues if i.severity == 'critical'])} critical, {len([i for i in issues if i.severity == 'warning'])} warnings)")
    else:
        logger.info("✅ No regression issues found")
    
    return issues


def _has_fastmcp(tree: ast.AST) -> bool:
    """Check if code has FastMCP instance."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Name) and node.value.func.id == "FastMCP":
                    return True
    return False


def _extract_tool_functions(tree: ast.AST) -> List[str]:
    """Extract list of tool function names."""
    tool_names: List[str] = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
            # Check if has @mcp.tool decorator
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Attribute) and decorator.attr == "tool":
                    tool_names.append(node.name)
                elif isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "tool":
                        tool_names.append(node.name)
    
    return tool_names


def _has_server_run(tree: ast.AST) -> bool:
    """Check if code has server entrypoint."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "run":
                    return True
    return False


def _extract_imports(tree: ast.AST) -> List[str]:
    """Extract all import names."""
    imports: List[str] = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split('.')[0])
    
    return imports


def _has_import(imports: List[str], module: str) -> bool:
    """
    Check if module is in imports list.
    
    Conservative matching to avoid false positives.
    """
    module_lower = module.lower()
    for imp in imports:
        imp_lower = imp.lower()
        # Exact match or module is prefix of import (e.g., "fastmcp" matches "fastmcp.core")
        if imp_lower == module_lower or imp_lower.startswith(module_lower + "."):
            return True
    return False
