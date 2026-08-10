# How Agent-Based API to MCP Conversion Works

This document explains the agent-based conversion process in detail.

## Agent-Based Conversion Process

### Step-by-Step Flow

```
API Spec JSON
    ↓
ADK Agent (with code generation tools)
    ↓
Agent Reads API Spec
    ↓
Agent Analyzes Structure
    ↓
Agent Generates Python Code
    ├─ FastMCP imports
    ├─ Server initialization
    ├─ Tool functions for each endpoint
    └─ Server run code
    ↓
Write Generated Code to File
    ↓
Generated Python File (runnable)
```

## Agent Instruction

The agent is given detailed instructions to:
1. Read the API specification
2. Understand the structure (OpenAPI or Postman)
3. Generate complete FastMCP server code
4. Handle all edge cases
5. Include proper error handling
6. Write the code to a file

## Agent Tools

1. **read_api_spec_tool**: Reads API specification files
2. **write_code_tool**: Writes generated Python code to files

## Example Agent Prompt

```
Please analyze the API specification at 'sample-data/example_api_spec.json' and generate 
a complete FastMCP server Python script.

The generated code should:
1. Read the API specification using read_api_spec_tool
2. Generate a complete FastMCP server with all endpoints as tools
3. Save the generated code to 'mcp_server_generated.py' using write_code_tool
```

## Conversion Examples

### Example 1: Simple GET Endpoint

**Input (OpenAPI):**
```json
{
  "paths": {
    "/posts": {
      "get": {
        "operationId": "get_posts",
        "parameters": [
          {
            "name": "userId",
            "in": "query",
            "schema": {"type": "integer"}
          }
        ]
      }
    }
  }
}
```

**Agent-Generated Output:**
```python
@mcp.tool()
async def get_posts(userId: int = None) -> dict:
    """Get all posts, optionally filtered by user ID."""
    url = "https://jsonplaceholder.typicode.com/posts"
    async with httpx.AsyncClient() as client:
        params = {}
        if userId is not None:
            params["userId"] = userId
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
```

### Example 2: POST with Request Body

**Input (Postman):**
```json
{
  "name": "create_post",
  "method": "POST",
  "path": "/posts",
  "parameters": [
    {"name": "title", "type": "string"},
    {"name": "body", "type": "string"},
    {"name": "userId", "type": "integer"}
  ]
}
```

**Agent-Generated Output:**
```python
@mcp.tool()
async def create_post(title: str, body: str, userId: int) -> dict:
    """Create a new post."""
    url = "http://aliwalay-001-site3.atempurl.com/posts"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json={"title": title, "body": body, "userId": userId},
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
```

## Technical Details

### Parameter Handling

**Path Parameters:**
- Detected in URL: `/api/posts/{id}`
- Replaced in URL: `url.replace("{id}", str(id))`

**Query Parameters:**
- Added to `params` dict for GET/DELETE
- Ignored for POST/PUT/PATCH (unless no body)

**Request Body:**
- Extracted from `requestBody` (OpenAPI) or inferred (Postman)
- Sent as JSON for POST/PUT/PATCH
- All non-path params become body params if body expected

### Error Handling

Agent can add custom error handling, logging, retries, etc. based on the API structure and requirements.

## Advantages of Agent-Based Generation

1. **Adaptability**: LLM can handle edge cases and unusual API structures
2. **Code Review**: Generated code can be reviewed and modified before use
3. **Customization**: Agent can add custom logic, error handling, or features
4. **Debugging**: Static code is easier to debug than runtime-generated tools
5. **Version Control**: Generated code can be committed to version control
6. **Reusability**: Generated server can be used independently

## Workflow

1. **Generate**: Run `agent_mcp_generator.py` with your API spec
2. **Review**: Check the generated code for correctness
3. **Customize** (optional): Modify the generated code as needed
4. **Run**: Execute the generated server
5. **Version Control** (optional): Commit the generated code

## Future Enhancements

Potential improvements:
1. Code validation before execution
2. Template-based generation with agent customization
3. Support for more API formats
4. Automatic testing of generated servers
5. Integration with ADK agents that use the generated MCP server
