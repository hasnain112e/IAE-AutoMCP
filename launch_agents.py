#!/usr/bin/env python3
"""
Launch All Agents

Starts all agents for the integrated agentic MCP system.
"""
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from agents.generator.generator_agent import GeneratorAgent
from agents.validator.validator_agent import ValidatorAgent
from agents.ui_controller.ui_controller_agent import UIControllerAgent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentLauncher:
    """Manages launching and stopping all agents"""

    def __init__(self):
        self.agents = []
        self.tasks = []
        self.running = False

    async def start_all(self):
        """Start all agents"""
        logger.info("=" * 60)
        logger.info("Starting IAE-AutoMCP Integrated Agentic System")
        logger.info("=" * 60)

        # Create agents
        # Use 127.0.0.1 to avoid Windows localhost/::1 resolution issues that can
        # break service-to-service connectivity when one process binds only IPv4.
        orchestrator = OrchestratorAgent(host="127.0.0.1", port=8100)
        generator = GeneratorAgent(host="127.0.0.1", port=8101)
        validator = ValidatorAgent(host="127.0.0.1", port=8002)
        ui_controller = UIControllerAgent(host="127.0.0.1", port=8102)

        self.agents = [orchestrator, generator, validator, ui_controller]

        # Start all agents in parallel
        logger.info("\nStarting agents...")
        self.tasks = [
            asyncio.create_task(orchestrator.run(), name="orchestrator"),
            asyncio.create_task(generator.run(), name="generator"),
            asyncio.create_task(validator.run(), name="validator"),
            asyncio.create_task(ui_controller.run(), name="ui_controller"),
        ]

        self.running = True

        logger.info("\n" + "=" * 60)
        logger.info("All agents started successfully!")
        logger.info("=" * 60)
        logger.info("\nAgent URLs:")
        logger.info("  Orchestrator:   http://127.0.0.1:8100")
        logger.info("  Generator:      http://127.0.0.1:8101")
        logger.info("  Validator:      http://127.0.0.1:8002")
        logger.info("  UI Controller:  http://127.0.0.1:8102 (WebSocket: ws://127.0.0.1:8102/ws)")
        logger.info("\nPress Ctrl+C to stop all agents")
        logger.info("=" * 60 + "\n")

        # Wait for all tasks
        try:
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            logger.info("\nShutting down agents...")
        except Exception as e:
            logger.error(f"Error running agents: {e}")

    async def stop_all(self):
        """Stop all agents"""
        if not self.running:
            return

        logger.info("\nStopping all agents...")

        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Stop all agents
        for agent in self.agents:
            try:
                await agent.stop()
            except Exception as e:
                logger.error(f"Error stopping {agent.name}: {e}")

        self.running = False
        logger.info("All agents stopped")


async def main():
    """Main entry point"""
    launcher = AgentLauncher()

    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("\nReceived interrupt signal...")
        asyncio.create_task(launcher.stop_all())

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        await launcher.start_all()
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
    finally:
        await launcher.stop_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nExiting...")
        sys.exit(0)
