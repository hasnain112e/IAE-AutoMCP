"""
Prompt Manager for MCP Code Generator

Centralized management of all prompts used by the MCP code generation agent.
This allows for easy customization and maintenance of prompts.
"""
import json


class PromptManager:
    """Manages all prompts for the MCP code generator agent."""
    
    @staticmethod
    def get_agent_instruction() -> str:
        """Get the main instruction prompt for the agent."""
        return """You are an expert Python developer specializing in creating MCP (Model Context Protocol) servers using FastMCP.

**CRITICAL: You MUST use the provided tools to complete this task.**

Your task is to analyze a specification file (API or SDK format) and generate a complete, working FastMCP server Python script.

**SPECIFICATION TYPES:**
1. **API Specifications**: Have HTTP methods (GET, POST, etc.) and paths, use httpx for HTTP requests
2. **SDK Specifications**: Have `metadata.source == "python_sdk"` with `sdk_module` and `sdk_function`, import and call Python SDK functions

**MANDATORY REQUIREMENT: DO NOT USE HARDCODED BASE URLs OR EXAMPLE URLs LIKE jsonplaceholder.typicode.com**
**You MUST generate code that reads from the JSON specification file dynamically at runtime.**

**Step-by-Step Process (MUST FOLLOW):**
1. **FIRST**: Use read_api_spec_tool to read the specification file
2. **SECOND**: Analyze the structure to determine if it's an API spec or SDK spec
   - Check if any tool has `metadata.source == "python_sdk"` to identify SDK specs
3. **THIRD**: Generate a complete Python script that loads the JSON file at runtime (NO HARDCODED URLs or SDK imports)
4. **FOURTH**: Use write_code_tool to save the generated code to the specified file path

**Code Requirements for API Specs:**
- Imports FastMCP, httpx, json, and os
- Creates a FastMCP server instance
- Includes a load_api_spec() function that reads the JSON file at runtime
- Converts each API endpoint into an MCP tool
- Each tool reads URL info dynamically from the loaded JSON spec
- Handle path parameters, query parameters, and request bodies correctly
- Use proper type hints for all parameters
- Include proper error handling
- Make the server runnable with streamable-http transport on port 8504

**Code Requirements for SDK Specs:**
- Imports FastMCP, json, os, and importlib (for dynamic SDK module imports)
- Creates a FastMCP server instance
- Includes a load_api_spec() function that reads the JSON file at runtime
- Dynamically imports SDK modules based on `metadata.sdk_module` from the spec
- Converts each SDK function into an MCP tool
- Each tool calls the SDK function with parameters from the spec
- Handle function parameters correctly (required/optional, types, defaults)
- Use proper type hints for all parameters
- Include proper error handling
- Make the server runnable with streamable-http transport on port 8504

**Code Generation Guidelines for API Specs:**
- For OpenAPI format: Extract paths, methods, parameters, and request bodies
- For Postman format: Extract tools array with name, method, path, parameters, and metadata.base_url
- Each endpoint should become an async function decorated with @mcp.tool()
- Use httpx.AsyncClient for making HTTP requests
- Handle both GET/DELETE (query params) and POST/PUT/PATCH (JSON body) correctly
- Replace path parameters in URLs (e.g., path parameter id -> actual value)
- **CRITICAL**: FastMCP requires tools to return a dict, not a list. If the API returns a list, wrap it in a dict like: `return {"result": response.json()}` or `return {"data": response.json()}`
- If the API returns a dict, return it directly: `return response.json()`
- Include proper docstrings for each tool function
- **CRITICAL**: Always read the JSON spec file at runtime to get dynamic base URLs and endpoint information. Do not hardcode base URLs.

**Code Generation Guidelines for SDK Specs:**
- Each SDK function should become an async function decorated with @mcp.tool()
- **CRITICAL**: FastMCP does NOT support `**kwargs` in tool functions. ALL parameters MUST be explicitly defined in the function signature.
- Dynamically import the SDK module using importlib: `import importlib; sdk_module = importlib.import_module(tool_info['metadata']['sdk_module'])`
- Call the SDK function: `result = sdk_module.tool_info['metadata']['sdk_function'](param1=param1, param2=param2, ...)`
- Handle both sync and async SDK functions (wrap sync functions in asyncio.to_thread if needed)
- Map ALL parameters from the spec to explicit function arguments in the signature
- For required parameters: `param_name: type` (e.g., `apikey: str`)
- For optional parameters: `param_name: type = default_value` (e.g., `limit: int = 10`)
- Convert parameter types appropriately (string -> str, integer -> int, boolean -> bool)
- Handle default values from the spec (convert string "True"/"False" to boolean, string numbers to int, etc.)
- **CRITICAL**: FastMCP requires tools to return a dict, not a list. If the SDK returns a list, wrap it: `return {"result": result}` or `return {"data": result}`
- If the SDK returns a dict, return it directly: `return result`
- Include proper docstrings for each tool function
- **CRITICAL**: Always read the JSON spec file at runtime to get SDK module and function names. Do not hardcode SDK imports.
- **CRITICAL**: DO NOT use `**kwargs` or `*args` in any tool function signature. All parameters must be explicitly named.

**Code Structure Requirements:**
1. Add a JSON loading function to read API spec at runtime
2. Extract base URLs and endpoint info dynamically from the JSON
3. Construct full URLs by combining base URLs from metadata with endpoint paths
4. Use the JSON file path as a relative reference (e.g., load the spec file next to the Python script)

**Example structure for API specs:**
```python
from fastmcp import FastMCP
import httpx
import json
import os

mcp = FastMCP("API Server Name")

def load_api_spec():
    \"\"\"Load API specification from JSON file.\"\"\"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    api_spec_filename = os.environ.get('API_SPEC_FILENAME', 'api_spec.json')
    spec_file = os.path.join(script_dir, api_spec_filename)
    with open(spec_file, 'r') as f:
        return json.load(f)

API_SPEC = load_api_spec()

@mcp.tool()
async def endpoint_name(param1: str, param2: int) -> dict:
    \"\"\"Description of what this endpoint does.\"\"\"
    tool_info = next((tool for tool in API_SPEC if tool['name'] == 'endpoint_name'), None)
    if not tool_info:
        raise ValueError(f"Tool 'endpoint_name' not found in API spec")
    
    base_url = tool_info['metadata'].get('base_url', '')
    path = tool_info.get('path', '')
    method = tool_info.get('method', 'GET').upper()
    url = base_url.rstrip('/') + '/' + path.lstrip('/')
    
    async with httpx.AsyncClient() as client:
        query_params = dict(param2=param2) if param2 else dict()
        if method == 'GET':
            response = await client.get(url, params=query_params)
        elif method == 'POST':
            response = await client.post(url, json=dict(param1=param1, param2=param2))
        else:
            response = await client.request(method, url, params=query_params)
            
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return dict(result=data)
        return data

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8504, path="/mcp")
```

**Example structure for SDK specs:**
```python
from fastmcp import FastMCP
import json
import os
import importlib
import asyncio

mcp = FastMCP("SDK Server Name")

def load_api_spec():
    \"\"\"Load SDK specification from JSON file.\"\"\"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    api_spec_filename = os.environ.get('API_SPEC_FILENAME', 'sdk_spec.json')
    spec_file = os.path.join(script_dir, api_spec_filename)
    with open(spec_file, 'r') as f:
        return json.load(f)

API_SPEC = load_api_spec()

# Cache for imported SDK modules
_sdk_modules = {}

def get_sdk_module(module_name: str):
    \"\"\"Dynamically import and cache SDK module.\"\"\"
    if module_name not in _sdk_modules:
        _sdk_modules[module_name] = importlib.import_module(module_name)
    return _sdk_modules[module_name]

# IMPORTANT: Generate ONE @mcp.tool() function for EACH tool in the spec
# Each function MUST have ALL parameters explicitly defined in the signature
# DO NOT use **kwargs or *args in the function signature

@mcp.tool()
async def sdk_function_name(apikey: str, param1: str = None, param2: int = 10) -> dict:
    \"\"\"Description of what this SDK function does.\"\"\"
    tool_info = next((tool for tool in API_SPEC if tool['name'] == 'sdk_function_name'), None)
    if not tool_info:
        raise ValueError(f"Tool 'sdk_function_name' not found in SDK spec")
    
    # Get SDK module and function from spec
    sdk_module_name = tool_info['metadata'].get('sdk_module')
    sdk_function_name = tool_info['metadata'].get('sdk_function')
    
    if not sdk_module_name or not sdk_function_name:
        raise ValueError(f"SDK module or function not found in spec")
    
    # Dynamically import and call SDK function
    sdk_module = get_sdk_module(sdk_module_name)
    sdk_function = getattr(sdk_module, sdk_function_name)
    
    # Build call arguments - only include non-None values
    # The function signature above has explicit parameters, but we build kwargs for the SDK call
    call_kwargs = {'apikey': apikey}
    if param1 is not None:
        call_kwargs['param1'] = param1
    if param2 is not None:
        call_kwargs['param2'] = param2
    
    # Call SDK function (handle both sync and async)
    if asyncio.iscoroutinefunction(sdk_function):
        result = await sdk_function(**call_kwargs)
    else:
        result = await asyncio.to_thread(sdk_function, **call_kwargs)
    
    # FastMCP requires dict, wrap list in dict
    if isinstance(result, list):
        return dict(result=result)
    return result if isinstance(result, dict) else dict(data=result)

# Generate separate @mcp.tool() functions for each tool in the spec
# DO NOT try to dynamically create tools in a loop - FastMCP requires explicit function definitions
# DO NOT use asyncio.run() or any async execution at module level
# Each tool must be a separate, statically defined function with explicit parameters

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8504, path="/mcp")
```

**CRITICAL NOTES FOR SDK CODE GENERATION:**
- Generate ONE separate @mcp.tool() decorated function for EACH tool in the spec
- Each function signature MUST explicitly list ALL parameters (no **kwargs in signature)
- Use proper Python types: str, int, bool based on the spec's parameter types
- For optional parameters, use default values from the spec (convert string defaults appropriately)
- The function body can use **call_kwargs when calling the SDK function, but the function signature itself must have explicit parameters
- **ABSOLUTELY FORBIDDEN**: DO NOT create tools dynamically in a loop or using helper functions like `create_tool()`
- **ABSOLUTELY FORBIDDEN**: DO NOT use `asyncio.run()` or any async execution in the module-level code
- **REQUIRED**: Each tool must be a top-level function definition with @mcp.tool() decorator
- **REQUIRED**: Use simple string literals for docstrings, not f-strings or template strings
- Example of CORRECT structure:
  ```python
  @mcp.tool()
  async def tool_name_1(apikey: str, param1: str = None) -> dict:
      \"\"\"Description from spec.\"\"\"
      # implementation
  
  @mcp.tool()
  async def tool_name_2(apikey: str, param2: int = 10) -> dict:
      \"\"\"Another description.\"\"\"
      # implementation
  ```
- Example of FORBIDDEN structure (DO NOT DO THIS):
  ```python
  # DO NOT create tools in a loop
  for tool_info in API_SPEC:
      async def create_tool(tool_info):
          async def tool_function(**kwargs):  # NO **kwargs!
              pass
      asyncio.run(create_tool(tool_info))  # NO asyncio.run at module level!
  ```

**CRITICAL FINAL STEP - YOU MUST DO THIS:**
After generating the code, you MUST call write_code_tool with:
- file_path: The exact output path provided in the user's request
- code: The COMPLETE generated Python code (not a description, not a summary - the actual full code)

**DO NOT:**
- Just describe what the code should do
- Provide code snippets without calling write_code_tool
- Skip calling write_code_tool

**YOU MUST:**
- Generate the complete, working Python code
- Call write_code_tool with the full code
- Ensure the code is saved to the specified file path

**REMEMBER**: Your task is not complete until you have called write_code_tool to save the generated code."""

    @staticmethod
    def get_batch_processing_prompt(
        batch_num: int,
        total_batches: int,
        batch_start: int,
        batch_end: int,
        total_tools: int,
        tools_json: str,
        output_path: str
    ) -> str:
        """Get the prompt for batch processing."""
        num_tools_in_batch = batch_end - batch_start
        return f"""Generate MCP tool functions for batch {batch_num} of {total_batches}.

**BATCH PROCESSING CONTEXT:**
- This is batch {batch_num} out of {total_batches} total batches
- You are processing tools {batch_start+1} through {batch_end} (out of {total_tools} total tools)
- This batch contains {num_tools_in_batch} tool(s) that MUST ALL be generated in this single request
- The file already exists with header code and may contain tools from previous batches
- You MUST append to the existing file, NOT overwrite it
- After this batch, there will be more batches to process

**CRITICAL REQUIREMENTS - YOU MUST GENERATE ALL {num_tools_in_batch} TOOLS IN THIS SINGLE REQUEST:**
- Generate ALL {num_tools_in_batch} @mcp.tool() functions for ALL tools in THIS batch in ONE response
- You MUST call write_tool_function for EACH of the {num_tools_in_batch} tools in this batch
- Do NOT stop after generating just one tool - you must generate ALL {num_tools_in_batch} tools
- Each function MUST have ALL parameters explicitly defined (NO **kwargs in signature)
- Use proper type hints: str, int, bool based on parameter types
- For optional parameters, use default values from the spec
- Use simple string literals for docstrings

**IMPORTANT - FILE PATH:**
The output file path is: {output_path}
You MUST use this exact path when calling write_tool_function.

**Tools to generate:**
{tools_json}

**For SDK tools:**
- Dynamically import SDK module using get_sdk_module()
- Call SDK function with explicit parameters
- Handle both sync and async SDK functions
- Example structure:
```python
@mcp.tool()
async def tool_name(apikey: str, param1: str = None, param2: int = 10) -> dict:
    \"\"\"Tool description from spec.\"\"\"
    tool_info = next((tool for tool in API_SPEC if tool['name'] == 'tool_name'), None)
    if not tool_info:
        raise ValueError(f"Tool 'tool_name' not found in SDK spec")
    
    sdk_module_name = tool_info['metadata'].get('sdk_module')
    sdk_function_name = tool_info['metadata'].get('sdk_function')
    
    if not sdk_module_name or not sdk_function_name:
        raise ValueError(f"SDK module or function not found in spec")
    
    sdk_module = get_sdk_module(sdk_module_name)
    sdk_function = getattr(sdk_module, sdk_function_name)
    
    call_kwargs = {{'apikey': apikey}}
    if param1 is not None:
        call_kwargs['param1'] = param1
    if param2 is not None:
        call_kwargs['param2'] = param2
    
    if asyncio.iscoroutinefunction(sdk_function):
        result = await sdk_function(**call_kwargs)
    else:
        result = await asyncio.to_thread(sdk_function, **call_kwargs)
    
    if isinstance(result, list):
        return dict(result=result)
    return result if isinstance(result, dict) else dict(data=result)
```

**For API tools:**
- Extract URL from tool_info metadata
- Make HTTP request using httpx

**CRITICAL - YOU MUST GENERATE ALL {num_tools_in_batch} TOOLS IN THIS SINGLE REQUEST:**
1. Generate the complete @mcp.tool() function code for ALL {num_tools_in_batch} tools in this batch
2. For EACH of the {num_tools_in_batch} tools, call write_tool_function (NOT write_code_tool) with:
   - file_path: "{output_path}" (use this exact path)
   - tool_code: The complete function code (including @mcp.tool() decorator)
3. You MUST call write_tool_function exactly {num_tools_in_batch} times - once for each tool in this batch
4. Do NOT stop after generating just one tool - continue until all {num_tools_in_batch} tools are generated
5. Do NOT include imports, header code, or the if __name__ block
6. Each tool function should be complete and ready to append

**ABSOLUTELY FORBIDDEN:**
- DO NOT use write_code_tool for incremental generation (it will overwrite the file!)
- DO NOT use write_code_tool with append=True (use write_tool_function instead)
- DO NOT write the entire file content - only write individual tool functions
- DO NOT generate only one tool and stop - you must generate ALL {num_tools_in_batch} tools

**Example of what to generate and append:**
For EACH of the {num_tools_in_batch} tools in this batch, generate code like the SDK example above, then call:
write_tool_function(file_path="{output_path}", tool_code="<the complete function code>")

**REMEMBER: This is a SINGLE request that must generate ALL {num_tools_in_batch} tools. Generate and save ALL {num_tools_in_batch} tool functions for this batch NOW."""

    @staticmethod
    def get_non_incremental_prompt(api_spec_path: str, output_path: str) -> str:
        """Get the prompt for non-incremental code generation."""
        return f"""Please analyze the specification file at '{api_spec_path}' and generate a complete FastMCP server Python script.

**FIRST: Determine if this is an API spec or SDK spec:**
- Check if any tool in the spec has `metadata.source == "python_sdk"`
- If yes, it's an SDK spec - generate code that imports and calls Python SDK functions
- If no, it's an API spec - generate code that makes HTTP requests

CRITICAL REQUIREMENTS FOR API SPECS:
- DO NOT use any hardcoded URLs like "https://jsonplaceholder.typicode.com" or "https://api.example.com"
- MUST generate code that loads the JSON specification file at runtime
- MUST extract base URLs and paths dynamically from the JSON spec
- MUST include a load_api_spec() function that reads the JSON file
- MUST import json, os, and httpx modules for dynamic loading

CRITICAL REQUIREMENTS FOR SDK SPECS:
- DO NOT hardcode SDK module imports (e.g., `import fmpsdk`)
- MUST generate code that loads the JSON specification file at runtime
- MUST dynamically import SDK modules using importlib based on `metadata.sdk_module`
- MUST call SDK functions based on `metadata.sdk_function` from the spec
- MUST include a load_api_spec() function that reads the JSON file
- MUST import json, os, importlib, and asyncio modules
- MUST handle both sync and async SDK functions (use asyncio.to_thread for sync functions)
- **CRITICAL**: FastMCP does NOT support `**kwargs` in tool function signatures. ALL parameters from the spec MUST be explicitly defined in each function signature (e.g., `async def tool_name(param1: str, param2: int = 10) -> dict:`)
- For each tool, explicitly list ALL parameters from the spec in the function signature
- Use proper type hints (str, int, bool) based on parameter types in the spec
- Set default values for optional parameters based on the spec's default values
- **ABSOLUTELY FORBIDDEN**: DO NOT create tools dynamically in a loop, using helper functions, or with asyncio.run() at module level
- **REQUIRED**: Each tool must be a separate, statically defined top-level function with @mcp.tool() decorator
- **REQUIRED**: Use simple string literals for docstrings, NOT f-strings or template strings. Use plain text in triple quotes.

The generated code should:
1. Read the specification using read_api_spec_tool
2. Detect if it's an API or SDK spec
3. For API specs: Include imports: from fastmcp import FastMCP, import httpx, import json, import os
4. For SDK specs: Include imports: from fastmcp import FastMCP, import json, import os, import importlib, import asyncio
5. Include a load_api_spec() function that dynamically reads the JSON file
6. For API specs: Create tools that extract URLs from the loaded spec data at runtime
7. For SDK specs: Create tools that dynamically import SDK modules and call SDK functions
8. Generate a complete FastMCP server with all endpoints/functions as tools
9. Save the generated code to '{output_path}' using write_code_tool
10. The server must run on port 8504 (use port=8504 in mcp.run())

REMEMBER: NO HARDCODED URLs OR SDK IMPORTS - everything must be read from the JSON spec file dynamically.
REMEMBER: Use port 8504 for the MCP server (mcp.run(transport="streamable-http", host="127.0.0.1", port=8504, path="/mcp"))."""

    @staticmethod
    def get_batch_followup_prompt(output_path: str, tool_names: list, num_tools: int) -> str:
        """Get the follow-up prompt for batch processing when tools weren't written."""
        tool_names_json = json.dumps(tool_names, indent=2)
        return f"""You MUST call write_tool_function to save the tool function(s) for this batch.

**CRITICAL**: The output file path is: {output_path}

The tools in this batch are:
{tool_names_json}

**You MUST:**
1. Generate ONE @mcp.tool() function for EACH tool listed above
2. For EACH function, call write_tool_function with:
   - file_path: "{output_path}" (use this exact path)
   - tool_code: The complete function code including @mcp.tool() decorator

**Example call:**
write_tool_function(file_path="{output_path}", tool_code="@mcp.tool()\\nasync def tool_name(...):\\n    ...")

Generate and save ALL {num_tools} tool function(s) NOW."""

    @staticmethod
    def get_non_incremental_followup_prompt(output_path: str) -> str:
        """Get the follow-up prompt for non-incremental generation when code wasn't written."""
        return f"""You MUST call write_code_tool to save the generated code.

CRITICAL: You have analyzed the specification but have NOT saved the code yet.

You MUST:
1. Generate the complete FastMCP server Python code
2. Call write_code_tool with:
   - file_path: "{output_path}"
   - code: <the complete generated Python code>

DO NOT just describe the code - you MUST actually call write_code_tool with the full code.

The code should be a complete, runnable Python script that:
- Imports necessary modules
- Loads the spec file dynamically
- Creates FastMCP tools for each endpoint/function
- Runs on port 8504

Call write_code_tool NOW with the complete generated code."""

    @staticmethod
    def get_regeneration_prompt(
        api_spec_path: str,
        output_path: str,
        feedback: dict,
        iteration: int
    ) -> str:
        """Get the prompt for regenerating code based on validation feedback.
        
        Args:
            api_spec_path: Path to the original API/SDK specification file
            output_path: Path where the code should be saved
            feedback: Validation feedback dict with approved, errors, warnings, suggestions
            iteration: Current regeneration iteration number
            
        Returns:
            Prompt string for regenerating code with feedback
        """
        feedback_text = ""
        if feedback.get("errors"):
            feedback_text += "**CRITICAL ERRORS TO FIX:**\n"
            for i, error in enumerate(feedback["errors"], 1):
                feedback_text += f"{i}. {error}\n"
            feedback_text += "\n"
        
        if feedback.get("warnings"):
            feedback_text += "**WARNINGS TO ADDRESS:**\n"
            for i, warning in enumerate(feedback["warnings"], 1):
                feedback_text += f"{i}. {warning}\n"
            feedback_text += "\n"
        
        if feedback.get("suggestions"):
            feedback_text += "**SUGGESTIONS FOR IMPROVEMENT:**\n"
            for i, suggestion in enumerate(feedback["suggestions"], 1):
                feedback_text += f"{i}. {suggestion}\n"
            feedback_text += "\n"
        
        if not feedback_text:
            feedback_text = "The validator provided feedback but no specific issues were listed. Please review the code carefully and ensure it meets all requirements.\n\n"
        
        return f"""You previously generated MCP server code, but the validator found issues that need to be fixed.

**REGENERATION CONTEXT:**
- This is regeneration iteration {iteration}
- The original specification file is: {api_spec_path}
- The code should be saved to: {output_path}
- Previous code generation had validation issues that must be addressed

**VALIDATION FEEDBACK:**
{feedback_text}

**CRITICAL REQUIREMENTS:**
1. Read the original specification file using read_api_spec_tool
2. Address ALL errors listed above - these are critical and must be fixed
3. Address warnings if possible
4. Consider suggestions for improvement
5. Generate COMPLETE, corrected code that fixes all the issues
6. Use write_code_tool to save the corrected code to {output_path}

**IMPORTANT:**
- Do NOT make the same mistakes as before
- Carefully review each error and ensure it's fixed in the new code
- Generate the complete file, not just patches or fixes
- Ensure the code is syntactically correct and follows all requirements from the original specification

**YOU MUST:**
- Generate the complete, corrected FastMCP server Python code
- Call write_code_tool with the full corrected code
- Ensure all validation errors are addressed

Call write_code_tool NOW with the complete corrected code."""



