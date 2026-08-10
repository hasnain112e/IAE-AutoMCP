# Edited by Dr. Wasim – static analysis normalization
"""
Static Analysis Validator

Performs AST-based static analysis for code quality issues.

All issues are normalized to "warning" or "suggestion" severity BEFORE scoring.
Static analysis NEVER produces "critical" issues.

ENFORCED RULES:
- severity ONLY "warning" or "suggestion" (NEVER "critical")
- points_deducted <= 3
- If severity == "suggestion": points_deducted = 0 (NEVER deduct)
"""
import ast
import logging
import re
from typing import List

from shared.message_types import ValidationIssue
from .utils import parse_code, get_code_lines

logger = logging.getLogger(__name__)


def analyze_code(code: str) -> List[ValidationIssue]:
    """
    Perform static analysis for warnings and suggestions.
    
    IMPORTANT: This module NEVER produces CRITICAL issues.
    All findings are warnings or suggestions (advisory only).
    
    Checks for:
    - Missing timeouts on httpx calls (warning)
    - Missing retry logic (suggestion)
    - Missing error handling (warning, only for external calls)
    - Missing async/await patterns (warning)
    - Missing Pydantic models (suggestion)
    
    Args:
        code: Python code to analyze
        
    Returns:
        List of warning/suggestion ValidationIssues (NEVER critical)
    """
    issues: List[ValidationIssue] = []
    tree = parse_code(code)
    lines = get_code_lines(code)
    
    if not tree:
        return issues
    
    # Check for httpx timeout
    httpx_issues = _check_httpx_timeout(tree, lines)
    issues.extend(httpx_issues)
    
    # Check for retry logic
    retry_issues = _check_retry_logic(tree, lines)
    issues.extend(retry_issues)
    
    # Check for error handling
    error_handling_issues = _check_error_handling(tree, lines)
    issues.extend(error_handling_issues)
    
    # Check for async patterns
    async_issues = _check_async_patterns(tree, lines)
    issues.extend(async_issues)
    
    # Check for Pydantic usage
    pydantic_issues = _check_pydantic_usage(tree, lines)
    issues.extend(pydantic_issues)
    
    # Edited by Dr. Wasim – static analysis normalization
    # Normalize ALL ValidationIssue objects to ensure they meet requirements:
    # - severity ONLY "warning" or "suggestion" (NEVER "critical")
    # - points_deducted <= 3
    # - If severity == "suggestion": points_deducted = 0 (NEVER deduct)
    normalized_issues = []
    for issue in issues:
        # RULE 1: Force normalization - only allow "warning" or "suggestion"
        if issue.severity == "critical":
            # Downgrade any critical issues to warning (should never happen, but defensive)
            logger.warning(f"Static analysis issue '{issue.code}' had critical severity - downgrading to warning")
            issue.severity = "warning"
        elif issue.severity not in ("warning", "suggestion"):
            # Normalize any other severity to warning
            logger.warning(f"Static analysis issue '{issue.code}' had unexpected severity '{issue.severity}' - normalizing to warning")
            issue.severity = "warning"
        
        # RULE 2: Defensive normalization - if severity == "suggestion": points_deducted = 0
        if issue.severity == "suggestion":
            if issue.points_deducted is not None and issue.points_deducted != 0:
                logger.warning(f"Static analysis suggestion '{issue.code}' had points_deducted={issue.points_deducted} - forcing to 0")
            issue.points_deducted = 0
        
        # RULE 3: Ensure points_deducted <= 3 (cap at 3)
        if issue.points_deducted is not None and issue.points_deducted > 3:
            logger.warning(f"Static analysis issue '{issue.code}' had points_deducted={issue.points_deducted} - capping at 3")
            issue.points_deducted = 3
        
        # Ensure points_deducted is non-negative
        if issue.points_deducted is not None and issue.points_deducted < 0:
            logger.warning(f"Static analysis issue '{issue.code}' had negative points_deducted={issue.points_deducted} - setting to 0")
            issue.points_deducted = 0
        
        normalized_issues.append(issue)
    
    return normalized_issues


def _check_httpx_timeout(tree: ast.AST, lines: List[str]) -> List[ValidationIssue]:
    """Check for timeout on httpx calls."""
    issues: List[ValidationIssue] = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check for httpx.AsyncClient() or httpx.Client()
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "httpx":
                    if node.func.attr in ("AsyncClient", "Client"):
                        # Check if timeout is provided
                        has_timeout = False
                        for keyword in node.keywords:
                            if keyword.arg == "timeout":
                                has_timeout = True
                                break
                        
                        if not has_timeout:
                            # Edited by Dr. Wasim – static analysis normalization
                            # severity="warning", points_deducted=3 (max allowed)
                            issues.append(ValidationIssue(
                                severity="warning",
                                message="Missing timeout on httpx client",
                                description="httpx calls should have timeout to prevent hanging",
                                line=node.lineno,
                                code="MISSING_TIMEOUT",
                                category="performance",
                                code_snippet=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                                suggestion="Add timeout parameter: httpx.AsyncClient(timeout=30.0)",
                                points_deducted=3  # Max allowed for warnings
                            ))
    
    return issues


def _check_retry_logic(tree: ast.AST, lines: List[str]) -> List[ValidationIssue]:
    """
    Check for retry logic on HTTP calls.
    
    Conservative check to reduce false positives.
    Only suggests retry if clearly missing and HTTP calls are present.
    """
    issues: List[ValidationIssue] = []
    
    # Check for retry-related imports (tenacity, backoff, etc.)
    has_retry_import = False
    retry_modules = ["tenacity", "backoff", "retry", "retrying"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(rm in alias.name.lower() for rm in retry_modules):
                    has_retry_import = True
                    break
        elif isinstance(node, ast.ImportFrom):
            if node.module and any(rm in node.module.lower() for rm in retry_modules):
                has_retry_import = True
                break
    
    # Check for manual retry patterns (for loops with retry/attempt in name)
    has_manual_retry = False
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            if isinstance(node.target, ast.Name):
                target_lower = node.target.id.lower()
                if "retry" in target_lower or "attempt" in target_lower:
                    has_manual_retry = True
                    break
    
    has_retry = has_retry_import or has_manual_retry
    
    # Only suggest retry if:
    # 1. No retry logic detected
    # 2. HTTP calls are present
    # 3. Multiple HTTP calls (more likely to need retry)
    if not has_retry:
        http_call_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("get", "post", "put", "delete", "patch", "request"):
                        http_call_count += 1
                        if http_call_count >= 2:  # Only suggest if multiple calls
                            # Edited by Dr. Wasim – static analysis normalization
                            # severity="suggestion", points_deducted=0 (suggestions NEVER deduct)
                            issues.append(ValidationIssue(
                                severity="suggestion",  # Downgraded from warning
                                message="Consider adding retry logic for HTTP calls",
                                description="Multiple HTTP calls detected. Retry logic can improve reliability for transient failures.",
                                line=1,
                                code="MISSING_RETRY",
                                category="error_handling",
                                suggestion="Consider adding retry logic (e.g., using tenacity or backoff) for HTTP calls",
                                points_deducted=0  # Suggestions NEVER deduct
                            ))
                            break
    
    return issues


def _check_error_handling(tree: ast.AST, lines: List[str]) -> List[ValidationIssue]:
    """
    Check for error handling in tool functions.
    
    Only suggests error handling for tools that make external calls
    (HTTP, file I/O, etc.) to reduce false positives.
    """
    issues: List[ValidationIssue] = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
            # Check if function has try/except
            has_try_except = False
            for child in ast.walk(node):
                if isinstance(child, ast.Try):
                    has_try_except = True
                    break
            
            # Only flag if function is a tool and makes external calls
            if not has_try_except and len(node.args.args) > 0:
                # Check if it's a tool function
                is_tool = False
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Attribute) and decorator.attr == "tool":
                        is_tool = True
                    elif isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "tool":
                            is_tool = True
                
                if is_tool:
                    # Check if function makes external calls (HTTP, file I/O, etc.)
                    makes_external_calls = False
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            # HTTP calls
                            if isinstance(child.func, ast.Attribute):
                                if child.func.attr in ("get", "post", "put", "delete", "patch", "request"):
                                    makes_external_calls = True
                                    break
                            # File operations
                            if isinstance(child.func, ast.Name):
                                if child.func.id in ("open", "read", "write"):
                                    makes_external_calls = True
                                    break
                    
                    # Only suggest error handling if external calls are made
                    if makes_external_calls:
                        # Edited by Dr. Wasim – static analysis normalization
                        # severity="warning", points_deducted=3 (max allowed)
                        issues.append(ValidationIssue(
                            severity="warning",
                            message=f"Function '{node.name}' could benefit from error handling",
                            description="Tool functions making external calls should have try/except for error handling",
                            line=node.lineno,
                            code="MISSING_ERROR_HANDLING",
                            category="error_handling",
                            code_snippet=lines[node.lineno - 1] if 1 <= node.lineno <= len(lines) else "",
                            suggestion=f"Consider adding try/except block in '{node.name}' for external calls",
                            points_deducted=3  # Max allowed for warnings
                        ))
    
    return issues


def _check_async_patterns(tree: ast.AST, lines: List[str]) -> List[ValidationIssue]:
    """Check for proper async/await patterns."""
    issues: List[ValidationIssue] = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            # Check if async function uses await
            has_await = False
            for child in ast.walk(node):
                if isinstance(child, ast.Await):
                    has_await = True
                    break
            
            # Check if it's a tool function
            is_tool = False
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Attribute) and decorator.attr == "tool":
                    is_tool = True
                elif isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "tool":
                        is_tool = True
            
            # If it's an async tool but doesn't use await, that's fine (might be sync tool)
            # Only flag if it's clearly meant to be async but not using await
            if is_tool and not has_await:
                # Check if it makes HTTP calls that should be async
                has_http_calls = False
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Attribute):
                            if child.func.attr in ("get", "post", "put", "delete", "patch"):
                                has_http_calls = True
                                break
                
                if has_http_calls:
                    # Edited by Dr. Wasim – static analysis normalization
                    # severity="warning", points_deducted=2 (<= 3 allowed)
                    issues.append(ValidationIssue(
                        severity="warning",
                        message=f"Function '{node.name}' should use await for async calls",
                        description="Async functions making HTTP calls should use await",
                        line=node.lineno,
                        code="MISSING_AWAIT",
                        category="code_quality",
                        suggestion=f"Use await for async HTTP calls in '{node.name}'",
                        points_deducted=2  # <= 3 allowed
                    ))
    
    return issues


def _check_pydantic_usage(tree: ast.AST, lines: List[str]) -> List[ValidationIssue]:
    """
    Check for Pydantic model usage in tool parameters.
    
    Only suggests if Pydantic is already imported but not used.
    Downgraded to suggestion (not warning) to be less aggressive.
    """
    issues: List[ValidationIssue] = []
    
    # Check if Pydantic is imported
    has_pydantic = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pydantic":
                    has_pydantic = True
                    break
        elif isinstance(node, ast.ImportFrom):
            if node.module and "pydantic" in node.module:
                has_pydantic = True
                break
    
    # Only suggest if Pydantic is imported but not used in tool parameters
    # This is a nice-to-have, not a requirement
    if has_pydantic:
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
                is_tool = False
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Attribute) and decorator.attr == "tool":
                        is_tool = True
                    elif isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "tool":
                            is_tool = True
                
                # Only suggest for tools with multiple parameters (more likely to benefit)
                if is_tool and len(node.args.args) >= 2:
                    # Check if parameters use Pydantic models
                    uses_pydantic = False
                    for arg in node.args.args:
                        if arg.annotation:
                            # Check annotation for BaseModel or other Pydantic types
                            if isinstance(arg.annotation, ast.Name):
                                # Could be a Pydantic model - assume it is
                                uses_pydantic = True
                                break
                    
                    if not uses_pydantic:
                        # Edited by Dr. Wasim – static analysis normalization
                        # severity="suggestion", points_deducted=0 (suggestions NEVER deduct)
                        issues.append(ValidationIssue(
                            severity="suggestion",  # Downgraded from warning
                            message=f"Function '{node.name}' could use Pydantic models for parameter validation",
                            description="Pydantic models provide better validation and type safety for tool parameters",
                            line=node.lineno,
                            code="MISSING_PYDANTIC",
                            category="code_quality",
                            suggestion=f"Consider using Pydantic BaseModel for '{node.name}' parameters (optional improvement)",
                            points_deducted=0  # Suggestions NEVER deduct
                        ))
    
    return issues
