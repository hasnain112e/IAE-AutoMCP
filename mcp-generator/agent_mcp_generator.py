#!/usr/bin/env python3
"""
Agent-based MCP code generator using ADK.

This script uses an ADK agent to generate MCP server code from API or SDK specifications.
The agent analyzes the spec and generates Python code for a FastMCP server that can:
- Make HTTP requests for API specifications
- Import and call Python SDK functions for SDK specifications
"""
import os
import sys
from pathlib import Path

# Add the mcp-generator directory to sys.path so we can import prompt_manager
# This works whether the script is run directly or as a module
script_dir = Path(__file__).parent.absolute()
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from dotenv import load_dotenv
from google.genai import types # Ensure this is imported
from prompt_manager import PromptManager

# 1. Load the API key into the environment (override=True ensures updated keys are loaded)
load_dotenv(override=True) 

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
import tempfile
import subprocess

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.tools.function_tool import FunctionTool
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.utils.context_utils import Aclosing
from google.genai import types

# A2A protocol support
try:
    from google.adk.a2a.utils.agent_to_a2a import to_a2a
    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False

# HTTP client for A2A communication
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def read_api_spec(file_path: str) -> Dict[str, Any]:
    """Read API or SDK specification from file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_generated_code(file_path: str, code: str) -> None:
    """Write generated code to file."""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)


def get_default_model() -> str:
    """Get the default model name from environment or use fallback."""
    load_dotenv(override=True)
    return os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash-lite')


async def validate_with_a2a_agent(
    validator_url: str,
    generated_code: str,
    iteration: int
) -> Dict[str, Any]:
    """Validate generated code with an A2A validator agent.
    
    Args:
        validator_url: URL of the A2A validator agent endpoint
        generated_code: The generated Python code to validate
        iteration: Current iteration number
        
    Returns:
        Dict with structure: {
            "approved": bool,
            "errors": List[str],
            "warnings": List[str],
            "suggestions": List[str]
        }
        
    Raises:
        Exception: If validation request fails
    """
    try:
        # Ensure validator_url ends with proper endpoint
        if not validator_url.endswith('/'):
            validator_url = validator_url.rstrip('/')
        
        # A2A agents typically expose endpoints at /a2a (standard) or /chat (fallback)
        # Try standard A2A endpoint first, then fallbacks
        endpoints_to_try = [
            f"{validator_url}/a2a",
            f"{validator_url}/chat",
            validator_url
        ]
        
        # Create JSON-RPC 2.0 request ID
        request_id = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        context_id = f"mcp_validation_{iteration}"
        
        # Format message for validator - include code and iteration in the text
        message_text = f"""Please validate this generated MCP server code (iteration {iteration}).

Generated Code:
```python
{generated_code}
```

Please provide feedback in the following JSON format:
{{
    "approved": true/false,
    "errors": ["error1", "error2"],
    "warnings": ["warning1"],
    "suggestions": ["suggestion1"]
}}"""
        
        # JSON-RPC 2.0 A2A protocol message format
        a2a_payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "message": {
                    "messageId": message_id,
                    "contextId": context_id,
                    "taskId": f"validate_mcp_code_iteration_{iteration}",
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": message_text
                        }
                    ],
                    "metadata": {
                        "iteration": iteration,
                        "code_length": len(generated_code)
                    }
                }
            },
            "id": request_id
        }
        
        # Also try simple JSON format for custom validators (backward compatibility)
        simple_payload = {
            "code": generated_code,
            "iteration": iteration
        }
        
        last_error = None
        for endpoint in endpoints_to_try:
            # Try A2A format first
            for payload, payload_name in [(a2a_payload, "A2A"), (simple_payload, "simple")]:
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            endpoint,
                            json=payload,
                            headers={"Content-Type": "application/json"}
                        )
                        response.raise_for_status()
                        
                        response_data = response.json()
                        
                        # Handle JSON-RPC 2.0 response format
                        if isinstance(response_data, dict) and response_data.get("jsonrpc") == "2.0":
                            # JSON-RPC 2.0 format response
                            if "error" in response_data:
                                # Handle JSON-RPC error
                                error_info = response_data.get("error", {})
                                error_msg = error_info.get("message", "Unknown error")
                                error_code = error_info.get("code", -1)
                                raise Exception(f"JSON-RPC error {error_code}: {error_msg}")
                            
                            # Extract result from JSON-RPC response
                            result_data = response_data.get("result", {})
                            if isinstance(result_data, dict):
                                feedback = result_data
                            elif isinstance(result_data, str):
                                # Try to parse JSON from string
                                try:
                                    feedback = json.loads(result_data)
                                except:
                                    # Extract JSON from text if it's embedded
                                    import re
                                    json_match = re.search(r'\{[^{}]*"approved"[^{}]*\}', result_data, re.DOTALL)
                                    if json_match:
                                        feedback = json.loads(json_match.group())
                                    else:
                                        feedback = response_data
                            else:
                                feedback = result_data
                        elif isinstance(response_data, dict) and "params" in response_data:
                            # Legacy A2A format response (backward compatibility)
                            result_data = response_data.get("params", {}).get("result", {})
                            if isinstance(result_data, dict):
                                feedback = result_data
                            elif isinstance(result_data, str):
                                try:
                                    feedback = json.loads(result_data)
                                except:
                                    import re
                                    json_match = re.search(r'\{[^{}]*"approved"[^{}]*\}', result_data, re.DOTALL)
                                    if json_match:
                                        feedback = json.loads(json_match.group())
                                    else:
                                        feedback = response_data
                            else:
                                feedback = result_data
                        else:
                            # Direct JSON response
                            feedback = response_data
                        
                        # Validate feedback structure
                        if not isinstance(feedback, dict):
                            raise ValueError("Validator response is not a JSON object")
                        
                        # Ensure required fields exist
                        result = {
                            "approved": feedback.get("approved", False),
                            "errors": feedback.get("errors", []),
                            "warnings": feedback.get("warnings", []),
                            "suggestions": feedback.get("suggestions", [])
                        }
                        
                        # Ensure lists are actually lists
                        for key in ["errors", "warnings", "suggestions"]:
                            if not isinstance(result[key], list):
                                result[key] = []
                        
                        logger.debug(f"Successfully validated using {payload_name} format at {endpoint}")
                        return result
                        
                except httpx.HTTPError as e:
                    last_error = e
                    logger.debug(f"Failed to reach validator at {endpoint} with {payload_name} format: {e}")
                    continue
                except (json.JSONDecodeError, ValueError) as e:
                    last_error = e
                    logger.debug(f"Invalid response format from {endpoint} with {payload_name} format: {e}")
                    continue
        
        # If all endpoints and formats failed, raise the last error
        raise last_error or Exception("Failed to reach validator at any endpoint with any format")
        
    except Exception as e:
        logger.error(f"Error validating code with A2A agent: {e}")
        # Return a default feedback indicating validation failed
        return {
            "approved": False,
            "errors": [f"Validation request failed: {str(e)}"],
            "warnings": [],
            "suggestions": []
        }


def process_validation_feedback(feedback: Dict[str, Any]) -> str:
    """Process validation feedback into a formatted string for regeneration prompt.
    
    Args:
        feedback: Validation feedback dict with approved, errors, warnings, suggestions
        
    Returns:
        Formatted string describing issues to fix
    """
    parts = []
    
    if feedback.get("errors"):
        parts.append("**CRITICAL ERRORS TO FIX:**")
        for i, error in enumerate(feedback["errors"], 1):
            parts.append(f"{i}. {error}")
        parts.append("")
    
    if feedback.get("warnings"):
        parts.append("**WARNINGS TO ADDRESS:**")
        for i, warning in enumerate(feedback["warnings"], 1):
            parts.append(f"{i}. {warning}")
        parts.append("")
    
    if feedback.get("suggestions"):
        parts.append("**SUGGESTIONS FOR IMPROVEMENT:**")
        for i, suggestion in enumerate(feedback["suggestions"], 1):
            parts.append(f"{i}. {suggestion}")
        parts.append("")
    
    if not parts:
        return "No specific feedback provided. Please review the code and ensure it meets all requirements."
    
    return "\n".join(parts)


def create_mcp_generator_agent(model: str = None) -> LlmAgent:
    """Create an ADK agent that generates MCP server code.
    
    Args:
        model: Model name to use. If None, reads from GEMINI_MODEL env var or uses default.
    """
    if model is None:
        model = get_default_model()
    
    # Tool to read API/SDK specs
    @FunctionTool
    def read_api_spec_tool(file_path: str) -> str:
        """Read and return the contents of an API or SDK specification file.
        
        Args:
            file_path: Path to the API or SDK specification JSON file
            
        Returns:
            JSON string of the API or SDK specification
        """
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    # Tool to write generated code
    @FunctionTool
    def write_code_tool(file_path: str, code: str, append: bool = False) -> str:
        """Write generated Python code to a file.
        
        WARNING: For incremental tool generation, use write_tool_function instead!
        This tool should only be used for writing complete files, not for appending tools.
        
        Args:
            file_path: Path where the code should be written
            code: Python code to write
            append: If True, append to file; if False, overwrite file (default: False)
            
        Returns:
            Confirmation message
        """
        file_path = os.path.normpath(os.path.abspath(file_path))
        
        if append:
            # Append mode
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(code)
            return f"Code appended to {file_path}"
        else:
            # Write mode - warn if file exists and has content
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    existing = f.read()
                    if existing.strip() and "@mcp.tool()" in existing:
                        logger.warning(f"⚠️ write_code_tool is OVERWRITING existing file with {existing.count('@mcp.tool()')} tools!")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            return f"Code written to {file_path} (overwrote existing file)"
    
    # Tool to write a single tool function
    @FunctionTool
    def write_tool_function(file_path: str, tool_code: str) -> str:
        """Append a single MCP tool function to the server file.
        
        IMPORTANT: This function APPENDS to the file, it does NOT overwrite.
        Use this to add tool functions one at a time.
        
        Args:
            file_path: Path to the MCP server file (must be absolute path)
            tool_code: Python code for a single @mcp.tool() function (must include @mcp.tool() decorator)
            
        Returns:
            Confirmation message with details about what was written
        """
        # Normalize the path
        file_path = os.path.normpath(os.path.abspath(file_path))
        
        # Ensure file exists (should have header already)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Output file not found: {file_path}. Header should have been written first.")
        
        # Read current content to verify we're appending
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
                existing_tool_count = existing_content.count("@mcp.tool()")
                existing_size = len(existing_content)
        except Exception as e:
            raise FileNotFoundError(f"Cannot read existing file {file_path}: {e}")
        
        # Append the tool function (mode "a" = append, not overwrite)
        # Use explicit append mode and ensure we add newlines
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                # Ensure we have proper spacing
                if not existing_content.endswith("\n"):
                    f.write("\n")
                f.write("\n" + tool_code)
                f.flush()  # Force write to disk
                os.fsync(f.fileno())  # Ensure OS has written to disk
        except Exception as e:
            raise RuntimeError(f"Failed to append to file {file_path}: {e}")
        
        # Verify the append worked by reading again
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                new_content = f.read()
                new_tool_count = new_content.count("@mcp.tool()")
                new_size = len(new_content)
        except Exception as e:
            raise RuntimeError(f"Failed to verify append to file {file_path}: {e}")
        
        # Verify content was appended, not replaced
        if new_size <= existing_size:
            raise RuntimeError(
                f"ERROR: File was overwritten instead of appended! "
                f"File size: {existing_size} -> {new_size} bytes. "
                f"Tool count: {existing_tool_count} -> {new_tool_count}. "
                f"This should not happen with append mode!"
            )
        
        if new_tool_count <= existing_tool_count:
            logger.warning(
                f"⚠️ Tool count did not increase: {existing_tool_count} -> {new_tool_count}. "
                f"File size increased ({existing_size} -> {new_size}), but tool count didn't."
            )
        
        logger.info(f"📝 Appended tool function to {file_path} (tools: {existing_tool_count} -> {new_tool_count}, size: {existing_size} -> {new_size} bytes)")
        return f"Tool function appended to {file_path}. File now contains {new_tool_count} tool(s) (was {existing_tool_count})."
    instruction = PromptManager.get_agent_instruction()

    agent = LlmAgent(
        name="mcp_code_generator",
        model=model,
        instruction=instruction,
        description="An agent that generates MCP server code from API or SDK specifications",
        tools=[read_api_spec_tool, write_code_tool, write_tool_function],
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=16384,  # Increased for large SDK specs
        )
    )
    
    return agent


async def generate_mcp_code_incremental(
    api_spec_path: str,
    output_path: Optional[str] = None,
    model: str = None,
    tools_per_batch: int = 10,
    max_tools: int = 0,
    validator_url: Optional[str] = None,
    max_validation_iterations: int = 3
) -> str:
    """Generate MCP server code incrementally, processing tools in batches.
    
    Args:
        api_spec_path: Path to API or SDK specification file
        output_path: Path to save generated code (defaults to mcp-generator/mcp_server_generated.py)
        model: Model to use for code generation (if None, reads from GEMINI_MODEL env var)
        tools_per_batch: Number of tools to generate per batch (default: 10)
        max_tools: Maximum number of tools to process (0 = all tools)
        
    Returns:
        Path to generated code file
    """
    if model is None:
        model = get_default_model()
    
    try:
        # Get the script directory (mcp-generator folder)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Normalize the spec path to get the actual filename
        api_spec_path_abs = os.path.abspath(api_spec_path)
        spec_filename = os.path.basename(api_spec_path_abs)
        
        if output_path is None:
            output_path = "mcp_server_generated.py"
        
        logger.info(f"📝 Output file path: {output_path}")
        
        # Read the spec to determine structure
        spec_data = read_api_spec(api_spec_path)
        
        # Handle both dict format (with "tools" key) and array format
        if isinstance(spec_data, dict) and "tools" in spec_data:
            tools = spec_data["tools"]
            source_type = spec_data.get("source_type", "unknown")
        elif isinstance(spec_data, list):
            tools = spec_data
            # Determine source type from first tool
            source_type = "python_sdk" if tools and tools[0].get("metadata", {}).get("source") == "python_sdk" else "api"
        else:
            raise ValueError(f"Unsupported spec format. Expected dict with 'tools' key or array, got {type(spec_data)}")
        
        # Limit tools if max_tools is specified
        if max_tools > 0 and max_tools < len(tools):
            logger.info(f"Limiting to first {max_tools} tools (out of {len(tools)} total)")
            tools = tools[:max_tools]
        
        total_batches = (len(tools) + tools_per_batch - 1) // tools_per_batch
        logger.info(f"Found {len(tools)} tools to generate. Source type: {source_type}")
        logger.info(f"Processing {tools_per_batch} tool(s) per batch ({total_batches} batches total)...")
        
        # Reload environment variables to ensure latest API key is used
        load_dotenv(override=True)
        api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
        if api_key:
            logger.info(f"✅ API key loaded (length: {len(api_key)}, starts with: {api_key[:10]}...)")
        else:
            logger.warning("⚠️ No API key found in environment (GOOGLE_API_KEY or GEMINI_API_KEY)")
        
        # Create agent
        agent = create_mcp_generator_agent(model)
        
        # Create runner
        runner = Runner(
            app_name="mcp_generator",
            agent=agent,
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
        
        # Create session
        session = await runner.session_service.create_session(
            app_name="mcp_generator",
            user_id="user",
        )
        
        # Generate initial MCP server header
        # Ensure spec_filename is correctly extracted
        spec_filename = os.path.basename(os.path.abspath(api_spec_path))
        
        if source_type == "python_sdk":
            header_code = f"""from fastmcp import FastMCP
import json
import os
import importlib
import asyncio

mcp = FastMCP("SDK Server")

def load_api_spec():
    \"\"\"Load SDK specification from JSON file.\"\"\"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    api_spec_filename = os.environ.get('API_SPEC_FILENAME', '{spec_filename}')
    spec_file = os.path.join(script_dir, api_spec_filename)
    with open(spec_file, 'r') as f:
        return json.load(f)

API_SPEC = load_api_spec()

# Cache for imported SDK modules
_sdk_modules = {{}}

def get_sdk_module(module_name: str):
    \"\"\"Dynamically import and cache SDK module.\"\"\"
    if module_name not in _sdk_modules:
        _sdk_modules[module_name] = importlib.import_module(module_name)
    return _sdk_modules[module_name]

"""
        else:
            header_code = f"""from fastmcp import FastMCP
import httpx
import json
import os

mcp = FastMCP("API Server")

def load_api_spec():
    \"\"\"Load API specification from JSON file.\"\"\"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    api_spec_filename = os.environ.get('API_SPEC_FILENAME', '{spec_filename}')
    spec_file = os.path.join(script_dir, api_spec_filename)
    with open(spec_file, 'r') as f:
        return json.load(f)

API_SPEC = load_api_spec()

"""
        
        # Write header to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header_code)
        logger.info(f"✅ Wrote MCP server header to {output_path}")
        
        # Process tools in batches
        total_tools = len(tools)
        max_batch_retries = 3
        batches_processed = 0
        batches_succeeded = 0
        batches_failed = 0
        total_batches = (total_tools + tools_per_batch - 1) // tools_per_batch
        
        logger.info(f"🔄 Starting batch processing: {total_batches} batches, {total_tools} total tools")
        logger.info(f"   Tools per batch: {tools_per_batch}")
        
        for batch_start in range(0, total_tools, tools_per_batch):
            batch_end = min(batch_start + tools_per_batch, total_tools)
            batch_tools = tools[batch_start:batch_end]
            batch_num = (batch_start // tools_per_batch) + 1
            
            num_tools_in_batch = len(batch_tools)
            logger.info(f"Processing batch {batch_num}/{total_batches} (tools {batch_start+1}-{batch_end} of {total_tools})...")
            logger.info(f"📦 Sending SINGLE request with all {num_tools_in_batch} tool(s) in this batch")
            
            # Create prompt for this batch
            # Truncate very long tool JSON to avoid token limits
            tools_json = json.dumps(batch_tools, indent=2)
            if len(tools_json) > 50000:  # Limit to ~50KB per batch
                logger.warning(f"⚠️ Batch {batch_num}: Tool JSON is very large ({len(tools_json)} chars), truncating...")
                # Keep first 25KB and last 25KB
                tools_json = tools_json[:25000] + "\n... (truncated for length) ...\n" + tools_json[-25000:]
            
            prompt = PromptManager.get_batch_processing_prompt(
                batch_num=batch_num,
                total_batches=total_batches,
                batch_start=batch_start,
                batch_end=batch_end,
                total_tools=total_tools,
                tools_json=tools_json,
                output_path=output_path
            )
            
            # Run agent for this batch with retries
            batch_completed = False
            for attempt in range(1, max_batch_retries + 1):
                message_content = types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)]
                )
                
                try:
                    logger.info(f"🚀 Sending request {attempt} for batch {batch_num} with {num_tools_in_batch} tool(s)")
                    async with Aclosing(
                        runner.run_async(
                            session_id=session.id,
                            user_id="user",
                            new_message=message_content,
                        )
                    ) as event_generator:
                        batch_tool_calls = []
                        write_tool_function_calls = 0
                        async for event in event_generator:
                            # Log function calls
                            function_calls = event.get_function_calls()
                            if function_calls:
                                for fc in function_calls:
                                    tool_name = fc.name
                                    logger.info(f"🔧 Batch {batch_num}: Agent calling tool: {tool_name}")
                                    batch_tool_calls.append(tool_name)
                                    if tool_name == "write_tool_function":
                                        write_tool_function_calls += 1
                            
                            # Log function responses
                            function_responses = event.get_function_responses()
                            if function_responses:
                                for fr in function_responses:
                                    logger.info(f"✅ Batch {batch_num}: Tool response from {fr.name}")
                        
                        # Log summary for this batch
                        logger.info(f"📊 Batch {batch_num} summary: write_tool_function called {write_tool_function_calls} time(s) (expected: {num_tools_in_batch})")
                        if write_tool_function_calls < num_tools_in_batch:
                            logger.warning(f"⚠️ Batch {batch_num}: Only {write_tool_function_calls} of {num_tools_in_batch} tools were generated in this request!")
                        
                        # Verify tools were actually written by checking file
                        if write_tool_function_calls > 0:
                            try:
                                with open(output_path, "r", encoding="utf-8") as f:
                                    current_content = f.read()
                                    current_tool_count = current_content.count("@mcp.tool()")
                                    logger.info(f"✅ Batch {batch_num}: Verified {current_tool_count} tool(s) in file after processing.")
                            except Exception as e:
                                logger.warning(f"⚠️ Could not verify tools in file after batch {batch_num}: {e}")
                        
                        # Check if tools were written
                        if "write_tool_function" not in batch_tool_calls and "write_code_tool" not in batch_tool_calls:
                            logger.warning(f"⚠️ Batch {batch_num}: No tools were written. Agent may need a follow-up.")
                            # Send follow-up for this batch
                            tool_names = [t.get('name', 'unknown') for t in batch_tools]
                            follow_up = types.Content(
                                role="user",
                                parts=[types.Part(text=PromptManager.get_batch_followup_prompt(
                                    output_path=output_path,
                                    tool_names=tool_names,
                                    num_tools=len(batch_tools)
                                ))]
                            )
                            try:
                                async with Aclosing(
                                    runner.run_async(
                                        session_id=session.id,
                                        user_id="user",
                                        new_message=follow_up,
                                    )
                                ) as follow_up_generator:
                                    async for event in follow_up_generator:
                                        function_calls = event.get_function_calls()
                                        if function_calls:
                                            for fc in function_calls:
                                                logger.info(f"🔧 Follow-up: Agent calling {fc.name}")
                            except Exception as follow_up_error:
                                logger.warning(f"Error in follow-up for batch {batch_num}: {follow_up_error}")
                    
                    # Final verification: check if expected number of tools were written
                    if write_tool_function_calls > 0:
                        # Check current tool count in file
                        try:
                            with open(output_path, "r", encoding="utf-8") as f:
                                current_content = f.read()
                                current_tool_count = current_content.count("@mcp.tool()")
                                expected_min = batch_start + write_tool_function_calls
                                logger.info(f"✅ Batch {batch_num} completed. File now has {current_tool_count} tool(s).")
                                
                                if current_tool_count < expected_min:
                                    logger.warning(f"⚠️ Batch {batch_num}: Expected at least {expected_min} tools, but found {current_tool_count}")
                        except Exception as e:
                            logger.warning(f"⚠️ Could not verify tools in file after batch {batch_num}: {e}")
                    elif write_tool_function_calls == 0:
                        logger.error(f"❌ Batch {batch_num}: No tools were written! write_tool_function was not called.")
                        # Don't mark as completed if no tools were written
                        batch_completed = False
                        continue  # Try next attempt
                    
                    batch_completed = True
                    break
                except asyncio.CancelledError as cancel_error:
                    logger.warning(f"Batch {batch_num} cancelled (attempt {attempt}/{max_batch_retries}): {cancel_error}")
                    if attempt == max_batch_retries:
                        raise
                    backoff = min(5 * attempt, 15)
                    logger.info(f"Retrying batch {batch_num} after {backoff} seconds...")
                    await asyncio.sleep(backoff)
                    continue
                except Exception as e:
                    logger.warning(f"Error processing batch {batch_num} (attempt {attempt}/{max_batch_retries}): {e}")
                    if attempt == max_batch_retries:
                        logger.error(f"Batch {batch_num} failed after {max_batch_retries} attempts. Skipping to next batch.")
                    else:
                        await asyncio.sleep(2 * attempt)
                    continue
            
            batches_processed += 1
            
            if not batch_completed:
                batches_failed += 1
                logger.error(f"❌ Batch {batch_num} could not be completed after {max_batch_retries} attempts. Continuing with remaining batches...")
            else:
                batches_succeeded += 1
                logger.info(f"✅ Batch {batch_num}/{total_batches} completed successfully. Moving to next batch...")
            
            # Log progress
            logger.info(f"📈 Progress: {batches_processed}/{total_batches} batches processed ({batches_succeeded} succeeded, {batches_failed} failed)")
        
        # Log final batch processing summary
        logger.info(f"📊 Batch processing complete: {batches_processed}/{total_batches} batches processed")
        logger.info(f"   Succeeded: {batches_succeeded}, Failed: {batches_failed}")
        
        # Write footer (if __name__ block)
        footer_code = """
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8504, path="/mcp")
"""
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(footer_code)
        
        # Verify file was created and has content
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            # Count actual tool functions
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()
                tool_count = content.count("@mcp.tool()")
                # Also count function definitions to double-check
                function_defs = content.count("async def ") + content.count("def ")
            
            logger.info(f"✅ Generated MCP server: {output_path}")
            logger.info(f"   File size: {file_size} bytes")
            logger.info(f"   Tools found: {tool_count} (expected: {total_tools})")
            logger.info(f"   Function definitions: {function_defs}")
            
            if tool_count == 0:
                logger.warning(f"⚠️ WARNING: No @mcp.tool() functions found in generated file!")
                logger.warning(f"   The file may only contain header/footer code.")
            elif tool_count < total_tools:
                missing = total_tools - tool_count
                logger.warning(f"⚠️ WARNING: Only {tool_count} of {total_tools} tools were generated!")
                logger.warning(f"   Missing {missing} tool(s). Some batches may have failed.")
                logger.warning(f"   Check the logs above for batch processing errors.")
        else:
            logger.error(f"❌ ERROR: Output file was not created: {output_path}")
        
        # Validation loop with A2A validator
        if validator_url:
            logger.info(f"🔄 Starting validation loop with A2A validator at {validator_url}")
            logger.info(f"   Max iterations: {max_validation_iterations}")
            
            for iteration in range(1, max_validation_iterations + 1):
                try:
                    # Read generated code
                    with open(output_path, "r", encoding="utf-8") as f:
                        generated_code = f.read()
                    
                    logger.info(f"📋 Validating generated code with A2A validator (iteration {iteration}/{max_validation_iterations})...")
                    
                    # Validate with A2A agent
                    feedback = await validate_with_a2a_agent(
                        validator_url=validator_url,
                        generated_code=generated_code,
                        iteration=iteration
                    )
                    
                    logger.info(f"✅ Validation feedback received: approved={feedback['approved']}, "
                              f"errors={len(feedback['errors'])}, warnings={len(feedback['warnings'])}, "
                              f"suggestions={len(feedback['suggestions'])}")
                    
                    if feedback["approved"]:
                        logger.info(f"🎉 Validation passed after {iteration} iteration(s)!")
                        break
                    
                    if iteration < max_validation_iterations:
                        logger.info(f"⚠️ Validation failed. Regenerating code based on feedback (iteration {iteration + 1}/{max_validation_iterations})...")
                        
                        # Create regeneration prompt
                        regeneration_prompt = PromptManager.get_regeneration_prompt(
                            api_spec_path=api_spec_path,
                            output_path=output_path,
                            feedback=feedback,
                            iteration=iteration + 1
                        )
                        
                        # Create new session for regeneration
                        regen_session = await runner.session_service.create_session(
                            app_name="mcp_generator",
                            user_id="user",
                        )
                        
                        # Regenerate code
                        regen_message = types.Content(
                            role="user",
                            parts=[types.Part(text=regeneration_prompt)]
                        )
                        
                        try:
                            async with Aclosing(
                                runner.run_async(
                                    session_id=regen_session.id,
                                    user_id="user",
                                    new_message=regen_message,
                                )
                            ) as regen_event_generator:
                                async for event in regen_event_generator:
                                    # Log function calls
                                    function_calls = event.get_function_calls()
                                    if function_calls:
                                        for fc in function_calls:
                                            logger.info(f"🔧 Regeneration: Agent calling tool: {fc.name}")
                                    
                                    # Log function responses
                                    function_responses = event.get_function_responses()
                                    if function_responses:
                                        for fr in function_responses:
                                            logger.info(f"✅ Regeneration: Tool response from {fr.name}")
                        except Exception as regen_error:
                            logger.error(f"❌ Error during regeneration: {regen_error}")
                            logger.warning("Continuing with current code...")
                    else:
                        logger.warning(f"⚠️ Validation failed after {max_validation_iterations} iterations. Using last generated code.")
                        logger.warning(f"   Final feedback: {len(feedback['errors'])} errors, {len(feedback['warnings'])} warnings")
                        
                except Exception as validation_error:
                    logger.error(f"❌ Error in validation loop (iteration {iteration}): {validation_error}")
                    if iteration < max_validation_iterations:
                        logger.warning("Continuing to next iteration...")
                    else:
                        logger.warning("Max iterations reached. Using generated code without validation.")
        else:
            logger.info("ℹ️ No validator URL provided. Skipping validation.")
        
        return output_path
    except Exception as e:
        # Log the full error with traceback
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"❌ Error in generate_mcp_code_incremental: {e}")
        logger.error(f"Full traceback:\n{error_trace}")
        # Re-raise with more context
        raise RuntimeError(f"Failed to generate MCP code: {e}\n{error_trace}") from e


async def generate_mcp_code(
    api_spec_path: str,
    output_path: Optional[str] = None,
    model: str = None,
    incremental: bool = False,
    tools_per_batch: int = 10,
    max_tools: int = 0,
    validator_url: Optional[str] = None,
    max_validation_iterations: int = 3
) -> str:
    """Generate MCP server code using an ADK agent.
    
    Args:
        api_spec_path: Path to API or SDK specification file
        output_path: Path to save generated code (defaults to mcp-generator/{spec_name}_mcp_server.py)
        model: Model to use for code generation (if None, reads from GEMINI_MODEL env var)
        incremental: If True, process tools incrementally (batches at a time)
        tools_per_batch: Number of tools to generate per batch when incremental=True
        max_tools: Maximum number of tools to process (0 = all tools)
        
    Returns:
        Path to generated code file
    """
    if model is None:
        model = get_default_model()
    
    if incremental:
        return await generate_mcp_code_incremental(
            api_spec_path, output_path, model, tools_per_batch, max_tools,
            validator_url, max_validation_iterations
        )
    
    if output_path is None:
        output_path = "mcp_server_generated.py"
    
    # Reload environment variables to ensure latest API key is used
    load_dotenv(override=True)
    api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    if api_key:
        logger.info(f"✅ API key loaded (length: {len(api_key)}, starts with: {api_key[:10]}...)")
    else:
        logger.warning("⚠️ No API key found in environment (GOOGLE_API_KEY or GEMINI_API_KEY)")
    
    # Create agent
    agent = create_mcp_generator_agent(model)
    
    # Create runner
    runner = Runner(
        app_name="mcp_generator",
        agent=agent,
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )
    
    # Create session
    session = await runner.session_service.create_session(
        app_name="mcp_generator",
        user_id="user",
    )
    
    # Prepare prompt
    prompt = PromptManager.get_non_incremental_prompt(
        api_spec_path=api_spec_path,
        output_path=output_path
    )
    
    logger.info(f"Generating MCP server code from {api_spec_path}...")
    logger.info("This may take a moment as the agent analyzes and generates the code...")
    
    # Create message content
    message_content = types.Content(
        role="user",
        parts=[types.Part(text=prompt)]
    )
    
    # Run agent and collect events
    tool_calls_made = []
    agent_responses = []  # Collect all agent text responses for code extraction
    try:
        async with Aclosing(
            runner.run_async(
                session_id=session.id,
                user_id="user",
                new_message=message_content,
            )
        ) as event_generator:
            async for event in event_generator:
                # Log function calls
                function_calls = event.get_function_calls()
                if function_calls:
                    for fc in function_calls:
                        tool_name = fc.name
                        logger.info(f"🔧 Agent calling tool: {tool_name} with args: {fc.args}")
                        tool_calls_made.append(tool_name)
                
                # Log function responses
                function_responses = event.get_function_responses()
                if function_responses:
                    for fr in function_responses:
                        tool_name = fr.name
                        response_preview = str(fr.response)[:100] if fr.response else "None"
                        logger.info(f"✅ Tool response from {tool_name}: {response_preview}...")
                
                # Log agent text responses (but truncate long responses)
                if event.content and event.content.parts:
                    text_parts = []
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                    if text_parts:
                        full_text = "".join(text_parts)
                        agent_responses.append(full_text)  # Store for code extraction
                        # Truncate very long responses
                        if len(full_text) > 500:
                            logger.info(f"Agent: {full_text[:500]}... (truncated)")
                        else:
                            logger.info(f"Agent: {full_text}")
    except (asyncio.CancelledError, KeyboardInterrupt) as e:
        # Handle cancellation gracefully - check if file was created
        logger.warning(f"Agent execution was interrupted: {e}")
        logger.info("Checking if code was successfully generated before interruption...")
    except Exception as e:
        # Log other errors but continue to check if file was created
        logger.warning(f"Error during agent execution: {e}")
        logger.info("Checking if code was successfully generated despite the error...")
    
    # Summary of tool usage
    if tool_calls_made:
        logger.info(f"Tools called: {', '.join(set(tool_calls_made))}")
        if "write_code_tool" not in tool_calls_made:
            logger.warning("⚠️ write_code_tool was not called. Sending follow-up prompt...")
            
            # Send follow-up message to explicitly request write_code_tool
            follow_up_message = types.Content(
                role="user",
                parts=[types.Part(text=PromptManager.get_non_incremental_followup_prompt(
                    output_path=output_path
                ))]
            )
            
            try:
                logger.info("Sending follow-up message to agent...")
                async with Aclosing(
                    runner.run_async(
                        session_id=session.id,
                        user_id="user",
                        new_message=follow_up_message,
                    )
                ) as event_generator:
                    async for event in event_generator:
                        # Log function calls
                        function_calls = event.get_function_calls()
                        if function_calls:
                            for fc in function_calls:
                                tool_name = fc.name
                                logger.info(f"🔧 Agent calling tool: {tool_name} with args: {fc.args}")
                                tool_calls_made.append(tool_name)
                        
                        # Log function responses
                        function_responses = event.get_function_responses()
                        if function_responses:
                            for fr in function_responses:
                                tool_name = fr.name
                                response_preview = str(fr.response)[:100] if fr.response else "None"
                                logger.info(f"✅ Tool response from {tool_name}: {response_preview}...")
                        
                        # Collect agent responses for code extraction
                        if event.content and event.content.parts:
                            text_parts = []
                            for part in event.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    text_parts.append(part.text)
                            if text_parts:
                                full_text = "".join(text_parts)
                                agent_responses.append(full_text)
            except Exception as e:
                logger.warning(f"Error in follow-up prompt: {e}")
    else:
        logger.warning("⚠️ No tools were called by the agent. The agent may need better instructions.")
    
    # Verify file was created (check even if there were async errors)
    logger.info(f"Checking if file exists: {output_path}")
    file_exists = os.path.exists(output_path)
    
    if not file_exists:
        logger.error(f"❌ Generated file {output_path} NOT FOUND!")
        logger.error("The agent did not successfully call write_code_tool to save the code.")
        
        # Try to extract code from agent's collected responses as fallback
        logger.warning("Attempting to extract code from agent's response...")
        try:
            import re
            # Search through all collected agent responses (most recent first)
            for text in reversed(agent_responses):
                if not text:
                    continue
                
                # Try multiple patterns to extract code
                extracted_code = None
                
                # Pattern 1: Markdown code blocks with python or no language specified
                code_blocks = re.findall(r'```(?:python)?\s*\n?(.*?)```', text, re.DOTALL)
                if code_blocks:
                    # Take the largest code block (likely the full generated code)
                    extracted_code = max(code_blocks, key=len).strip()
                
                # Pattern 2: If no code blocks found, look for code that starts with imports
                if not extracted_code:
                    # Look for code starting with common imports
                    import_pattern = r'(from fastmcp import.*?)(?=\n\n|\Z)'
                    match = re.search(import_pattern, text, re.DOTALL)
                    if match:
                        # Try to extract everything from the import to the end or next markdown block
                        start_pos = match.start()
                        # Find the end - either end of text or next ``` or ##
                        end_match = re.search(r'(?:\n```|\n##|\Z)', text[start_pos:], re.MULTILINE)
                        if end_match:
                            extracted_code = text[start_pos:start_pos + end_match.start()].strip()
                
                # Pattern 3: Look for code between "```python" and "```" even if not properly formatted
                if not extracted_code:
                    # More lenient pattern
                    match = re.search(r'```.*?python.*?\n(.*?)```', text, re.DOTALL | re.IGNORECASE)
                    if match:
                        extracted_code = match.group(1).strip()
                
                # Validate and save extracted code
                if extracted_code:
                    # Check if it looks like Python code
                    if ('from fastmcp' in extracted_code.lower() or 
                        'import fastmcp' in extracted_code.lower() or
                        ('import' in extracted_code and 'mcp' in extracted_code.lower())):
                        logger.info(f"Found code in agent response ({len(extracted_code)} chars), saving to {output_path}")
                        with open(output_path, "w", encoding="utf-8") as f:
                            f.write(extracted_code)
                        logger.info(f"✅ Extracted and saved code to {output_path}")
                        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                            file_exists = True
                            break
        except Exception as e:
            logger.debug(f"Could not extract code from response: {e}")
    
    # If file doesn't exist, raise error
    if not file_exists:
        logger.error("This could mean:")
        logger.error("  1. The agent didn't understand it needs to call write_code_tool")
        logger.error("  2. The agent encountered an error when trying to call the tool")
        logger.error("  3. The agent generated code but didn't save it")
        logger.error("\nPlease check the agent's responses above to see what happened.")
        raise FileNotFoundError(f"Generated code file {output_path} was not created by the agent.")
    
    # Check file size
    file_size = os.path.getsize(output_path)
    if file_size == 0:
        logger.warning(f"⚠️ Generated file {output_path} is empty!")
    else:
        logger.info(f"✅ Generated file {output_path} created successfully ({file_size} bytes)")
    
    logger.info("Code generation complete!")
    logger.info(f"Generated code saved to: {output_path}")
    
    # Validation loop with A2A validator
    if validator_url:
        logger.info(f"🔄 Starting validation loop with A2A validator at {validator_url}")
        logger.info(f"   Max iterations: {max_validation_iterations}")
        
        for iteration in range(1, max_validation_iterations + 1):
            try:
                # Read generated code
                with open(output_path, "r", encoding="utf-8") as f:
                    generated_code = f.read()
                
                logger.info(f"📋 Validating generated code with A2A validator (iteration {iteration}/{max_validation_iterations})...")
                
                # Validate with A2A agent
                feedback = await validate_with_a2a_agent(
                    validator_url=validator_url,
                    generated_code=generated_code,
                    iteration=iteration
                )
                
                logger.info(f"✅ Validation feedback received: approved={feedback['approved']}, "
                          f"errors={len(feedback['errors'])}, warnings={len(feedback['warnings'])}, "
                          f"suggestions={len(feedback['suggestions'])}")
                
                if feedback["approved"]:
                    logger.info(f"🎉 Validation passed after {iteration} iteration(s)!")
                    break
                
                if iteration < max_validation_iterations:
                    logger.info(f"⚠️ Validation failed. Regenerating code based on feedback (iteration {iteration + 1}/{max_validation_iterations})...")
                    
                    # Create regeneration prompt
                    regeneration_prompt = PromptManager.get_regeneration_prompt(
                        api_spec_path=api_spec_path,
                        output_path=output_path,
                        feedback=feedback,
                        iteration=iteration + 1
                    )
                    
                    # Create new session for regeneration
                    regen_session = await runner.session_service.create_session(
                        app_name="mcp_generator",
                        user_id="user",
                    )
                    
                    # Regenerate code
                    regen_message = types.Content(
                        role="user",
                        parts=[types.Part(text=regeneration_prompt)]
                    )
                    
                    try:
                        async with Aclosing(
                            runner.run_async(
                                session_id=regen_session.id,
                                user_id="user",
                                new_message=regen_message,
                            )
                        ) as regen_event_generator:
                            async for event in regen_event_generator:
                                # Log function calls
                                function_calls = event.get_function_calls()
                                if function_calls:
                                    for fc in function_calls:
                                        logger.info(f"🔧 Regeneration: Agent calling tool: {fc.name}")
                                
                                # Log function responses
                                function_responses = event.get_function_responses()
                                if function_responses:
                                    for fr in function_responses:
                                        logger.info(f"✅ Regeneration: Tool response from {fr.name}")
                    except Exception as regen_error:
                        logger.error(f"❌ Error during regeneration: {regen_error}")
                        logger.warning("Continuing with current code...")
                else:
                    logger.warning(f"⚠️ Validation failed after {max_validation_iterations} iterations. Using last generated code.")
                    logger.warning(f"   Final feedback: {len(feedback['errors'])} errors, {len(feedback['warnings'])} warnings")
                    
            except Exception as validation_error:
                logger.error(f"❌ Error in validation loop (iteration {iteration}): {validation_error}")
                if iteration < max_validation_iterations:
                    logger.warning("Continuing to next iteration...")
                else:
                    logger.warning("Max iterations reached. Using generated code without validation.")
    else:
        logger.info("ℹ️ No validator URL provided. Skipping validation.")
    
    return output_path


def run_generated_server(generated_code_path: str, port: int = 8000):
    """Run the generated MCP server."""
    logger.info(f"Starting generated MCP server on port {port}...")
    try:
        # Import and run the generated server
        import importlib.util
        spec = importlib.util.spec_from_file_location("mcp_server", generated_code_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # The generated code should have mcp.run() at the end
        # If not, we'll need to handle it differently
        logger.info("Server started successfully!")
    except Exception as e:
        logger.error(f"Error running generated server: {e}")
        logger.info("You can run it manually with: python " + generated_code_path)


def main():
    """Main entry point."""
    # Set Windows event loop policy if on Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    parser = argparse.ArgumentParser(
        description="Generate MCP server code using ADK agent"
    )
    parser.add_argument(
        "api_spec",
        type=str,
        help="Path to API or SDK specification file (OpenAPI, Postman, or SDK format)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to save generated code (default: mcp-generator/{spec_name}_mcp_server.py)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model to use for code generation (defaults to GEMINI_MODEL env var or 'gemini-2.5-flash-lite')",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the generated server after generation",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8504,
        help="Port for running the server (if --run is used)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Process tools incrementally (one at a time)",
    )
    parser.add_argument(
        "--tools-per-batch",
        type=int,
        default=10,
        help="Number of tools to generate per batch when using --incremental (default: 10)",
    )
    parser.add_argument(
        "--max-tools",
        type=int,
        default=0,
        help="Maximum number of tools to process (0 = all tools). Use this to process large specs in chunks.",
    )
    parser.add_argument(
        "--validator-url",
        type=str,
        default=None,
        help="URL of A2A validator agent (defaults to VALIDATOR_A2A_URL env var)",
    )
    parser.add_argument(
        "--max-validation-iterations",
        type=int,
        default=None,
        help="Maximum number of validation/regeneration iterations (default: 3, or MAX_VALIDATION_ITERATIONS env var)",
    )
    
    args = parser.parse_args()
    
    # Get validator URL from env if not provided via CLI
    validator_url = args.validator_url or os.environ.get('VALIDATOR_A2A_URL')
    max_validation_iterations = args.max_validation_iterations
    if max_validation_iterations is None:
        max_validation_iterations = int(os.environ.get('MAX_VALIDATION_ITERATIONS', '3'))
    
    # Validate input file exists
    if not os.path.exists(args.api_spec):
        logger.error(f"Error: API spec file not found: {args.api_spec}")
        sys.exit(1)
    
    # Generate code
    try:
        # Check if we're already in an event loop (e.g., from Jupyter/IPython)
        try:
            loop = asyncio.get_running_loop()
            logger.warning("⚠️ Already in an event loop. This may cause issues.")
            logger.warning("Consider running this script directly, not from within an async context.")
            # Try to use nest_asyncio if available, otherwise fail gracefully
            try:
                import nest_asyncio
                nest_asyncio.apply()
                logger.info("✅ Applied nest_asyncio to allow nested event loops")
            except ImportError:
                logger.error("❌ Cannot run in existing event loop. Please run this script directly.")
                logger.error("   Install nest_asyncio: pip install nest-asyncio")
                sys.exit(1)
        except RuntimeError:
            # No running event loop, we're good to use asyncio.run()
            pass
        
        # Use asyncio.run() which handles event loop creation/cleanup
        output_path = asyncio.run(
            generate_mcp_code(
                args.api_spec, 
                args.output, 
                args.model,
                incremental=args.incremental,
                tools_per_batch=args.tools_per_batch,
                max_tools=args.max_tools,
                validator_url=validator_url,
                max_validation_iterations=max_validation_iterations
            )
        )
        
        if args.run:
            run_generated_server(output_path, args.port)
        else:
            logger.info(f"\nGenerated code saved to: {output_path}")
            logger.info("You can run it with: python " + output_path)
            
    except KeyboardInterrupt:
        logger.info("\n⚠️ Interrupted by user")
        sys.exit(1)
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            logger.error("❌ Cannot run asyncio.run() from within an existing event loop.")
            logger.error("   Please run this script directly: python agent_mcp_generator.py <spec_file>")
            logger.error("   Or install nest_asyncio: pip install nest-asyncio")
        else:
            logger.error(f"Runtime error: {e}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

