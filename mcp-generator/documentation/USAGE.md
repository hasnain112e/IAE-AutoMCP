# Agent-Based MCP Code Generation - Usage Guide

This guide explains how to use the agent-based approach to convert API specifications into MCP servers.

## Overview

The `agent_mcp_generator.py` script uses an ADK agent to analyze API specifications and generate complete FastMCP server Python code.

## Installation

From the project root:
```bash
pip install -r requirements.txt
```

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

### Generate with Custom Output Path

```bash
python agent_mcp_generator.py sample-data/example_api_spec.json --output my_mcp_server.py
```

### Generate and Run

```bash
python agent_mcp_generator.py sample-data/example_api_spec.json --run --port 8000
```

### Command Line Options

- `api_spec`: Path to API specification file (OpenAPI or Postman format) - **required**
- `--output`: Path to save generated code (default: `mcp_server_generated.py`)
- `--model`: Model to use for code generation (default: `gemini-2.0-flash`)
- `--run`: Run the generated server after generation
- `--port`: Port for running the server (if `--run` is used, default: `8000`)

## Supported Formats

### OpenAPI Format

The `sample-data/example_api_spec.json` file contains a sample OpenAPI 3.0 specification that demonstrates:
- GET, POST, PUT, DELETE operations
- Path parameters
- Query parameters
- Request bodies
- Multiple endpoints

### Postman Collection Format

The `sample-data/example_postman_format.json` file contains a sample Postman collection format that demonstrates:
- Tools array with API endpoints
- Method, path, and description for each endpoint
- Tags for categorization
- Metadata with base_url
- Parameters (if any)

Example structure:
```json
{
  "source_type": "PostmanCollectionParser",
  "tools": [
    {
      "name": "tool_name",
      "description": "Tool description",
      "method": "GET",
      "path": "/api/endpoint",
      "tags": ["tag1", "tag2"],
      "parameters": [],
      "metadata": {
        "base_url": "http://example.com",
        "source": "postman_collection"
      }
    }
  ]
}
```

## How It Works

1. **Agent Creation**: An ADK agent is created with code generation tools
2. **API Analysis**: Agent reads and analyzes the API specification
3. **Code Generation**: Agent generates complete FastMCP server Python code
4. **Code Saving**: Generated code is saved to a file
5. **Execution** (optional): The generated code can be run independently

## Architecture

```
API Spec → ADK Agent → Generated Python Code → MCP Server
```

- **ADK Agent**: Analyzes API spec and generates code
- **Generated Code**: Complete, runnable FastMCP server
- **MCP Server**: Exposes API endpoints as tools

## Advantages

- **Adaptable**: LLM can handle edge cases and unusual API structures
- **Reviewable**: Generated code can be reviewed and modified before use
- **Customizable**: Agent can add custom logic, error handling, or features
- **Debuggable**: Static code is easier to debug than runtime-generated tools
- **Version Control**: Generated code can be committed to version control

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

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8000, path="/mcp")
```

## Notes

- The agent automatically handles path parameters, query parameters, and request bodies
- HTTP methods supported: GET, POST, PUT, PATCH, DELETE
- The generated server uses streamable-http transport
- You can review and modify the generated code before running it
