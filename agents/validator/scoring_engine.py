# Edited by Dr. Wasim
"""
Scoring Engine

Weighted scoring system with category-based deductions.
Allows score recovery across iterations.
"""
import logging
from typing import List, Dict, Tuple, Optional, Any

from shared.message_types import ValidationIssue

logger = logging.getLogger(__name__)

# Edited by Dr. Wasim – weighted deductions by category
# Maximum deductions per category (allows score recovery)
MAX_DEDUCTIONS_BY_CATEGORY = {
    "syntax": 40,           # Syntax errors: max 40 points
    "regression": 30,      # Regression criticals: max 30 points
    "import": 50,          # Runtime import failures: max 50 points
    "runtime": 30,         # Runtime errors: max 30 points
    "execution": 25,        # Execution issues: max 25 points
    "mcp_compliance": 20,  # MCP compliance: max 20 points
    "security": 25,        # Security issues: max 25 points
    "default": 15,         # Default for unknown categories: max 15 points
}

# Weighted deductions by issue code
CRITICAL_DEDUCTIONS: Dict[str, int] = {
    # Syntax errors (max 40 total)
    "SYNTAX_ERROR": 15,
    "E999": 15,  # Ruff syntax error code
    
    # Import failures (max 50 total)
    "MISSING_FASTMCP": 50,  # Required import - can force score=0 if truly missing
    "REGRESSION_IMPORT_REMOVED": 30,
    "IMPORT_ERROR": 20,
    
    # Regression issues (max 30 total)
    "REGRESSION_FASTMCP_REMOVED": 20,
    "REGRESSION_TOOL_REMOVED": 15,
    "REGRESSION_SERVER_RUN_REMOVED": 10,
    
    # Runtime errors (max 30 total)
    "MISSING_SERVER_RUN": 15,
    "INVALID_RETURN_TYPE": 10,
    "RUNTIME_ERROR": 15,
    
    # Execution issues (max 25 total)
    "DANGEROUS_EVAL": 15,
    "DANGEROUS_EXEC": 15,
    "SHELL_INJECTION": 20,
}

WARNING_DEDUCTIONS: Dict[str, int] = {
    "MISSING_TIMEOUT": 5,
    "MISSING_RETRY": 5,
    "MISSING_PYDANTIC": 5,
    "MISSING_ERROR_HANDLING": 5,
    "MISSING_AWAIT": 5,
}

# Default deductions if code not found
DEFAULT_CRITICAL_DEDUCTION = 15
DEFAULT_WARNING_DEDUCTION = 5
DEFAULT_SUGGESTION_DEDUCTION = 0  # Suggestions don't deduct by default

# Maximum total deductions
MAX_WARNING_DEDUCTION = 20  # Warnings can deduct max 20 points total
# Suggestions: ALWAYS 0 deduction (advisory only, never affect score)

# Edited by Dr. Wasim – PHILOSOPHY CHANGE: No code is worthless
# Instead of score=0 for fatal errors, we use MIN_SCORE to enable learning gradient
# MIN_SCORE = 10: Worst valid code still has value for learning
MIN_SCORE = 10

# DEPRECATED: Previous approach forced score=0 for fatal errors
# NEW APPROACH: Generate fix_instructions and allow non-zero score
FATAL_ERROR_CODES = {
    "UNPARSEABLE_CODE",      # Code cannot be parsed at all - still gets MIN_SCORE
}

# Category mapping for weighted deductions
CATEGORY_MAPPING = {
    "syntax": "syntax",
    "regression": "regression",
    "import": "import",
    "runtime": "runtime",
    "execution": "execution",
    "mcp_compliance": "mcp_compliance",
    "security": "security",
}


def calculate_score(
    critical_issues: List[ValidationIssue],
    warnings: List[ValidationIssue],
    suggestions: List[ValidationIssue],
    improvement_signals: Optional[Dict[str, Any]] = None
) -> Tuple[int, Dict[str, int]]:
    """
    Calculate quality score with weighted deductions by category.
    
    SCORING RULES (Edited by Dr. Wasim):
    - Start at 100
    - Critical issues: weighted deductions by category (max per category)
    - Warnings: deduct max 5 points each, capped at 20 points total
    - Suggestions: ALWAYS 0 deduction (advisory only, never affect score)
    - Only truly fatal errors force score = 0:
      * Code cannot be parsed at all (UNPARSEABLE_CODE)
      * Required imports missing (MISSING_FASTMCP - if truly missing)
    - All other critical issues use weighted deductions (allows score recovery)
    - Improvement signals adjust scoring:
      * If critical count decreased → reduce penalty
      * If syntax error resolved → remove syntax penalty
      * If only warnings/suggestions remain → allow score >= 70
    - Score clamped to 0-100
    - points_earned + points_deducted = 100
    
    Args:
        critical_issues: List of critical issues
        warnings: List of warnings
        suggestions: List of suggestions (minimal impact)
        improvement_signals: Optional dict with improvement signals from previous iteration
        
    Returns:
        Tuple of (score, breakdown_dict)
    """
    # Edited by Dr. Wasim
    # RULE 1: If all issue lists are empty, score MUST be exactly 100
    if len(critical_issues) == 0 and len(warnings) == 0 and len(suggestions) == 0:
        logger.info("📊 No issues found → score = 100/100 (perfect code)")
        return 100, {
            "critical_issues": 0,
            "fatal_errors": 0,
            "critical_deduction": 0,
            "warnings": 0,
            "warning_deduction": 0,
            "suggestions": 0,
            "suggestion_deduction": 0,
            "has_critical_errors": False,
            "has_fatal_errors": False,
            "score": 100,
            "points_earned": 100,
            "points_deducted": 0,
            "reason_for_deduction": "No issues found"
        }
    
    # Edited by Dr. Wasim – initialize score at 100
    score = 100
    total_critical_deduction = 0
    total_warning_deduction = 0
    total_suggestion_deduction = 0
    
    # Track deductions by category for weighted limits
    category_deductions: Dict[str, int] = {}
    
    # Edited by Dr. Wasim – process improvement signals
    improvement_bonus = 0
    if improvement_signals:
        # If critical count decreased → reduce penalty (bonus points)
        if improvement_signals.get("critical_count_decreased", False):
            previous_count = improvement_signals.get("previous_critical_count", 0)
            current_count = improvement_signals.get("current_critical_count", 0)
            if previous_count > 0:
                # Give bonus proportional to improvement
                improvement_ratio = (previous_count - current_count) / previous_count
                improvement_bonus = int(10 * improvement_ratio)  # Up to 10 bonus points
                logger.info(f"📈 Critical issues decreased ({previous_count}→{current_count}) → +{improvement_bonus} bonus points")
        
        # If syntax error resolved → remove syntax penalty (bonus points)
        if improvement_signals.get("syntax_error_resolved", False):
            # Syntax errors deduct up to 40 points, so give bonus when resolved
            syntax_bonus = 20  # Partial bonus for resolving syntax error
            improvement_bonus += syntax_bonus
            logger.info(f"✅ Syntax error resolved → +{syntax_bonus} bonus points")
    
    # Check for fatal errors (force score=0)
    fatal_errors: List[ValidationIssue] = []
    has_fatal_errors = False
    
    if len(critical_issues) > 0:
        for issue in critical_issues:
            code = (issue.code or "").upper()
            if code in FATAL_ERROR_CODES:
                fatal_errors.append(issue)
                has_fatal_errors = True
                logger.warning(f"🚨 Fatal error detected: {code}")
    
    # Deduct for critical issues (weighted by category)
    if len(critical_issues) > 0:
        for issue in critical_issues:
            # Skip fatal errors (handled separately)
            if issue in fatal_errors:
                continue
                
            category = (issue.category or "default").lower()
            category = CATEGORY_MAPPING.get(category, "default")
            
            # Get deduction amount
            code = (issue.code or "").upper()
            if code in CRITICAL_DEDUCTIONS:
                deduction = CRITICAL_DEDUCTIONS[code]
            elif issue.points_deducted is not None:
                deduction = issue.points_deducted
            else:
                deduction = DEFAULT_CRITICAL_DEDUCTION
            
            # Apply category cap
            max_for_category = MAX_DEDUCTIONS_BY_CATEGORY.get(category, MAX_DEDUCTIONS_BY_CATEGORY["default"])
            current_category_total = category_deductions.get(category, 0)
            
            # Cap deduction to not exceed category maximum
            remaining_category_capacity = max(0, max_for_category - current_category_total)
            deduction = min(deduction, remaining_category_capacity)
            
            if deduction > 0:
                category_deductions[category] = category_deductions.get(category, 0) + deduction
                total_critical_deduction += deduction
                logger.debug(f"Critical '{code}' ({category}): -{deduction} points (category total: {category_deductions[category]}/{max_for_category})")
    
    # Deduct for warnings: max 5 points each, capped at 20 points total
    if len(warnings) > 0:
        for issue in warnings:
            code = (issue.code or "").upper()
            if code in WARNING_DEDUCTIONS:
                deduction = WARNING_DEDUCTIONS[code]
            elif issue.points_deducted is not None:
                deduction = issue.points_deducted
            else:
                deduction = DEFAULT_WARNING_DEDUCTION
            
            # Cap individual warning at 5 points
            deduction = max(0, min(5, deduction))
            total_warning_deduction += deduction
            logger.debug(f"Warning '{code}': -{deduction} points")
        
        # Cap total warning deduction at 20
        if total_warning_deduction > MAX_WARNING_DEDUCTION:
            logger.debug(f"Warning deduction capped: {total_warning_deduction} → {MAX_WARNING_DEDUCTION}")
        total_warning_deduction = min(total_warning_deduction, MAX_WARNING_DEDUCTION)
    
    # Deduct for suggestions: ALWAYS 0 (suggestions are advisory only)
    # STRICT RULE: suggestion severity must NEVER deduct points
    # Deductions are computed ONLY when suggestions list is non-empty (but always 0)
    if len(suggestions) > 0:
        for issue in suggestions:
            code = issue.code or ""
            # FORCE deduction to 0 regardless of points_deducted value
            deduction = 0
            total_suggestion_deduction += deduction
            logger.debug(f"Suggestion '{code}': -{deduction} points (advisory only, no score impact)")
    
    # Suggestions never deduct (always 0) - explicit enforcement
    total_suggestion_deduction = 0
    
    # Edited by Dr. Wasim – calculate base score
    # PHILOSOPHY CHANGE: No longer force score=0 for fatal errors
    # Instead, apply MIN_SCORE to always provide learning gradient
    if has_fatal_errors:
        # Calculate deductions normally, but enforce MIN_SCORE floor
        base_score = 100 - total_critical_deduction - total_warning_deduction - total_suggestion_deduction
        score = max(MIN_SCORE, base_score)  # Never go below MIN_SCORE
        logger.warning(f"🔧 Fatal errors detected → score set to {score} (MIN_SCORE={MIN_SCORE}) with fix_instructions")
    else:
        # Calculate score by subtracting weighted deductions
        base_score = score - total_critical_deduction - total_warning_deduction - total_suggestion_deduction
        
        # Apply improvement bonus
        if improvement_bonus > 0:
            score = min(100, base_score + improvement_bonus)
            logger.info(f"📈 Applied improvement bonus: +{improvement_bonus} points (score: {base_score} → {score})")
        else:
            score = base_score
    
    # Edited by Dr. Wasim – ensure points_earned + points_deducted = 100
    points_deducted = total_critical_deduction + total_warning_deduction + total_suggestion_deduction
    points_earned = 100 - points_deducted
    
    # Edited by Dr. Wasim – if only warnings/suggestions remain → allow score >= 70
    if improvement_signals and improvement_signals.get("only_warnings_suggestions", False):
        if score < 70:
            logger.info(f"📊 Only warnings/suggestions remain → enforcing minimum score of 70 (was {score})")
        score = max(70, score)
    
    # Clamp score to 0-100 (deterministic)
    score = max(0, min(100, score))
    
    # Final safety check: if no issues, score must be 100
    if len(critical_issues) == 0 and len(warnings) == 0 and len(suggestions) == 0:
        if score < 100:
            logger.error(f"🚨 SAFETY VIOLATION: 0 issues but score is {score} → forcing to 100")
        score = 100
        points_earned = 100
        points_deducted = 0
        total_critical_deduction = 0
        total_warning_deduction = 0
        total_suggestion_deduction = 0
    
    # Build breakdown (for transparency)
    breakdown = {
        "critical_issues": len(critical_issues),
        "fatal_errors": len(fatal_errors),
        "critical_deduction": total_critical_deduction,
        "warnings": len(warnings),
        "warning_deduction": total_warning_deduction,
        "suggestions": len(suggestions),
        "suggestion_deduction": total_suggestion_deduction,
        "has_critical_errors": len(critical_issues) > 0,
        "has_fatal_errors": has_fatal_errors,
        "score": score,
        "points_earned": points_earned,
        "points_deducted": points_deducted,
        "category_deductions": category_deductions,
        "improvement_bonus": improvement_bonus,  # Edited by Dr. Wasim
        "improvement_signals": improvement_signals or {},  # Edited by Dr. Wasim
        "reason_for_deduction": _get_deduction_reason(
            total_critical_deduction,
            total_warning_deduction,
            total_suggestion_deduction,
            has_fatal_errors
        )
    }
    
    logger.info(
        f"📊 Score calculated: {score}/100 "
        f"(points_earned={points_earned}, points_deducted={points_deducted}, "
        f"critical={len(critical_issues)} [fatal={len(fatal_errors)}]/-{total_critical_deduction}, "
        f"warnings={len(warnings)}/-{total_warning_deduction}, "
        f"suggestions={len(suggestions)}/-{total_suggestion_deduction}, "
        f"has_fatal={has_fatal_errors})"
    )
    
    return score, breakdown


def _get_deduction_reason(
    critical_deduction: int,
    warning_deduction: int,
    suggestion_deduction: int,
    has_fatal: bool
) -> str:
    """Get human-readable reason for score deduction."""
    if has_fatal:
        return "Fatal errors detected - code cannot run"
    
    if critical_deduction == 0 and warning_deduction == 0 and suggestion_deduction == 0:
        return "No issues found"
    
    reasons = []
    if critical_deduction > 0:
        reasons.append(f"{critical_deduction} points from critical issues")
    if warning_deduction > 0:
        reasons.append(f"{warning_deduction} points from warnings")
    if suggestion_deduction > 0:
        reasons.append(f"{suggestion_deduction} points from suggestions")
    
    return "; ".join(reasons) if reasons else "No issues found"
