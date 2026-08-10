#!/usr/bin/env python3
"""
Quick test script to verify A2A communication with the validator.
Run this after starting test_validator_agent.py to verify connectivity.
"""

import asyncio
import httpx
import json
import sys

VALIDATOR_URL = "http://localhost:8001"

SAMPLE_CODE = """
from fastmcp import FastMCP

mcp = FastMCP("sample_server")

@mcp.tool()
async def get_data(query: str) -> dict:
    \"\"\"Get some data.\"\"\"
    return {"query": query, "result": "sample"}

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8504)
"""


async def test_a2a_endpoint():
    """Test the /a2a endpoint with JSON-RPC 2.0 format."""
    print("Testing /a2a endpoint (JSON-RPC 2.0)...")
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "message": {
                "messageId": "test-123",
                "contextId": "test_validation",
                "taskId": "validate_mcp_code",
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": f"Please validate this code:\n```python\n{SAMPLE_CODE}\n```"
                    }
                ]
            }
        },
        "id": "test-request-1"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{VALIDATOR_URL}/a2a",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            
            print("✅ SUCCESS!")
            print(f"Response: {json.dumps(data, indent=2)}")
            
            # Check if it's JSON-RPC response
            if data.get("jsonrpc") == "2.0":
                print("\n✅ Valid JSON-RPC 2.0 response")
                result = data.get("result", {})
                print(f"   Approved: {result.get('approved')}")
                print(f"   Errors: {len(result.get('errors', []))}")
                print(f"   Warnings: {len(result.get('warnings', []))}")
                print(f"   Suggestions: {len(result.get('suggestions', []))}")
            
            return True
            
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


async def test_simple_endpoint():
    """Test the /chat endpoint with simple JSON format."""
    print("\nTesting /chat endpoint (Simple JSON)...")
    
    payload = {
        "code": SAMPLE_CODE,
        "iteration": 1
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{VALIDATOR_URL}/chat",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            
            print("✅ SUCCESS!")
            print(f"Response: {json.dumps(data, indent=2)}")
            
            print(f"\n   Approved: {data.get('approved')}")
            print(f"   Errors: {len(data.get('errors', []))}")
            print(f"   Warnings: {len(data.get('warnings', []))}")
            print(f"   Suggestions: {len(data.get('suggestions', []))}")
            
            return True
            
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("A2A Validator Communication Test")
    print("=" * 60)
    print(f"\nValidator URL: {VALIDATOR_URL}")
    print("\nMake sure test_validator_agent.py is running!")
    print("  Start it with: python test_validator_agent.py --port 8001")
    print("\n" + "=" * 60)
    
    results = []
    
    # Test A2A endpoint
    results.append(await test_a2a_endpoint())
    
    # Test simple endpoint
    results.append(await test_simple_endpoint())
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✅ All tests passed! A2A communication is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Check if validator is running.")
        return 1


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
