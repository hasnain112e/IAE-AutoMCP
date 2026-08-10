#!/usr/bin/env python3
"""
Monitor A2A (Agent-to-Agent) communication between MCP Generator and Validator.
Shows the complete A2A protocol flow.
"""
import requests
import json
import time
import sys

def test_a2a_communication():
    """Test and monitor A2A communication."""
    
    print("=" * 70)
    print("🔄 TESTING A2A (AGENT-TO-AGENT) COMMUNICATION")
    print("=" * 70)
    
    # Test code
    code = """
from fastmcp import FastMCP

mcp = FastMCP("Test Server")

@mcp.tool()
async def test_tool(name: str) -> str:
    \"\"\"A test tool.\"\"\"
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
"""
    
    print("\n📝 Test Code:")
    print(code)
    
    # Test 1: Health Check
    print("\n" + "=" * 70)
    print("1️⃣  HEALTH CHECK")
    print("=" * 70)
    
    try:
        health = requests.get("http://localhost:8002/health", timeout=5)
        health_data = health.json()
        print(f"✅ Status: {health_data.get('status')}")
        print(f"🧠 LLM Available: {health_data.get('llm_available')}")
        print(f"📡 A2A Available: {health_data.get('a2a_available')}")
        
        if not health_data.get('llm_available'):
            print("\n⚠️  WARNING: LLM not available. Agentic validation may not work.")
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot connect to validator")
        print("   Start validator: cd IAE-AutoMCP-Mcp_super_Validator && python http_server.py --port 8002")
        sys.exit(1)
    
    # Test 2: A2A Protocol (JSON-RPC 2.0)
    print("\n" + "=" * 70)
    print("2️⃣  A2A PROTOCOL TEST (JSON-RPC 2.0)")
    print("=" * 70)
    
    a2a_request = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "message": {
                "messageId": f"test-{int(time.time())}",
                "contextId": "a2a-test-1",
                "taskId": "validate_code",
                "role": "user",
                "parts": [{
                    "kind": "text",
                    "text": f"Please validate this MCP server code:\n```python\n{code}\n```"
                }],
                "metadata": {
                    "iteration": 1,
                    "code_length": len(code)
                }
            }
        },
        "id": f"req-{int(time.time())}"
    }
    
    print("\n📤 Sending A2A request...")
    print(f"   Message ID: {a2a_request['params']['message']['messageId']}")
    print(f"   Context ID: {a2a_request['params']['message']['contextId']}")
    
    try:
        response = requests.post(
            "http://localhost:8002/a2a",
            json=a2a_request,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"\n📥 Response Status: {response.status_code}")
        
        if result.get("jsonrpc") == "2.0":
            print("✅ JSON-RPC 2.0 format confirmed")
            
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                validation_result = result.get("result", {})
                print(f"\n✅ A2A Communication Successful!")
                print(f"   Approved: {validation_result.get('approved')}")
                print(f"   Issues: {len(validation_result.get('issues', []))}")
                
                if validation_result.get('llm_validation'):
                    print(f"   🧠 Agentic validation: YES")
                    llm = validation_result['llm_validation']
                    if llm.get('reasoning'):
                        print(f"   💭 Reasoning: Available")
                    if llm.get('risk_assessment'):
                        print(f"   ⚠️  Risk Assessment: Available")
        else:
            print(f"⚠️  Unexpected response format")
            print(json.dumps(result, indent=2)[:500])
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)
    
    # Test 3: Simple JSON (Fallback)
    print("\n" + "=" * 70)
    print("3️⃣  SIMPLE JSON TEST (Fallback)")
    print("=" * 70)
    
    simple_request = {
        "code": code,
        "iteration": 1,
        "use_llm": True
    }
    
    print("\n📤 Sending simple JSON request...")
    
    try:
        response = requests.post(
            "http://localhost:8002/chat",
            json=simple_request,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ Response received")
        print(f"   Approved: {result.get('approved')}")
        print(f"   Issues: {len(result.get('issues', []))}")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    print("\n✅ A2A Communication Test Complete!")
    print("\nTo see A2A in action with MCP Generator:")
    print("  1. Keep validator running (Terminal 1)")
    print("  2. In Terminal 2, run:")
    print("     cd mcp-generator")
    print("     python agent_mcp_generator.py <spec.json> --use-super-validator --validator-url http://localhost:8002")
    print("\nWatch Terminal 1 to see A2A requests coming in!")
    print("=" * 70)

if __name__ == "__main__":
    test_a2a_communication()

