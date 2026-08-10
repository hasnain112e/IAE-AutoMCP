# Edited by Dr. Wasim
"""
Validator Agent with real-time telemetry and automatic code improvement.

Emits agent-native telemetry events to UI Controller for live timeline.
"""
import os
import json
import time
import uuid
import asyncio
import logging
from typing import Optional, Dict, Any, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx
from dotenv import load_dotenv

from agents.base_agent import BaseAgent
from shared.a2a_protocol import (
    A2ARequest,
    A2AResponse,
    A2AMessage,
)
from shared.message_types import (
    AgentType,
    ValidationIssue,
    LLMValidationResult,
    ValidationResponse,
)

from .syntax_validator import validate_syntax
from .static_analysis import analyze_code
from .regression_checker import check_regression
from .llm_validator import validate_with_llm
from .scoring_engine import calculate_score
from .ruff_integration import run_ruff_autofix

# Import MCP compliance checker (now exists)
from .mcp_compliance import check_mcp_compliance
MCP_COMPLIANCE_AVAILABLE = True

load_dotenv()

logger = logging.getLogger(__name__)

# Input limits for code validation (Security: prevent DoS attacks)
MAX_CODE_SIZE = 1_000_000  # 1MB maximum code size
MAX_LINES = 10_000  # Maximum lines of code

# Try to import OpenAI
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None


class ValidatorAgent(BaseAgent):
    def __init__(self, host: str = "localhost", port: int = 8002, model: str = None):
        super().__init__(
            agent_type=AgentType.VALIDATOR,
            name="validator",
            host=host,
            port=port,
            timeout=120.0,
        )
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.openai_client: Optional[AsyncOpenAI] = None
        self.telemetry_client: Optional[httpx.AsyncClient] = None
        self.ui_controller_url = "http://127.0.0.1:8102/telemetry"
        self.app = FastAPI(title="Validator Agent")
        # Edited by Dr. Wasim – track previous iteration validation results
        self.previous_validation_results: Dict[str, Dict[str, Any]] = {}  # keyed by context_id
        self._setup_routes()
        self._init_openai()

    def _init_openai(self) -> None:
        if not OPENAI_AVAILABLE or AsyncOpenAI is None:
            logger.info("OpenAI SDK not available, LLM validation disabled")
            return
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.info("No OpenAI API key found, LLM validation disabled")
            return
        try:
            self.openai_client = AsyncOpenAI(api_key=api_key)
            self.telemetry_client = httpx.AsyncClient(timeout=5.0)
            logger.info(f"Using OpenAI model: {self.model}")
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {e}")

    def _setup_routes(self) -> None:
        app = self.app
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.post("/a2a")
        async def handle_a2a_message(request_dict: Dict[str, Any]) -> Dict[str, Any]:
            try:
                logger.info(f"Received A2A message: {request_dict.get('method', 'unknown')}")
                request = A2ARequest.from_dict(request_dict)
                response = await self.handle_message(request)
                logger.info(f"A2A message handled successfully: {request.request_id}")
                return response.to_dict()
            except Exception as e:
                logger.error(f"Error handling message: {e}", exc_info=True)
                return A2AResponse.error(
                    request_id=request_dict.get("id", "unknown"),
                    code=-32000,
                    message=f"Internal server error: {str(e)}",
                ).to_dict()

        @app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "agent": "validator",
                "llm_available": self.openai_client is not None,
            }

    async def handle_message(self, request: A2ARequest) -> A2AResponse:
        try:
            message = A2AMessage.from_dict(request.params.get("message", {}))
            context_id = message.context_id
            req_id = request.request_id

            code = None
            iteration = 1
            previous_code = None
            best_code = None

            for part in message.parts:
                if part.get("kind") == "code" and code is None:
                    code = part.get("code", "")
                elif part.get("kind") == "data":
                    data = part.get("data", {})
                    if "previous_code" in data:
                        previous_code = data["previous_code"]
                    if "best_code" in data:
                        best_code = data["best_code"]
            metadata = message.metadata
            if metadata:
                iteration = metadata.get("iteration", 1)

            if not code:
                return A2AResponse.error(
                    request_id=req_id,
                    code=-32602,
                    message="No code provided in message",
                )

            result = await self.validate_code(
                code=code,
                iteration=iteration,
                use_llm=True,
                previous_code=previous_code,
                best_code=best_code,
                req_id=req_id,
                context_id=context_id,
            )

            # Edited by Dr. Wasim – fix serialization: return validation result dict directly
            # The orchestrator expects response.result to be the ValidationResponse dict
            # A2AProtocol.parse_validation_response will extract it correctly
            return A2AResponse.success(
                request_id=req_id,
                result=result.dict()  # Return ValidationResponse dict directly
            )
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            return A2AResponse.error(
                request_id=request.request_id,
                code=-32000,
                message=f"Internal server error: {str(e)}",
            )

    async def validate_code(
        self,
        code: str,
        iteration: int = 1,
        use_llm: bool = True,
        previous_code: Optional[str] = None,
        best_code: Optional[str] = None,
        req_id: Optional[str] = None,
        context_id: Optional[str] = None,
    ) -> ValidationResponse:
        """
        Validate code with STRICT validation precedence.
        
        PHASE 0: INPUT SANITIZATION
        - Check code size and line count limits
        
        PHASE 1: EXECUTION VIABILITY CHECK (binary)
        - If ANY blocking error exists → provide fix_instructions (non-zero score)
        - Pass → continue to Phase 2
        
        PHASE 2: QUALITY SCORING (only if Phase 1 passed)
        - Assign score (10–100) - never 0 to allow learning
        - Populate warnings (non-blocking issues)
        """
        
        # ========================================================================
        # INPUT SANITIZATION (Security: prevent DoS attacks)
        # ========================================================================
        if len(code) > MAX_CODE_SIZE:
            logger.warning(f"[Validator] Code exceeds size limit: {len(code)} > {MAX_CODE_SIZE}")
            return ValidationResponse(
                approved=False,
                quality_score=0,
                iteration=iteration,
                errors=[ValidationIssue(
                    severity="critical",
                    message=f"Code size {len(code)} bytes exceeds maximum allowed {MAX_CODE_SIZE} bytes",
                    code="INPUT_TOO_LARGE",
                    category="input",
                )],
                warnings=[],
                feedback=f"Code exceeds maximum size limit ({MAX_CODE_SIZE} bytes). Please reduce code size.",
                metadata={"status": "rejected", "blocking_error": True, "gate_triggered": "input_sanitization"},
            )
        
        line_count = code.count('\n') + 1
        if line_count > MAX_LINES:
            logger.warning(f"[Validator] Code exceeds line limit: {line_count} > {MAX_LINES}")
            return ValidationResponse(
                approved=False,
                quality_score=0,
                iteration=iteration,
                errors=[ValidationIssue(
                    severity="critical",
                    message=f"Code has {line_count} lines, exceeds maximum allowed {MAX_LINES} lines",
                    code="INPUT_TOO_MANY_LINES",
                    category="input",
                )],
                warnings=[],
                feedback=f"Code exceeds maximum line count ({MAX_LINES} lines). Please reduce code length.",
                metadata={"status": "rejected", "blocking_error": True, "gate_triggered": "input_sanitization"},
            )
        
        # ========================================================================
        # PHASE 0: RUFF AUTOFIX (Automatic Code Improvement)
        # ========================================================================
        # Edited by Dr. Wasim – Ruff failures (not found, timeout, errors) should NOT block validation
        # Only fatal syntax/runtime errors detected by Ruff should cause rejection
        original_code = code
        ruff_result = run_ruff_autofix(code)
        
        # Check for fatal errors from Ruff (syntax/runtime errors that cannot be auto-fixed)
        # NEW PHILOSOPHY: Don't reject with score=0, provide fix_instructions instead
        if ruff_result.get("fatal_errors", []):
            fatal_errors = ruff_result.get("fatal_errors", [])
            fix_instructions = ruff_result.get("fix_instructions", [])
            regeneration_hints = ruff_result.get("regeneration_hints", [])
            
            logger.warning(f"[Validator] Ruff detected {len(fatal_errors)} fatal errors → providing fix_instructions (not score=0)")
            
            fatal_issues = []
            for err in fatal_errors:
                error_code = err.get("code", "RUFF_FATAL")
                error_message = err.get("message", "Unknown error")
                error_line = err.get("location", {}).get("row", 0) if isinstance(err.get("location"), dict) else 0
                
                # Create comprehensive description
                description = f"Ruff detected a fatal error ({error_code}): {error_message}"
                if error_line > 0:
                    description = f"Line {error_line}: {description}"
                description += ". This error prevents the code from running and must be fixed."
                
                # Create clear message
                message = f"Fatal error ({error_code}): {error_message}"
                if error_line > 0:
                    message = f"[Line {error_line}] {message}"
                
                fatal_issues.append(ValidationIssue(
                    severity="critical",
                    message=message,
                    description=description,  # Detailed description for UI display
                    line=error_line,
                    code=error_code,
                    category="ruff",
                    suggestion=f"Fix the {error_code} error. Review the fix_instructions in metadata for specific guidance."
                ))
            
            # Calculate non-zero score based on severity
            # MIN_SCORE = 10 (worst valid code still has learning value)
            base_score = max(10, 100 - (len(fatal_errors) * 20))
            
            return ValidationResponse(
                approved=False,
                quality_score=base_score,  # NOT 0 - allows learning gradient
                iteration=iteration,
                errors=fatal_issues,
                warnings=[],
                llm_validation=None,
                feedback=f"Ruff detected {len(fatal_errors)} fatal error(s). Review fix_instructions to improve code.",
                metadata={
                    "status": "needs_fixes",
                    "blocking_error": True,
                    "gate_triggered": "ruff_fatal_errors",
                    "ruff_result": ruff_result,
                    "fix_instructions": fix_instructions,  # NEW: Actionable instructions
                    "regeneration_hints": regeneration_hints,  # NEW: High-level hints
                },
            )
        
        # Use fixed code if Ruff made changes
        code = ruff_result.get("fixed_code", code)
        applied_fixes = ruff_result.get("applied_fixes", [])
        remaining_warnings = ruff_result.get("remaining_warnings", [])
        
        # ========================================================================
        # PHASE 1: EXECUTION VIABILITY CHECK (HARD GATE)
        # ========================================================================
        # Syntax validation (first gate)
        is_valid, syntax_issue = validate_syntax(code)
        if not is_valid:
            # NEW PHILOSOPHY: Don't use score=0, use MIN_SCORE instead
            from .scoring_engine import MIN_SCORE
            logger.warning(f"[Validator] Critical error detected (syntax) → providing fix_instructions with score={MIN_SCORE}")
            issues = [syntax_issue] if syntax_issue else []
            
            # Generate fix instructions for syntax error
            fix_instructions = []
            if syntax_issue:
                fix_instructions.append({
                    "error_code": "SYNTAX_ERROR",
                    "message": syntax_issue.message,
                    "line": syntax_issue.line or 0,
                    "column": 0,
                    "fix_instruction": "Fix the syntax error. Check for missing colons, parentheses, brackets, or invalid Python syntax.",
                    "suggested_code": None,
                    "context": f"Line {syntax_issue.line}: Syntax error detected",
                    "priority": "critical"
                })
            
            return ValidationResponse(
                approved=False,
                quality_score=MIN_SCORE,  # NOT 0 - allows learning gradient
                iteration=iteration,
                errors=issues,
                warnings=[],
                llm_validation=LLMValidationResult(
                    reasoning="Syntax error detected. Code will not run.",
                    improvements=["Fix syntax errors before validation"],
                ),
                feedback=f"Syntax error detected. Review fix_instructions to correct the issue. Score: {MIN_SCORE}/100 (not 0 to enable learning).",
                metadata={
                    "syntax_gate_failed": True,
                    "status": "needs_fixes",
                    "blocking_error": True,
                    "gate_triggered": "syntax_validation",
                    "fixed_code": code if code != original_code else None,
                    "applied_fixes": applied_fixes,
                    "ruff_result": ruff_result,
                    "fix_instructions": fix_instructions,
                    "regeneration_hints": [
                        "Check for missing colons after function/class definitions",
                        "Ensure all parentheses, brackets, and braces are matched",
                        "Verify proper indentation (4 spaces per level)",
                        "Check for typos in keywords (def, class, if, etc.)"
                    ],
                },
            )

        # ========================================================================
        # PHASE 2: QUALITY SCORING (only if Phase 1 passed)
        # ========================================================================
        critical_issues: List[ValidationIssue] = []
        warnings: List[ValidationIssue] = []
        suggestions: List[ValidationIssue] = []

        # Static analysis
        static_issues = analyze_code(code)
        for issue in static_issues:
            if issue.severity == "critical" or issue.severity == "error":
                critical_issues.append(issue)
            elif issue.severity == "warning":
                warnings.append(issue)
            else:
                suggestions.append(issue)

        # MCP compliance (if available)
        if MCP_COMPLIANCE_AVAILABLE:
            mcp_issues = check_mcp_compliance(code)
            for issue in mcp_issues:
                if issue.severity == "critical" or issue.severity == "error":
                    critical_issues.append(issue)
                elif issue.severity == "warning":
                    warnings.append(issue)
                else:
                    suggestions.append(issue)

        # Regression checking (only if previous code exists)
        if iteration > 1 and (previous_code or best_code):
            baseline_code = best_code if best_code else previous_code
            regression_issues = check_regression(code, baseline_code, iteration)
            for issue in regression_issues:
                if issue.severity == "critical":
                    critical_issues.append(issue)
                elif issue.severity == "warning":
                    warnings.append(issue)
                else:
                    suggestions.append(issue)

        # LLM validation (advisory only, never affects approval)
        llm_result = None
        if use_llm and self.openai_client:
            try:
                # Edited by Dr. Wasim – fix LLM validation call to include iteration and handle tuple return
                llm_result, llm_warnings, llm_suggestions = await validate_with_llm(
                    code=code,
                    iteration=iteration,
                    openai_client=self.openai_client,
                    model=self.model,
                )
                # LLM issues are always suggestions (advisory only)
                for issue in llm_suggestions:
                    suggestions.append(issue)
                for issue in llm_warnings:
                    warnings.append(issue)
            except Exception as e:
                logger.warning(f"LLM validation failed: {e}")

        # ========================================================================
        # Edited by Dr. Wasim: TRACK PREVIOUS ITERATION & CALCULATE IMPROVEMENT SIGNALS
        # ========================================================================
        # Get previous validation results for this context
        previous_result = self.previous_validation_results.get(context_id or "", {}) if context_id else {}
        previous_critical_count = previous_result.get("critical_count", 0)
        previous_has_syntax_error = previous_result.get("has_syntax_error", False)
        previous_score = previous_result.get("score", 0)
        
        # Calculate improvement signals
        current_critical_count = len(critical_issues)
        has_syntax_error = any(issue.code == "SYNTAX_ERROR" or issue.category == "syntax" for issue in critical_issues)
        critical_count_decreased = current_critical_count < previous_critical_count
        syntax_error_resolved = previous_has_syntax_error and not has_syntax_error
        only_warnings_suggestions = len(critical_issues) == 0 and (len(warnings) > 0 or len(suggestions) > 0)
        
        improvement_signals = {
            "critical_count_decreased": critical_count_decreased,
            "syntax_error_resolved": syntax_error_resolved,
            "only_warnings_suggestions": only_warnings_suggestions,
            "previous_critical_count": previous_critical_count,
            "current_critical_count": current_critical_count,
            "previous_has_syntax_error": previous_has_syntax_error,
            "current_has_syntax_error": has_syntax_error,
        }
        
        logger.info(
            f"[Validator] Improvement signals: "
            f"critical_decreased={critical_count_decreased} ({previous_critical_count}→{current_critical_count}), "
            f"syntax_resolved={syntax_error_resolved}, "
            f"only_warnings_suggestions={only_warnings_suggestions}"
        )
        
        # ========================================================================
        # APPROVAL DECISION: ANY CRITICAL ERROR = FAIL (approved=False)
        # ========================================================================
        # STRICT RULE: If there are ANY critical issues, the code MUST be rejected.
        # Critical errors indicate the code will not work properly or violates
        # essential requirements (syntax, MCP compliance, runtime errors, etc.)
        
        # Count all critical issues (all categories)
        blocking_errors: List[ValidationIssue] = critical_issues
        
        # Approval decision: NO critical errors allowed
        # If critical_issues > 0 → approved = False (ALWAYS)
        # If critical_issues = 0 → approved = True (only warnings/suggestions)
        approved = len(critical_issues) == 0
        
        logger.info(
            f"[Validator] Approval decision: "
            f"critical_issues={len(critical_issues)}, "
            f"approved={approved} "
            f"(RULE: ANY critical error → FAIL)"
        )
        
        # Initialize score_breakdown
        score_breakdown: Dict[str, Any] = {}
        
        # ALWAYS calculate score from scoring_engine (reflects actual code quality)
        # Score calculation is INDEPENDENT of approval status
        quality_score, score_breakdown = calculate_score(
            critical_issues=critical_issues,
            warnings=warnings,
            suggestions=suggestions,
            improvement_signals=improvement_signals,
        )
        
        # Determine status based on approval
        if not approved:
            # Critical errors exist → FAIL
            status = "needs_fixes"
            blocking_reason = critical_issues[0].message if critical_issues else "Critical errors detected"
            logger.warning(
                f"[Validator] FAILED validation: "
                f"critical_errors={len(critical_issues)}, "
                f"score={quality_score}/100 (calculated normally), "
                f"approved=False, "
                f"reason: {blocking_reason}"
            )
        else:
            # No critical errors → can be approved (status depends on score)
            status = "validated"
            
            # Edited by Dr. Wasim – final score guard
            # HARD GUARD: If approved with zero issues, force score=100 and status="validated"
            guard_triggered = False
            if approved and len(critical_issues) == 0 and len(warnings) == 0 and len(suggestions) == 0:
                if quality_score != 100:
                    logger.warning(f"BUG GUARD: score corrected to 100 due to zero issues (was {quality_score})")
                quality_score = 100
                status = "validated"
                score_breakdown["score"] = 100
                score_breakdown["reason_for_deduction"] = "Perfect code"
                guard_triggered = True
            
            # Edited by Dr. Wasim – apply improvement-based score adjustments
            # If only warnings/suggestions remain → allow score >= 70
            if only_warnings_suggestions:
                quality_score = max(70, quality_score)
                logger.info(f"[Validator] Only warnings/suggestions remain → enforcing minimum score of 70 (was {quality_score})")
            
            # If syntax error resolved → remove syntax penalty (already handled by scoring_engine via improvement_signals)
            if syntax_error_resolved:
                logger.info(f"[Validator] Syntax error resolved → syntax penalty removed")
            
            # If critical count decreased → reduce penalty (already handled by scoring_engine via improvement_signals)
            if critical_count_decreased:
                logger.info(f"[Validator] Critical issues decreased ({previous_critical_count}→{current_critical_count}) → penalty reduced")
            
            # Determine status based on score and issue counts (skip if guard was triggered)
            if not guard_triggered:
                if len(suggestions) > 0 and len(warnings) == 0 and len(critical_issues) == 0:
                    quality_score = max(80, quality_score)
                    status = "approved_with_suggestions"
                elif len(warnings) > 0 or len(applied_fixes) > 0 or len(remaining_warnings) > 0:
                    quality_score = max(80, min(90, quality_score))
                    status = "validated_with_warnings"
                else:
                    quality_score = max(90, quality_score)
                    status = "validated"

        # Build feedback message
        feedback_lines = []
        
        if applied_fixes:
            feedback_lines.append(f"✅ Ruff automatically fixed {len(applied_fixes)} issue(s)")
        
        if critical_issues:
            feedback_lines.append(f"Validation Failed ({len(critical_issues)} Critical Issue{'s' if len(critical_issues) != 1 else ''})")
            for error in critical_issues[:5]:
                line_info = f" (line {error.line})" if error.line else ""
                feedback_lines.append(f"- {error.message}{line_info}")
        else:
            feedback_lines.append("Validation Passed")
        
        if warnings:
            feedback_lines.append(f"Warnings ({len(warnings)}):")
            for warning in warnings[:5]:
                feedback_lines.append(f"- {warning.message}")
        
        if suggestions:
            feedback_lines.append(f"Suggestions ({len(suggestions)}):")
            for suggestion in suggestions[:5]:
                feedback_lines.append(f"- {suggestion.message}")
        
        feedback_text = "\n".join(feedback_lines)
        
        # Edited by Dr. Wasim: Final safety check before returning
        # Ensure score is never 0 when there are no blocking errors
        if approved and quality_score == 0:
            logger.error(f"🚨 BUG: Approved but score is 0! Forcing to 80 (critical_issues={len(critical_issues)}, warnings={len(warnings)}, suggestions={len(suggestions)})")
            quality_score = 80
            score_breakdown["score"] = 80
        
        logger.info(f"[Validator] Validation complete: status={status}, approved={approved}, score={quality_score}, critical_errors={len(critical_issues)}, warnings={len(warnings)}, suggestions={len(suggestions)}, blocking_errors={len(blocking_errors)}")
        
        # Edited by Dr. Wasim – store current validation results for next iteration comparison
        if context_id:
            self.previous_validation_results[context_id] = {
                "critical_count": len(critical_issues),
                "has_syntax_error": has_syntax_error,
                "score": quality_score,
                "iteration": iteration,
            }
        
        return ValidationResponse(
            approved=approved,
            quality_score=quality_score,
            iteration=iteration,
            errors=critical_issues,
            warnings=warnings,
            suggestions=suggestions,  # Added by Dr. Wasim
            llm_validation=llm_result,
            feedback=feedback_text,
            metadata={
                "status": status,
                "blocking_error": not approved,
                "severity_counts": {
                    "critical": len(critical_issues),
                    "warning": len(warnings),
                    "suggestion": len(suggestions),
                },
                "fixed_code": code if code != original_code else None,
                "applied_fixes": applied_fixes,
                "remaining_warnings": remaining_warnings,
                "ruff_result": ruff_result,
                "scoring_details": score_breakdown,
                "improvement_signals": improvement_signals,  # Edited by Dr. Wasim
            },
        )

    async def run(self):
        """Run the validator agent server"""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def stop(self):
        """Stop the validator agent"""
        if self.telemetry_client:
            await self.telemetry_client.aclose()


if __name__ == "__main__":
    import asyncio
    agent = ValidatorAgent()
    asyncio.run(agent.run())
