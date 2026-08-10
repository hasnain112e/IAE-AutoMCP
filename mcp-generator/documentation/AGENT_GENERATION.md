# Agent-Based MCP Code Generation

This document explains how the agent-based MCP code generation works.

## Overview

The `agent_mcp_generator.py` script uses an ADK agent to **generate** MCP server code from API specifications. The agent analyzes the API spec and generates complete, runnable Python code for a FastMCP server.

## How It Works

The agent-based approach:
1. Uses an ADK agent to analyze the API spec
2. Agent generates complete Python code for an MCP server
3. Saves the generated code to a file
4. The generated file can be run independently

**Flow:**
```
API Spec → ADK Agent → Generated Python Code → MCP Server (from code)
```

## Key Advantages

| Aspect | Benefit |
|--------|---------|
| **Code Generation** | Static Python code generation that can be reviewed |
| **Flexibility** | LLM can adapt to edge cases and unusual API structures |
| **Output** | Python source file that can be modified and version controlled |
| **Customization** | Agent can add custom logic, error handling, or features |
| **Debugging** | Can review/edit generated code before execution |
| **Reusability** | Generated code is reusable and can be committed to version control |

## Usage

### Generate MCP Server Code

From the `mcp-generator` directory:
```bash
cd mcp-generator
python agent_mcp_generator.py sample-data/example_api_spec.json
```

This will:
1. Create an ADK agent with code generation capabilities
2. Agent reads and analyzes the API spec
3. Agent generates complete FastMCP server code
4. Saves to `mcp_server_generated.py` (or custom path with `--output`)

### Generate and Run

```bash
python agent_mcp_generator.py sample-data/example_api_spec.json --run --port 8000
```

### Custom Output Path

```bash
python agent_mcp_generator.py sample-data/example_api_spec.json --output my_mcp_server.py
```

## Agent Capabilities

The agent is instructed to:
- Analyze API specifications (OpenAPI or Postman format)
- Generate complete, runnable FastMCP server code
- Handle all endpoint types (GET, POST, PUT, DELETE, etc.)
- Properly handle path parameters, query parameters, and request bodies
- Include error handling and type hints
- Generate proper docstrings

## Example Generated Code

The agent generates code like this:

```python
from fastmcp import FastMCP
import httpx

mcp = FastMCP("API Server Name")

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
        data = response.json()
        # FastMCP requires dict, wrap list in dict
        if isinstance(data, list):
            return {"result": data}
        return data

@mcp.tool()
async def create_post(title: str, body: str, userId: int) -> dict:
    """Create a new post."""
    url = "https://jsonplaceholder.typicode.com/posts"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json={"title": title, "body": body, "userId": userId}
        )
        response.raise_for_status()
        return response.json()

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8000, path="/mcp")
```

## Advantages of Agent-Based Generation

1. **Adaptability**: LLM can handle edge cases and unusual API structures
2. **Code Review**: Generated code can be reviewed and modified before use
3. **Version Control**: Generated code can be committed to version control
4. **Customization**: Agent can add custom logic, error handling, or features
5. **Debugging**: Easier to debug static code than runtime-generated tools
6. **Reusability**: Generated server can be used independently

## Workflow

1. **Generate**: Run `agent_mcp_generator.py` with your API spec
2. **Review**: Check the generated code for correctness
3. **Customize** (optional): Modify the generated code as needed
4. **Run**: Execute the generated server
5. **Version Control** (optional): Commit the generated code to your repository

