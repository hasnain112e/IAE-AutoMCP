# Edited by Dr. Wasim
"""
Syntax Validator

Validates Python syntax using AST parsing.

IMPORTANT: Syntax errors are fixable and should not zero the score.
They deduct up to 40 points but allow score recovery across iterations.
"""
import ast
import logging
from typing import Optional, Tuple

from shared.message_types import ValidationIssue
from .utils import get_code_lines, extract_code_snippet

logger = logging.getLogger(__name__)


def validate_syntax(code: str) -> Tuple[bool, Optional[ValidationIssue]]:
    """
    Validate Python syntax.
    
    IMPORTANT: Syntax errors are fixable and should not zero the score.
    - Emits ONE critical issue with points_deducted <= 40
    - Marks code as non-runnable (cannot execute)
    - Does NOT imply total failure (code can be fixed)
    
    Args:
        code: Python code to validate
        
    Returns:
        Tuple of (is_valid, issue_or_none)
    """
    try:
        ast.parse(code)
        logger.info("✅ Syntax check passed")
        return True, None
    except SyntaxError as e:
        # Edited by Dr. Wasim – syntax errors are fixable and should not zero the score
        logger.error(f"❌ Syntax error: {e.msg} at line {e.lineno}")
        lines = get_code_lines(code)
        # Ensure line number is always valid
        line_num = e.lineno if (e.lineno is not None and e.lineno > 0) else 1
        line_num = min(line_num, len(lines)) if lines else 1
        
        # Safe snippet extraction (never crashes)
        snippet = extract_code_snippet(lines, line_num) if lines else ""
        
        # Clear, actionable error message
        error_msg = f"Syntax error: {e.msg}"
        if e.text:
            error_msg += f" (found: {e.text.strip()})"
        
        # Edited by Dr. Wasim – syntax errors deduct up to 40 points (not fatal)
        # Syntax errors are fixable and should not zero the score
        # This issue marks code as non-runnable but does NOT imply total failure
        points_deducted = min(40, 15)  # Cap at 40, use 15 as base deduction
        
        issue = ValidationIssue(
            severity="critical",
            message=error_msg,
            description=f"Syntax error at line {line_num}: {e.msg}. Code cannot run until fixed. This is a fixable issue that deducts up to 40 points but does not zero the score.",
            line=line_num,
            code="SYNTAX_ERROR",
            category="syntax",
            code_snippet=snippet,
            suggestion=f"Fix syntax error at line {line_num}: {e.msg}. Ensure valid Python syntax (check for missing colons, unmatched brackets, incorrect indentation).",
            points_deducted=points_deducted
        )
        return False, issue
    except Exception as e:
        logger.error(f"Unexpected error during syntax check: {e}")
        # Don't fail on unexpected errors, just log
        return True, None
