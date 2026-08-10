# Edited by Dr. Wasim
"""
Ruff Integration for Automatic Code Fixes

Runs Ruff in autofix mode on generated code to automatically fix minor issues
without changing business logic.

PHILOSOPHY: No code is worthless - generate fix_instructions for unfixable errors
to enable the Generator to learn and improve.
"""
import subprocess
import tempfile
import os
import sys
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class FixInstruction:
    """Actionable fix instruction for the Generator Agent."""
    error_code: str
    message: str
    line: int
    column: int
    fix_instruction: str
    suggested_code: Optional[str] = None
    context: Optional[str] = None
    priority: str = "high"  # "critical", "high", "medium", "low"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# Ruff error codes that indicate fatal/syntax errors (generate fix_instructions)
FATAL_ERROR_CODES = {
    "E999",  # SyntaxError
    "F821",  # Undefined name
    "F822",  # Undefined name in __all__
    "F823",  # Local variable referenced before assignment
    "F831",  # Duplicate argument name
}

# Error codes that can be auto-corrected with specific fixes
AUTO_CORRECTABLE_ERRORS = {
    "F841": "unused_variable",  # Local variable assigned but never used
    "F401": "unused_import",  # Unused import
    "E501": "line_too_long",  # Line too long
    "E302": "expected_blank_lines",  # Expected 2 blank lines
    "E303": "too_many_blank_lines",  # Too many blank lines
    "E711": "none_comparison",  # comparison to None
    "E712": "true_false_comparison",  # comparison to True/False
    "W291": "trailing_whitespace",  # trailing whitespace
    "W292": "no_newline_at_eof",  # no newline at end of file
    "W293": "blank_line_whitespace",  # blank line contains whitespace
}

# Ruff error codes that are safe to auto-fix (minor issues)
SAFE_TO_FIX_CODES = {
    "E",     # pycodestyle errors (formatting)
    "W",     # pycodestyle warnings (formatting)
    "F401",  # Unused import
    "F403",  # Star import
    "F405",  # Name may be undefined (from star import)
    "I",     # isort (import sorting)
    "N",     # pep8-naming
    "UP",    # pyupgrade
    "B",     # flake8-bugbear
    "C4",    # flake8-comprehensions
    "PIE",   # flake8-pie
    "SIM",   # flake8-simplify
    "T20",   # flake8-print
    "PT",    # flake8-pytest-style
    "Q",     # flake8-quotes
    "RUF",   # Ruff-specific rules
}


def _check_ruff_installed() -> bool:
    """
    Check if Ruff is installed and available in PATH.
    
    Returns:
        True if Ruff is available, False otherwise
    """
    try:
        result = subprocess.run(
            ["ruff", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, TimeoutError):
        return False
    except Exception:
        return False


def _install_ruff() -> bool:
    """
    Attempt to install Ruff using pip.
    
    Returns:
        True if installation succeeded, False otherwise
    """
    # Edited by Dr. Wasim – auto-install Ruff if not found
    try:
        logger.info("[Ruff] Ruff not found. Attempting to install...")
        install_result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "ruff"],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minutes for installation
        )
        
        if install_result.returncode == 0:
            logger.info("[Ruff] Successfully installed Ruff")
            return True
        else:
            error_msg = install_result.stderr or install_result.stdout or "Unknown error"
            logger.warning(f"[Ruff] Failed to install Ruff: {error_msg}")
            return False
    except TimeoutError:
        logger.warning("[Ruff] Installation timeout (exceeded 120s)")
        return False
    except Exception as e:
        logger.warning(f"[Ruff] Error installing Ruff: {e}")
        return False


def _attempt_auto_correction(code: str, errors: List[Dict[str, Any]]) -> tuple:
    """
    Attempt to auto-correct simple errors before Ruff processing.
    
    This handles errors that Ruff might not auto-fix but are simple to correct:
    - Missing common imports
    - Trailing whitespace
    - Missing newlines
    
    Args:
        code: Original code
        errors: List of detected errors
        
    Returns:
        Tuple of (corrected_code, list_of_corrections_made)
    """
    corrections = []
    lines = code.split('\n')
    
    # Common missing imports we can auto-add
    COMMON_IMPORTS = {
        'httpx': 'import httpx',
        'requests': 'import requests',
        'asyncio': 'import asyncio',
        'json': 'import json',
        'os': 'import os',
        'sys': 'import sys',
        'typing': 'from typing import Any, Dict, List, Optional',
        'datetime': 'from datetime import datetime',
        'logging': 'import logging',
        'FastMCP': 'from fastmcp import FastMCP',
        'fastmcp': 'from fastmcp import FastMCP',
    }
    
    imports_to_add = set()
    
    for error in errors:
        error_code = str(error.get("code", ""))
        message = str(error.get("message", ""))
        
        # Handle undefined name errors (F821)
        if error_code == "F821":
            # Extract the undefined name from the message
            # Format: "Undefined name `httpx`"
            if "'" in message:
                name = message.split("'")[1] if len(message.split("'")) > 1 else ""
            elif "`" in message:
                name = message.split("`")[1] if len(message.split("`")) > 1 else ""
            else:
                continue
            
            # Check if we have a common import for this name
            if name in COMMON_IMPORTS:
                imports_to_add.add(COMMON_IMPORTS[name])
                corrections.append({
                    "type": "auto_import",
                    "name": name,
                    "import_statement": COMMON_IMPORTS[name]
                })
        
        # Handle trailing whitespace (W291, W293)
        elif error_code in ["W291", "W293"]:
            line_num = error.get("location", {}).get("row", 0) if isinstance(error.get("location"), dict) else 0
            if 0 < line_num <= len(lines):
                lines[line_num - 1] = lines[line_num - 1].rstrip()
                corrections.append({
                    "type": "trailing_whitespace",
                    "line": line_num
                })
    
    # Add missing imports at the top (after any existing imports)
    if imports_to_add:
        # Find the last import line
        last_import_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                last_import_idx = i + 1
            elif stripped and not stripped.startswith('#') and last_import_idx > 0:
                break
        
        # Insert imports after existing imports
        import_block = "\n".join(sorted(imports_to_add))
        if last_import_idx > 0:
            lines.insert(last_import_idx, import_block)
        else:
            # No existing imports, add at top after docstring/comments
            insert_at = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and not stripped.startswith('"""') and not stripped.startswith("'''"):
                    insert_at = i
                    break
            lines.insert(insert_at, import_block)
    
    # Ensure newline at end of file
    corrected_code = '\n'.join(lines)
    if corrected_code and not corrected_code.endswith('\n'):
        corrected_code += '\n'
        corrections.append({"type": "add_trailing_newline"})
    
    return corrected_code, corrections


def _generate_fix_instruction(error: Dict[str, Any], code_lines: List[str]) -> FixInstruction:
    """
    Generate actionable fix instruction for an error.
    
    Args:
        error: Error dict from Ruff
        code_lines: Source code split into lines
        
    Returns:
        FixInstruction with detailed guidance for the Generator
    """
    error_code = str(error.get("code", "UNKNOWN"))
    message = str(error.get("message", "Unknown error"))
    location = error.get("location", {}) if isinstance(error.get("location"), dict) else {}
    line = location.get("row", 0)
    column = location.get("column", 0)
    
    # Get context (the problematic line)
    context = ""
    if 0 < line <= len(code_lines):
        context = f"Line {line}: {code_lines[line - 1].strip()}"
    
    # Generate fix instructions based on error code
    fix_instruction = ""
    suggested_code = None
    priority = "high"
    
    if error_code == "E999":
        fix_instruction = "Fix the syntax error. Check for missing colons, parentheses, or invalid Python syntax."
        priority = "critical"
    elif error_code == "F821":
        # Undefined name - likely missing import
        name_match = message.split("'")[1] if "'" in message else "unknown"
        fix_instruction = f"Import or define '{name_match}' before using it."
        suggested_code = f"import {name_match}  # or: from module import {name_match}"
        priority = "critical"
    elif error_code == "F822":
        fix_instruction = "Define the name before using it in __all__."
        priority = "critical"
    elif error_code == "F823":
        fix_instruction = "Ensure the variable is assigned before it is referenced."
        priority = "critical"
    elif error_code == "F831":
        fix_instruction = "Remove duplicate argument name from function definition."
        priority = "critical"
    elif error_code == "F841":
        fix_instruction = "Either use the variable or remove it. Consider prefixing with underscore if intentionally unused."
        suggested_code = "_ = unused_value  # or remove the assignment"
        priority = "medium"
    elif error_code.startswith("E"):
        fix_instruction = f"Fix formatting issue: {message}"
        priority = "low"
    elif error_code.startswith("W"):
        fix_instruction = f"Address warning: {message}"
        priority = "low"
    else:
        fix_instruction = f"Address this issue: {message}"
        priority = "medium"
    
    return FixInstruction(
        error_code=error_code,
        message=message,
        line=line,
        column=column,
        fix_instruction=fix_instruction,
        suggested_code=suggested_code,
        context=context,
        priority=priority
    )


def run_ruff_autofix(code: str) -> Dict[str, Any]:
    """
    Run Ruff in autofix mode on code.
    
    Args:
        code: Python code to fix
        
    Returns:
        Dict with:
            - fixed_code: str (fixed code, or original if no fixes)
            - applied_fixes: List[Dict] (list of fixes applied)
            - remaining_warnings: List[Dict] (warnings that couldn't be auto-fixed)
            - has_fatal_errors: bool (if fatal errors detected)
            - fatal_errors: List[Dict] (fatal error details)
            - fix_instructions: List[Dict] (actionable instructions for Generator)
            - regeneration_hints: List[str] (high-level hints for regeneration)
            - success: bool (whether Ruff ran successfully)
            - error: Optional[str] (error message if Ruff failed)
    """
    result = {
        "fixed_code": code,
        "applied_fixes": [],
        "remaining_warnings": [],
        "has_fatal_errors": False,
        "fatal_errors": [],
        "fix_instructions": [],  # NEW: Actionable instructions for Generator
        "regeneration_hints": [],  # NEW: High-level hints
        "auto_corrections": [],  # NEW: Pre-Ruff auto corrections
        "success": False,
        "error": None,
    }
    
    # Split code into lines for context generation
    code_lines = code.split('\n')
    
    # Step 0: Attempt pre-Ruff auto-corrections for common issues
    try:
        # Quick scan for potential issues to pre-correct
        pre_scan_errors = []
        # Check for common undefined names (more comprehensive check)
        common_undefined = {
            'httpx': 'import httpx',
            'requests': 'import requests',
            'asyncio': 'import asyncio',
            'json': 'import json',
            'os': 'import os',
            'sys': 'import sys',
            'FastMCP': 'from fastmcp import FastMCP',
        }
        
        code_lower = code.lower()
        for name, import_stmt in common_undefined.items():
            # Check if name is used but not imported
            if name.lower() in code_lower:
                # Check various import patterns
                has_import = (
                    f"import {name}" in code or
                    f"from {name}" in code or
                    (name == 'FastMCP' and ('from fastmcp import' in code.lower() or 'import fastmcp' in code_lower))
                )
                if not has_import:
                    pre_scan_errors.append({
                        "code": "F821",
                        "message": f"Undefined name `{name}`",
                        "location": {"row": 0, "column": 0}
                    })
        
        # Also check for trailing whitespace and missing newline
        lines = code.split('\n')
        for i, line in enumerate(lines):
            if line.rstrip() != line:
                pre_scan_errors.append({
                    "code": "W291",
                    "message": "trailing whitespace",
                    "location": {"row": i + 1, "column": len(line.rstrip())}
                })
        
        if pre_scan_errors:
            corrected_code, auto_corrections = _attempt_auto_correction(code, pre_scan_errors)
            if auto_corrections:
                code = corrected_code  # Use corrected code
                result["auto_corrections"] = auto_corrections
                result["fixed_code"] = code  # Update fixed_code immediately
                logger.info(f"[Ruff] ✅ Pre-corrected {len(auto_corrections)} issues before Ruff processing: {[c.get('type') for c in auto_corrections]}")
                # Update code_lines after pre-correction
                code_lines = code.split('\n')
    except Exception as e:
        logger.warning(f"[Ruff] Pre-correction failed (non-fatal): {e}", exc_info=True)
    
    # Edited by Dr. Wasim – auto-install Ruff if not found
    # Check if Ruff is installed, install if not
    if not _check_ruff_installed():
        logger.info("[Ruff] Ruff not found. Attempting to install...")
        if not _install_ruff():
            # Installation failed - continue validation without Ruff
            result["error"] = "Ruff not found and installation failed. Install manually with: pip install ruff"
            result["success"] = True  # Don't treat missing Ruff as fatal - continue validation
            logger.warning("[Ruff] Ruff not installed and auto-installation failed. Continuing validation without Ruff.")
            return result
        # Verify installation succeeded
        if not _check_ruff_installed():
            result["error"] = "Ruff installation completed but not found in PATH. Please restart the validator."
            result["success"] = True
            logger.warning("[Ruff] Ruff installation completed but not found in PATH")
            return result
    
    # Never crash validator on Ruff errors
    # IMPORTANT: In Python 3.11+, subprocess.run raises built-in TimeoutError (not subprocess.TimeoutError)
    # If you see "module 'subprocess' has no attribute 'TimeoutError'", restart the agents to clear cached bytecode
    try:
        # Create temporary file with code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp_file:
            tmp_file.write(code)
            tmp_file_path = tmp_file.name
        
        try:
            # Run Ruff check first to see what issues exist
            # Edited by Dr. Wasim – subprocess.run raises built-in TimeoutError in Python 3.11+
            check_result = subprocess.run(
                ["ruff", "check", "--output-format=json", tmp_file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            # Edited by Dr. Wasim – check for syntax errors in stderr
            # Ruff may output syntax errors to stderr instead of stdout
            if check_result.stderr:
                stderr_lower = check_result.stderr.lower()
                if "syntaxerror" in stderr_lower or "syntax error" in stderr_lower or "invalid syntax" in stderr_lower:
                    # Syntax error detected in stderr
                    result["has_fatal_errors"] = True
                    result["fatal_errors"] = [{
                        "code": "E999",
                        "message": check_result.stderr.strip(),
                        "location": {"row": 0},
                    }]
                    result["success"] = True
                    logger.warning(f"[Ruff] Syntax error detected in stderr: {check_result.stderr[:200]}")
                    return result
            
            # Parse Ruff check output
            issues = []
            if check_result.returncode == 0:
                # No issues found - try to run fix anyway to ensure code is formatted
                pass
            elif check_result.stdout:
                try:
                    import json
                    issues = json.loads(check_result.stdout)
                    if not isinstance(issues, list):
                        issues = []
                except json.JSONDecodeError:
                    # Try parsing as text output
                    issues = []
                    for line in check_result.stdout.split('\n'):
                        if line.strip():
                            issues.append({"raw": line})
            
            # Check for fatal errors in parsed issues
            fatal_errors = []
            for issue in issues:
                code_str = str(issue.get("code", ""))
                # Check if it's a fatal error code
                if any(fatal_code in code_str for fatal_code in FATAL_ERROR_CODES):
                    fatal_errors.append(issue)
                # Also check message for syntax error keywords
                message = str(issue.get("message", "")).lower()
                if "syntax" in message or "invalid syntax" in message:
                    fatal_errors.append(issue)
            
            if fatal_errors:
                result["has_fatal_errors"] = True
                result["fatal_errors"] = fatal_errors
                result["success"] = True  # Ruff ran successfully, just found fatal errors
                
                # NEW: Generate fix_instructions for fatal errors
                for error in fatal_errors:
                    fix_inst = _generate_fix_instruction(error, code_lines)
                    result["fix_instructions"].append(fix_inst.to_dict())
                
                # NEW: Add regeneration hints
                result["regeneration_hints"] = [
                    "Ensure all imports are declared at the top of the file",
                    "Define all variables and functions before using them",
                    "Check for typos in function/variable names",
                    "Verify syntax is valid Python (no JavaScript patterns)",
                ]
                
                logger.warning(f"[Ruff] Fatal errors detected: {len(fatal_errors)} issues, generated {len(result['fix_instructions'])} fix instructions")
                return result
            
            # Run Ruff autofix
            fix_result = subprocess.run(
                ["ruff", "check", "--fix", "--output-format=json", tmp_file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            # Read fixed code
            with open(tmp_file_path, 'r', encoding='utf-8') as f:
                fixed_code = f.read()
            
            # Parse fixes applied
            applied_fixes = []
            remaining_warnings = []
            
            # Check if code was actually modified
            if fixed_code != code:
                # Code was modified - run check again to see what's left
                post_check_result = subprocess.run(
                    ["ruff", "check", "--output-format=json", tmp_file_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                
                post_fix_issues = []
                if post_check_result.stdout:
                    try:
                        import json
                        post_fix_issues = json.loads(post_check_result.stdout)
                        if not isinstance(post_fix_issues, list):
                            post_fix_issues = []
                    except json.JSONDecodeError:
                        pass
                
                # Compare original issues with post-fix issues to determine what was fixed
                original_issue_codes = {str(issue.get("code", "")) for issue in issues if isinstance(issue, dict)}
                post_fix_issue_codes = {str(issue.get("code", "")) for issue in post_fix_issues if isinstance(issue, dict)}
                fixed_codes = original_issue_codes - post_fix_issue_codes
                
                for issue in issues:
                    if isinstance(issue, dict):
                        issue_code = str(issue.get("code", ""))
                        if issue_code in fixed_codes:
                            applied_fixes.append({
                                "code": issue_code,
                                "message": issue.get("message", ""),
                                "line": issue.get("location", {}).get("row", 0) if isinstance(issue.get("location"), dict) else 0,
                            })
                        else:
                            remaining_warnings.append({
                                "code": issue_code,
                                "message": issue.get("message", ""),
                                "line": issue.get("location", {}).get("row", 0) if isinstance(issue.get("location"), dict) else 0,
                            })
                
                # If we couldn't parse issues but code changed, assume fixes were applied
                if not applied_fixes and not remaining_warnings and fixed_code != code:
                    applied_fixes.append({"note": "Code was modified by Ruff (formatting/imports)"})
            else:
                # Code unchanged - all original issues remain as warnings
                for issue in issues:
                    if isinstance(issue, dict):
                        remaining_warnings.append({
                            "code": str(issue.get("code", "")),
                            "message": issue.get("message", ""),
                            "line": issue.get("location", {}).get("row", 0) if isinstance(issue.get("location"), dict) else 0,
                        })
            
            result["fixed_code"] = fixed_code
            result["applied_fixes"] = applied_fixes
            result["remaining_warnings"] = remaining_warnings
            result["success"] = True
            
            # NEW: Generate fix_instructions for remaining warnings
            for warning in remaining_warnings:
                fix_inst = _generate_fix_instruction(warning, code_lines)
                result["fix_instructions"].append(fix_inst.to_dict())
            
            if applied_fixes:
                logger.info(f"[Ruff] Applied {len(applied_fixes)} automatic fixes")
            if remaining_warnings:
                logger.info(f"[Ruff] {len(remaining_warnings)} warnings remain (not auto-fixable), generated fix instructions")
            
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass
                
    # Edited by Dr. Wasim – Python 3.11+ uses built-in TimeoutError, NOT subprocess.TimeoutError
    # If you see "module 'subprocess' has no attribute 'TimeoutError'", restart the agents to clear cached .pyc files
    except TimeoutError:  # Built-in exception in Python 3.11+ (NOT subprocess.TimeoutError)
        result["error"] = "Ruff timeout (exceeded 30s)"
        result["success"] = True  # Don't treat timeout as fatal - continue validation
        logger.warning("[Ruff] Timeout while running autofix")
    except FileNotFoundError:
        result["error"] = "Ruff not found. Install with: pip install ruff"
        result["success"] = True  # Don't treat missing Ruff as fatal - continue validation
        logger.warning("[Ruff] Ruff not installed or not in PATH")
    except Exception as e:
        result["error"] = f"Ruff error: {str(e)}"
        result["success"] = True  # Don't treat Ruff errors as fatal - continue validation
        logger.warning(f"[Ruff] Error running autofix: {e}")
    
    # Always return result (never crash)
    return result
