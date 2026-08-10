# Edited by Dr. Wasim
"""
Base Agent Class

Provides common functionality for all agents in the system.
"""
import asyncio
import logging
import time
import httpx
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime

from shared.a2a_protocol import (
    A2ARequest,
    A2AResponse,
    A2AMessage,
    MessageRole
)
from shared.message_types import AgentType, AgentMessage, AgentResponse

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all agents

    Provides:
    - A2A message handling
    - HTTP client for agent-to-agent communication
    - Logging and error handling
    - Agent lifecycle management
    """

    def __init__(
        self,
        agent_type: AgentType,
        name: str,
        host: str = "localhost",
        port: int = 8000,
        timeout: float = 120.0
    ):
        self.agent_type = agent_type
        self.name = name
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"
        self.running = False
        self.client: Optional[httpx.AsyncClient] = None
        self.logger = logging.getLogger(f"agent.{name}")

    async def start(self) -> None:
        """Start the agent"""
        if self.running:
            self.logger.warning(f"{self.name} already running")
            return

        self.logger.info(f"Starting {self.name} on {self.base_url}")
        self.client = httpx.AsyncClient(timeout=self.timeout)
        self.running = True
        await self.on_start()

    async def stop(self) -> None:
        """Stop the agent"""
        if not self.running:
            return

        self.logger.info(f"Stopping {self.name}")
        self.running = False
        await self.on_stop()

        if self.client:
            await self.client.aclose()
            self.client = None

    async def on_start(self) -> None:
        """Hook called when agent starts"""
        pass

    async def on_stop(self) -> None:
        """Hook called when agent stops"""
        pass

    @abstractmethod
    async def handle_message(self, request: A2ARequest) -> A2AResponse:
        """
        Handle incoming A2A message

        Args:
            request: Incoming A2A request

        Returns:
            A2A response
        """
        pass

    async def send_message(
        self,
        target_url: str,
        request: A2ARequest,
        timeout: Optional[float] = None
    ) -> A2AResponse:
        """
        Send A2A message to another agent

        Args:
            target_url: Target agent URL
            request: A2A request to send
            timeout: Optional request timeout

        Returns:
            A2A response from target agent
        """
        if not self.client:
            raise RuntimeError(f"{self.name} not started")

        send_ts = int(time.time() * 1000)
        # Capture EXACT request payload (FULL JSON)
        request_payload: Dict[str, Any] = request.to_dict()
        response_payload: Optional[Dict[str, Any]] = None
        status = "success"

        try:
            self.logger.debug(f"Sending message to {target_url}: {request.method}")

            response = await self.client.post(
                target_url,
                json=request_payload,
                timeout=timeout or self.timeout
            )
            response.raise_for_status()

            # Capture EXACT response payload (FULL JSON) before parsing
            response_payload = response.json()
            return A2AResponse.from_dict(response_payload)

        except httpx.TimeoutException as e:
            status = "error"
            self.logger.error(f"Timeout sending message to {target_url}: {e}")
            # Capture EXACT error response payload
            response_payload = {
                "jsonrpc": "2.0",
                "id": request.request_id,
                "error": {
                    "code": -32001,
                    "message": f"Timeout: {str(e)}"
                }
            }
            return A2AResponse.error(
                request_id=request.request_id,
                code=-32001,
                message=f"Timeout: {str(e)}"
            )
        except httpx.HTTPError as e:
            status = "error"
            self.logger.error(f"HTTP error sending message to {target_url}: {e}")
            # Capture EXACT error response payload
            response_payload = {
                "jsonrpc": "2.0",
                "id": request.request_id,
                "error": {
                    "code": -32002,
                    "message": f"HTTP error: {str(e)}"
                }
            }
            return A2AResponse.error(
                request_id=request.request_id,
                code=-32002,
                message=f"HTTP error: {str(e)}"
            )
        except Exception as e:
            status = "error"
            self.logger.error(f"Error sending message to {target_url}: {e}")
            # Capture EXACT error response payload
            response_payload = {
                "jsonrpc": "2.0",
                "id": request.request_id,
                "error": {
                    "code": -32000,
                    "message": f"Unknown error: {str(e)}"
                }
            }
            return A2AResponse.error(
                request_id=request.request_id,
                code=-32000,
                message=f"Unknown error: {str(e)}"
            )
        finally:
            recv_ts = int(time.time() * 1000)
            try:
                await self._emit_a2a_telemetry(
                    target_url=target_url,
                    request_payload=request_payload,
                    response_payload=response_payload,
                    send_ts=send_ts,
                    recv_ts=recv_ts,
                    status=status,
                )
            except Exception as telemetry_error:
                self.logger.warning(f"Failed to emit A2A telemetry: {telemetry_error}")

    async def _emit_a2a_telemetry(
        self,
        target_url: str,
        request_payload: Dict[str, Any],
        response_payload: Optional[Dict[str, Any]],
        send_ts: int,
        recv_ts: int,
        status: str,
    ) -> None:
        """
        Optional hook for subclasses to emit real A2A telemetry.
        """
        return None

    async def send_to_orchestrator(
        self,
        message: A2AMessage,
        method: str = "tasks/response"
    ) -> A2AResponse:
        """
        Send message to orchestrator agent

        Args:
            message: Message to send
            method: JSON-RPC method

        Returns:
            Response from orchestrator
        """
        request = A2ARequest(method=method, message=message)
        # Assuming orchestrator runs on port 8100
        orchestrator_url = f"http://{self.host}:8100/a2a"
        return await self.send_message(orchestrator_url, request)

    def create_response(
        self,
        request_id: str,
        success: bool,
        result: Optional[Any] = None,
        error_message: Optional[str] = None
    ) -> A2AResponse:
        """
        Create A2A response

        Args:
            request_id: Request ID to respond to
            success: Whether operation succeeded
            result: Result data (if success)
            error_message: Error message (if failure)

        Returns:
            A2A response
        """
        if success:
            return A2AResponse.success(request_id, result)
        else:
            return A2AResponse.error(
                request_id=request_id,
                code=-32000,
                message=error_message or "Unknown error"
            )

    def log_message(self, direction: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Log agent message

        Args:
            direction: "sent" or "received"
            message: Message description
            data: Optional additional data
        """
        log_data = {
            "agent": self.name,
            "direction": direction,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        if data:
            log_data.update(data)

        self.logger.info(f"[{direction.upper()}] {message}", extra=log_data)


class AgentRegistry:
    """
    Registry of all agents in the system

    Allows agents to discover and communicate with each other.
    """

    def __init__(self):
        self.agents: Dict[AgentType, BaseAgent] = {}
        self.agent_urls: Dict[AgentType, str] = {}

    def register(self, agent: BaseAgent, url: str) -> None:
        """Register an agent"""
        self.agents[agent.agent_type] = agent
        self.agent_urls[agent.agent_type] = url
        logger.info(f"Registered {agent.name} at {url}")

    def unregister(self, agent_type: AgentType) -> None:
        """Unregister an agent"""
        if agent_type in self.agents:
            agent = self.agents[agent_type]
            del self.agents[agent_type]
            del self.agent_urls[agent_type]
            logger.info(f"Unregistered {agent.name}")

    def get_agent(self, agent_type: AgentType) -> Optional[BaseAgent]:
        """Get agent by type"""
        return self.agents.get(agent_type)

    def get_url(self, agent_type: AgentType) -> Optional[str]:
        """Get agent URL by type"""
        return self.agent_urls.get(agent_type)

    def get_all_agents(self) -> Dict[AgentType, BaseAgent]:
        """Get all registered agents"""
        return self.agents.copy()

    async def start_all(self) -> None:
        """Start all registered agents"""
        tasks = [agent.start() for agent in self.agents.values()]
        await asyncio.gather(*tasks)
        logger.info(f"Started {len(self.agents)} agents")

    async def stop_all(self) -> None:
        """Stop all registered agents"""
        tasks = [agent.stop() for agent in self.agents.values()]
        await asyncio.gather(*tasks)
        logger.info(f"Stopped {len(self.agents)} agents")


# Global agent registry
_registry = AgentRegistry()


def get_registry() -> AgentRegistry:
    """Get global agent registry"""
    return _registry
