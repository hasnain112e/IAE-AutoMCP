# Edited by Dr. Wasim
"""
Validator Utilities

Helper functions for line number resolution and code parsing.
"""
import ast
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def resolve_line_number(
    code_lines: List[str],
    snippet: Optional[str] = None,
    suggested_line: Optional[int] = None,
) -> int:
    """
    Lightweight line number resolution.
    
    NEVER uses fuzzy matching or multi-line heuristics.
    Strategy:
    1. If snippet matches exact line → use that line
    2. If LLM provides line number → trust it (if valid)
    3. Else → default to 1
    
    Args:
        code_lines: List of code lines (1-indexed)
        snippet: Code snippet from LLM (optional)
        suggested_line: Suggested line number from LLM (optional)
        
    Returns:
        1-indexed line number (always valid, clamped to 1..len(code_lines))
    """
    if not code_lines:
        logger.debug("Empty code_lines, defaulting to line 1")
        return 1
    
    max_line = len(code_lines)
    
    # Strategy 1: Exact snippet match (single line only, no fuzzy matching)
    if snippet:
        snippet_clean = snippet.strip()
        if snippet_clean:  # Only if snippet is non-empty
            for i, line in enumerate(code_lines, 1):
                line_clean = line.strip()
                # Exact match only (no substring matching to avoid false positives)
                if snippet_clean == line_clean:
                    logger.debug(f"Found exact snippet match at line {i}")
                    return i
    
    # Strategy 2: Trust suggested line if valid (clamp to valid range)
    if suggested_line is not None:
        clamped_line = max(1, min(suggested_line, max_line))
        if clamped_line != suggested_line:
            logger.debug(f"Clamped suggested line {suggested_line} to valid range: {clamped_line}")
        else:
            logger.debug(f"Using suggested line {suggested_line}")
        return clamped_line
    
    # Strategy 3: Default to line 1 (safe fallback)
    logger.debug("No snippet or valid suggestion, defaulting to line 1")
    return 1


def parse_code(code: str) -> Optional[ast.AST]:
    """
    Parse Python code into AST.
    
    Args:
        code: Python code string
        
    Returns:
        AST node or None if parsing fails
    """
    try:
        return ast.parse(code)
    except SyntaxError as e:
        logger.error(f"Syntax error: {e.msg} at line {e.lineno}")
        return None
    except Exception as e:
        logger.error(f"AST parsing error: {e}")
        return None


def get_code_lines(code: str) -> List[str]:
    """
    Split code into lines.
    
    Args:
        code: Code string
        
    Returns:
        List of code lines
    """
    return code.split('\n')


def extract_code_snippet(code_lines: List[str], line_num: int, context: int = 2) -> str:
    """
    Extract code snippet around a line number.
    
    Safe extraction that never crashes, always returns valid snippet.
    
    Args:
        code_lines: List of code lines
        line_num: Line number (1-indexed)
        context: Number of lines before/after to include
        
    Returns:
        Code snippet string (empty if invalid input)
    """
    if not code_lines:
        return ""
    
    # Clamp line_num to valid range
    line_num = max(1, min(line_num, len(code_lines)))
    
    # Calculate safe bounds
    start = max(0, line_num - context - 1)
    end = min(len(code_lines), line_num + context)
    
    # Ensure start <= end
    if start >= end:
        return code_lines[line_num - 1] if line_num <= len(code_lines) else ""
    
    return '\n'.join(code_lines[start:end])
