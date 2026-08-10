# Edited by Dr. Wasim
"""
LLM Validator

Optional advisory LLM validation (non-blocking).

IMPORTANT: LLM feedback is ALWAYS advisory only.
- All issues are severity="suggestion"
- points_deducted=0 (never affects score)
- Never affects approval/rejection
- Never escalated to warning/critical
"""
import os
import json
import logging
from typing import Optional, Tuple, List

from shared.message_types import ValidationIssue, LLMValidationResult

logger = logging.getLogger(__name__)

# Try to import OpenAI
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI SDK not available. LLM validation disabled.")


async def validate_with_llm(
    code: str,
    iteration: int,
    openai_client: Optional[AsyncOpenAI] = None,
    model: Optional[str] = None,
) -> Tuple[Optional[LLMValidationResult], List[ValidationIssue], List[ValidationIssue]]:
    """
    Perform optional LLM validation (advisory only, non-blocking).
    
    LLM findings are treated as:
    - Suggestions or warnings only
    - NEVER produce CRITICAL errors
    - Never cause validation failure
    
    Args:
        code: Python code to validate
        iteration: Current iteration number
        openai_client: OpenAI client (optional)
        model: Model to use
        
    Returns:
        Tuple of (llm_result, warnings, suggestions)
        All issues from LLM are warnings/suggestions, never critical
    """
    if not OPENAI_AVAILABLE or not openai_client:
        logger.debug("LLM validation skipped (not available)")
        return None, [], []
    
    try:
        logger.info("Running LLM validation (advisory only)...")

        model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        logger.info(f"Using OpenAI model: {model}")

        prompt = f"""You are a code quality advisor for MCP (Model Context Protocol) server code.

Analyze the following Python code and provide advisory feedback. Your role is to suggest improvements, NOT to block code.

Code (Iteration {iteration}):
```python
{code}
```

Provide feedback in the following format:
{{
    "reasoning": "Brief summary of code quality",
    "improvements": ["suggestion1", "suggestion2", ...]
}}

IMPORTANT RULES:
- Do NOT mark anything as critical or blocking
- Only provide suggestions and warnings
- Focus on code quality, documentation, best practices
- Do NOT suggest code length changes
- Be constructive and helpful

Return only valid JSON."""

        response = await openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful code quality advisor. Provide constructive, non-blocking feedback."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        content = response.choices[0].message.content
        logger.debug(f"LLM response: {content[:200]}...")
        
        # Parse JSON response
        try:
            # Extract JSON from response (might have markdown code blocks)
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()
            
            data = json.loads(content)
            
            llm_result = LLMValidationResult(
                reasoning=data.get("reasoning", "Code quality analysis completed"),
                improvements=data.get("improvements", [])
            )
            
            # Edited by Dr. Wasim: Convert improvements to suggestions (non-blocking)
            # LLM issues are ALWAYS suggestions, never warnings or critical
            # They must never affect approval or score deduction
            suggestions: List[ValidationIssue] = []
            for improvement in data.get("improvements", []):
                # Force severity="suggestion" and points_deducted=0
                suggestions.append(ValidationIssue(
                    severity="suggestion",  # ALWAYS suggestion, never warning/critical
                    message=improvement,
                    description=improvement,
                    line=None,
                    code="LLM_SUGGESTION",
                    category="code_quality",
                    suggestion=improvement,
                    points_deducted=0  # ALWAYS 0 - never affects score
                ))
            
            logger.info(f"LLM validation complete: {len(suggestions)} suggestions (advisory only)")
            # Return empty warnings list - LLM never produces warnings
            return llm_result, [], suggestions
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            # Return basic result with raw reasoning
            return LLMValidationResult(
                reasoning=content[:500] if content else "LLM analysis completed",
                improvements=[]
            ), [], []
            
    except Exception as e:
        logger.error(f"LLM validation error: {e}")
        # Don't fail validation if LLM fails
        return None, [], []
