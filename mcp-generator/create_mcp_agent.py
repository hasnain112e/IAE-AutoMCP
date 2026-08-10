#!/usr/bin/env python3
"""
Create an ADK agent that uses an MCP server.

This script creates an ADK agent that connects to a running MCP server
and can use all the tools exposed by that server.
"""

# Load environment variables from .env file FIRST, before any other imports
# This ensures the API key is available when ADK initializes the Google client
from dotenv import load_dotenv
load_dotenv()

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.utils.context_utils import Aclosing
from google.genai import types

try:
    from google.adk.a2a.utils.agent_to_a2a import to_a2a
    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mcp_agent(
    mcp_url: str,
    model: str = "gemini-2.0-flash",
    agent_name: str = "mcp_api_agent",
    instruction: str = None
) -> LlmAgent:
    """Create an ADK agent that uses an MCP server.

    Args:
        mcp_url: URL of the MCP server (e.g., "http://localhost:8000/mcp")
        model: Model to use for the agent
        agent_name: Name for the agent
        instruction: Custom instruction for the agent (optional)

    Returns:
        Configured LlmAgent
    """
    # Create MCP toolset connection
    connection_params = StreamableHTTPConnectionParams(
        url=mcp_url,
        timeout=30.0,
        sse_read_timeout=300.0,
    )
    
    mcp_toolset = McpToolset(connection_params=connection_params)
    
    # Default instruction if not provided
    if instruction is None:
        instruction = (
            "You are an API assistant agent. You can query and interact with "
            "APIs through the available MCP tools. Use the tools to make API calls "
            "and help users accomplish their tasks. When a user asks you to do something "
            "that requires an API call, use the appropriate tool from the available MCP tools."
        )
    
    # Create agent
    agent = LlmAgent(
        name=agent_name,
        model=model,
        instruction=instruction,
        description="An agent that can interact with APIs through MCP tools",
        tools=[mcp_toolset],
    )
    
    return agent


async def run_agent_interactive(agent: LlmAgent):
    """Run agent in interactive mode."""
    runner = Runner(
        app_name=agent.name,
        agent=agent,
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )
    
    print(f"\n{'='*60}")
    print(f"🤖 {agent.name} is ready!")
    print(f"{'='*60}")
    print("Type 'quit' or 'exit' to stop.\n")
    
    # Create session
    session = await runner.session_service.create_session(
        app_name=agent.name,
        user_id="user",
    )
    
    while True:
        try:
            user_input = input("\nYou: ").strip()
            if user_input.lower() in ["quit", "exit", "q"]:
                print("\nGoodbye!")
                break
            
            if not user_input:
                continue
            
            # Create message content
            message_content = types.Content(
                role="user",
                parts=[types.Part(text=user_input)]
            )
            
            # Run agent
            print("\n" + "="*60)
            print("***** AGENT RESPONSE START *****")
            print("="*60 + "\n")
            async with Aclosing(
                runner.run_async(
                    session_id=session.id,
                    user_id="user",
                    new_message=message_content,
                )
            ) as event_generator:
                async for event in event_generator:
                    # Print agent responses
                    if event.content and event.content.parts:
                        text = "".join(part.text or "" for part in event.content.parts)
                        if text:
                            print(text, end="", flush=True)
            
            print("\n" + "="*60)
            print("***** AGENT RESPONSE END *****")
            print("="*60)
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            print(f"\n❌ Error: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create an ADK agent that uses an MCP server"
    )
    parser.add_argument(
        "--mcp-url",
        type=str,
        default="http://localhost:8504/mcp",
        help="URL of the MCP server (default: http://localhost:8504/mcp)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.0-flash",
        help="Model to use for ADK agent (default: gemini-2.0-flash)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="mcp_api_agent",
        help="Name for the agent (default: mcp_api_agent)",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        default=None,
        help="Custom instruction for the agent (optional)",
    )
    parser.add_argument(
        "--a2a",
        action="store_true",
        help="Expose agent via A2A protocol",
    )
    parser.add_argument(
        "--a2a-port",
        type=int,
        default=8001,
        help="Port for A2A agent server (default: 8001)",
    )
    
    args = parser.parse_args()
    
    logger.info(f"Creating ADK agent that connects to MCP server at {args.mcp_url}...")
    
    # Create agent
    agent = create_mcp_agent(
        mcp_url=args.mcp_url,
        model=args.model,
        agent_name=args.name,
        instruction=args.instruction
    )
    
    if args.a2a:
        if not A2A_AVAILABLE:
            logger.error("A2A protocol is not available. Please install required dependencies.")
            sys.exit(1)
        
        # Expose agent via A2A protocol
        import uvicorn
        a2a_app = to_a2a(agent, host="0.0.0.0", port=args.a2a_port, protocol="http")
        logger.info(f"Starting A2A agent server on port {args.a2a_port}...")
        logger.info(f"A2A agent will be available at http://localhost:{args.a2a_port}/")
        uvicorn.run(a2a_app, host="0.0.0.0", port=args.a2a_port)
    else:
        # Run in interactive mode
        logger.info("Starting interactive agent...")
        asyncio.run(run_agent_interactive(agent))


if __name__ == "__main__":
    main()

