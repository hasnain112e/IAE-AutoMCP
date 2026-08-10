"""
MCP Code Generation Endpoint
Integrates with Creator Agent for code generation
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
import json
import asyncio
import sys
import logging
from pathlib import Path

# Add mcp-generator to path
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-generator"))

router = APIRouter()
logger = logging.getLogger(__name__)

class GenerateCodeRequest(BaseModel):
    tools: List[Dict[str, Any]]
    iteration: int = 1
    use_validator: bool = True
    max_validation_iterations: int = 999  # No practical limit - user controls iterations manually

class GenerateCodeResponse(BaseModel):
    success: bool
    code: Optional[str] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
    validation_feedback: Optional[Dict[str, Any]] = None  # Validation feedback with errors, warnings, suggestions

def _is_api_key_or_quota_error(exception: Exception) -> Tuple[bool, Optional[str]]:
    """
    Detect if an exception is related to API key or quota issues.
    
    Returns:
        Tuple of (is_api_error, user_friendly_message)
    """
    error_str = str(exception).lower()
    error_type = type(exception).__name__.lower()
    
    # Check for API key/quota related keywords
    api_key_keywords = [
        "api key", "apikey", "api_key",
        "authentication", "unauthorized", "auth",
        "invalid key", "invalid_key",
        "key not found", "key_not_found",
        "missing key", "missing_key"
    ]
    
    quota_keywords = [
        "quota", "quota exceeded", "quota_exceeded",
        "rate limit", "rate_limit", "ratelimit",
        "exceeded", "exhausted", "limit reached",
        "429", "too many requests", "too_many_requests",
        "403", "forbidden"
    ]
    
    # Check for quota errors
    for keyword in quota_keywords:
        if keyword in error_str or keyword in error_type:
            return True, (
                f"Gemini API quota exhausted or rate limit exceeded. "
                f"Error: {str(exception)}. "
                f"Please check your API key limits or try again later. "
                f"Falling back to deterministic code generation."
            )
    
    # Check for API key errors
    for keyword in api_key_keywords:
        if keyword in error_str or keyword in error_type:
            return True, (
                f"Gemini API key issue detected. "
                f"Error: {str(exception)}. "
                f"Please check your GOOGLE_API_KEY or GEMINI_API_KEY environment variable. "
                f"Falling back to deterministic code generation."
            )
    
    return False, None

def _format_validation_feedback(feedback: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format validation feedback to include detailed information with line numbers and corrections.
    
    Args:
        feedback: Raw validation feedback from validator
        
    Returns:
        Formatted feedback with errors, warnings, suggestions with line numbers and corrections
    """
    formatted = {
        "approved": feedback.get("approved", False),
        "quality_score": feedback.get("quality_score", 0),
        "iteration": feedback.get("iteration", 1),
        "errors": [],
        "warnings": [],
        "suggestions": [],
        "summary": ""
    }
    
    # Format errors with line numbers and suggestions
    for error in feedback.get("errors", []):
        formatted_error = {
            "severity": error.get("severity", "error"),
            "category": error.get("category", "unknown"),
            "line": error.get("line"),
            "description": error.get("description", ""),
            "suggestion": error.get("suggestion") or error.get("fix", ""),
            "code_snippet": error.get("code_snippet", "")
        }
        formatted["errors"].append(formatted_error)
    
    # Format warnings
    for warning in feedback.get("warnings", []):
        formatted_warning = {
            "severity": warning.get("severity", "warning"),
            "category": warning.get("category", "unknown"),
            "line": warning.get("line"),
            "description": warning.get("description", ""),
            "suggestion": warning.get("suggestion") or warning.get("fix", ""),
            "code_snippet": warning.get("code_snippet", "")
        }
        formatted["warnings"].append(formatted_warning)
    
    # Format suggestions
    for suggestion in feedback.get("suggestions", []):
        formatted_suggestion = {
            "severity": "suggestion",
            "category": suggestion.get("category", "improvement"),
            "line": suggestion.get("line"),
            "description": suggestion.get("description", ""),
            "suggestion": suggestion.get("suggestion") or suggestion.get("fix", ""),
            "code_snippet": suggestion.get("code_snippet", "")
        }
        formatted["suggestions"].append(formatted_suggestion)
    
    # Generate summary
    error_count = len(formatted["errors"])
    warning_count = len(formatted["warnings"])
    suggestion_count = len(formatted["suggestions"])
    
    if formatted["approved"]:
        formatted["summary"] = f"✅ Validation passed! Quality score: {formatted['quality_score']}/100"
        if warning_count > 0:
            formatted["summary"] += f" ({warning_count} warning(s), {suggestion_count} suggestion(s))"
    else:
        formatted["summary"] = f"❌ Validation failed with {error_count} error(s), {warning_count} warning(s), {suggestion_count} suggestion(s). Quality score: {formatted['quality_score']}/100"
    
    return formatted

@router.post("/generate-mcp-code", response_model=GenerateCodeResponse)
async def generate_mcp_code_endpoint(request: GenerateCodeRequest):
    """Generate MCP code from collected tools"""
    # Get project root
    project_root = Path(__file__).parent.parent.absolute()

    # Ensure output directory exists
    output_dir = project_root / "mcp-generator"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"mcp_server_generated_iter_{request.iteration}.py"

    # Always persist the incoming tools as a temp spec file for reproducibility
    temp_file_path = project_root / f"temp_api_spec_iter_{request.iteration}.json"
    with open(temp_file_path, "w", encoding="utf-8") as f:
        json.dump(request.tools, f, indent=2, ensure_ascii=False)

    # Prefer the LLM-based generator if available; otherwise fall back deterministically.
    llm_generation_failed = False
    llm_error_message = None
    api_key_error_detected = False
    
    try:
        from agent_mcp_generator import generate_mcp_code

        logger.info(f"Attempting LLM-based code generation for {len(request.tools)} tools (iteration {request.iteration})")
        logger.info(f"Validation enabled: {request.use_validator}, Max validation iterations: {request.max_validation_iterations}")
        
        result = await generate_mcp_code(
            api_spec_path=str(temp_file_path),
            output_path=str(output_file),
            use_super_validator=request.use_validator,
            validator_url="http://localhost:8002" if request.use_validator else None,
            max_validation_iterations=request.max_validation_iterations,  # Use configurable max iterations
        )
        
        # Handle tuple return (output_path, validation_feedback) or just output_path for backward compatibility
        if isinstance(result, tuple):
            output_path, validation_feedback = result
        else:
            output_path = result
            validation_feedback = None

        # Verify the output path is valid
        if not output_path:
            logger.warning("LLM generation returned empty output path")
            llm_generation_failed = True
            llm_error_message = "LLM generation returned empty output path"
        else:
            # Verify the output path and file exists
            output_path_obj = Path(output_path)
            if not output_path_obj.is_absolute():
                output_path_obj = project_root / output_path

            # Check if file exists before trying to read it
            if output_path_obj.exists() and output_path_obj.is_file():
                # Verify file has content
                if output_path_obj.stat().st_size > 0:
                    logger.info(f"LLM generation succeeded. Generated file: {output_path_obj} ({output_path_obj.stat().st_size} bytes)")
                    code = output_path_obj.read_text(encoding="utf-8")
                    
                    # Format validation feedback if available
                    formatted_feedback = None
                    if validation_feedback:
                        formatted_feedback = _format_validation_feedback(validation_feedback)
                    
                    return GenerateCodeResponse(
                        success=True, 
                        code=code, 
                        output_path=str(output_path_obj),
                        validation_feedback=formatted_feedback
                    )
                else:
                    logger.warning(f"LLM generation returned empty file: {output_path_obj}")
                    llm_generation_failed = True
                    llm_error_message = "LLM generation produced an empty file"
            else:
                logger.warning(f"LLM generation did not create expected file: {output_path_obj}")
                llm_generation_failed = True
                llm_error_message = f"LLM generation did not create output file: {output_path_obj}"
            
    except ImportError as e:
        # LLM generator (Google ADK) not installed
        logger.info(f"LLM generator (Google ADK) not available: {e}. Falling back to deterministic generator.")
        llm_generation_failed = True
        llm_error_message = f"Google ADK not installed: {str(e)}"
    except Exception as e:
        # Log the exception with full details
        logger.error(f"LLM-based code generation failed: {type(e).__name__}: {e}", exc_info=True)
        llm_generation_failed = True
        llm_error_message = str(e)
        
        # Check if this is an API key/quota error
        is_api_error, api_error_msg = _is_api_key_or_quota_error(e)
        if is_api_error:
            api_key_error_detected = True
            logger.warning(api_error_msg)
            llm_error_message = api_error_msg

    # Always try deterministic fallback if LLM generation failed or was not attempted
    if llm_generation_failed:
        logger.info("Attempting deterministic fallback code generation")
        try:
            from shared.mcp_deterministic_generator import generate_mcp_server_code

            code = generate_mcp_server_code(
                tools=request.tools,
                server_name="Generated MCP Server (Deterministic Fallback)",
                default_spec_filename=temp_file_path.name,
            )
            
            # Write the generated code to file
            output_file.write_text(code, encoding="utf-8")
            logger.info(f"Deterministic fallback generation succeeded. Generated {len(code)} characters of code.")
            
            # Prepare response with warning if API key issue was detected
            error_msg = None
            if api_key_error_detected:
                error_msg = llm_error_message
            
            return GenerateCodeResponse(
                success=True, 
                code=code, 
                output_path=str(output_file),
                error=error_msg  # Include API key error as warning but still return success with fallback code
            )
        except Exception as e:
            logger.error(f"Deterministic fallback generation also failed: {type(e).__name__}: {e}", exc_info=True)
            # Combine error messages if both failed
            combined_error = f"Both LLM and deterministic generation failed. "
            if llm_error_message:
                combined_error += f"LLM error: {llm_error_message}. "
            combined_error += f"Deterministic error: {str(e)}"
            return GenerateCodeResponse(success=False, error=combined_error)
    
    # This should not be reached, but handle it just in case
    logger.error("Code generation reached unexpected state")
    return GenerateCodeResponse(
        success=False, 
        error="Unexpected error: Code generation failed without attempting fallback"
    )

