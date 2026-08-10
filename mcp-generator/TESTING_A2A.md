# Testing A2A Validation

This guide explains how to test the A2A (Agent-to-Agent) validation feature for the MCP generator.

## Overview

The A2A validation feature allows the MCP generator to:
1. Generate MCP server code
2. Send the code to a validator agent via HTTP (JSON-RPC 2.0 protocol)
3. Receive structured feedback (errors, warnings, suggestions)
4. Regenerate the code based on feedback
5. Repeat until validation passes or max iterations reached

## Prerequisites

1. **Activate virtual environment:**
   ```powershell
   venv\Scripts\activate
   ```

2. **Install dependencies** (if not already installed):
   ```powershell
   pip install fastapi uvicorn httpx
   ```

3. **Ensure you have an API spec file:**
   - Example: `sdk_spec.json` or `fmpsdk_spec.json`

## Testing Steps

### Step 1: Start the Validator Agent

Open a **new terminal** (Terminal 1) and run:

```powershell
cd d:\Projects\IAE-AutoMCP\mcp-generator
venv\Scripts\activate
python test_validator_agent.py --port 8001
```

You should see:
```
Starting simple validator server on port 8001...
Endpoints available:
  - POST http://localhost:8001/a2a (JSON-RPC 2.0)
  - POST http://localhost:8001/chat (Simple JSON)
  - POST http://localhost:8001/ (Simple JSON)
INFO:     Started server process...
```

**Keep this terminal running!**

### Step 2: Run the Generator with Validation

Open **another terminal** (Terminal 2) and run:

```powershell
cd d:\Projects\IAE-AutoMCP\mcp-generator
venv\Scripts\activate
python agent_mcp_generator.py sdk_spec.json --validator-url http://localhost:8001
```

### Step 3: Observe the Validation Loop

You'll see output like:

```
INFO: Generated MCP server: mcp_server_generated.py
INFO: 🔄 Starting validation loop with A2A validator at http://localhost:8001
INFO: 📋 Validating generated code with A2A validator (iteration 1/3)...
INFO: ✅ Validation feedback received: approved=True, errors=0, warnings=2, suggestions=1
INFO: 🎉 Validation passed after 1 iteration(s)!
```

### Step 4: Check Validation Results

**If validation passes:**
- Generator exits successfully
- Generated code is in `mcp_server_generated.py`

**If validation fails:**
- Generator regenerates code
- You'll see iteration 2, 3, etc.
- After max iterations (default 3), generator exits with the last version

## Testing Scenarios

### Test 1: Basic Validation (Should Pass)

```powershell
python agent_mcp_generator.py sdk_spec.json --validator-url http://localhost:8001
```

Expected: Code generates correctly and passes validation in 1-2 iterations.

### Test 2: Custom Max Iterations

```powershell
python agent_mcp_generator.py sdk_spec.json --validator-url http://localhost:8001 --max-validation-iterations 5
```

Expected: Allows up to 5 regeneration attempts.

### Test 3: Without Validation

```powershell
python agent_mcp_generator.py sdk_spec.json
```

Expected: Generates code without validation (skips validator).

### Test 4: Using Environment Variables

Set in `.env` file:
```
VALIDATOR_A2A_URL=http://localhost:8001
MAX_VALIDATION_ITERATIONS=5
```

Then run:
```powershell
python agent_mcp_generator.py sdk_spec.json
```

Expected: Uses validator URL from environment variable.

## Understanding Validator Feedback

The validator checks for:

### Errors (Must fix - code won't be approved)
- Python syntax errors
- Missing FastMCP import
- Missing FastMCP instance creation
- No @mcp.tool() decorators

### Warnings (Should fix - code approved with warnings)
- Low number of tools
- Missing __main__ block
- Missing mcp.run() call
- Missing async def for tools

### Suggestions (Optional improvements)
- Add error handling (try/except)
- Add timeout to HTTP requests

## Checking Validation in Terminal 1

In the validator terminal, you'll see HTTP requests:

```
INFO:     127.0.0.1:xxxxx - "POST /a2a HTTP/1.1" 200 OK
```

## Troubleshooting

### Problem: "Failed to reach validator"

**Solution:**
1. Ensure validator is running (Terminal 1)
2. Check port is correct (default: 8001)
3. Check firewall isn't blocking localhost:8001

### Problem: "Connection refused"

**Solution:**
1. Validator isn't running - start it in Terminal 1
2. Wrong port - verify `--port` matches `--validator-url`

### Problem: "Validation failed after 3 iterations"

**Solution:**
1. Check the generated code in `mcp_server_generated.py`
2. Review error messages in the generator output
3. The validator might be too strict - adjust validation logic in `test_validator_agent.py`

### Problem: Generator hangs

**Solution:**
1. Check validator terminal for errors
2. Try Ctrl+C and restart both terminals
3. Increase timeout: edit `httpx.AsyncClient(timeout=60.0)` in `agent_mcp_generator.py`

## Advanced Testing

### Test with Different API Specs

```powershell
# Test with FMP SDK spec
python agent_mcp_generator.py fmpsdk_spec.json --validator-url http://localhost:8001

# Test with custom spec
python agent_mcp_generator.py sample-data/example_api_spec.json --validator-url http://localhost:8001
```

### Test JSON-RPC 2.0 Endpoint Directly

Use `curl` or Postman to test the validator:

```powershell
curl -X POST http://localhost:8001/a2a `
  -H "Content-Type: application/json" `
  -d '{
    "jsonrpc": "2.0",
    "method": "tasks/send",
    "params": {
      "message": {
        "messageId": "test-123",
        "contextId": "test",
        "taskId": "validate",
        "role": "user",
        "parts": [{
          "kind": "text",
          "text": "```python\nfrom fastmcp import FastMCP\nmcp = FastMCP(\"test\")\n@mcp.tool()\nasync def test(): pass\nif __name__ == \"__main__\":\n    mcp.run()\n```"
        }]
      }
    },
    "id": "req-1"
  }'
```

Expected response:
```json
{
  "jsonrpc": "2.0",
  "result": {
    "approved": true,
    "errors": [],
    "warnings": [...],
    "suggestions": [...]
  },
  "id": "req-1"
}
```

## Cleanup

When done testing:

1. Stop validator (Terminal 1): `Ctrl+C`
2. Stop generator if running (Terminal 2): `Ctrl+C`
3. Deactivate virtual environment: `deactivate`

## Next Steps

- Customize validation rules in `test_validator_agent.py` (function `validate_code()`)
- Adjust max iterations via CLI or environment variables
- Review generated code in `mcp_server_generated.py`
- Deploy your own production validator agent for real validation
