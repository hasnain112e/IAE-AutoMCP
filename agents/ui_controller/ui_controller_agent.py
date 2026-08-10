#Edited by Dr. Wasim
"""
UI Controller Agent

Bridges the Orchestrator Agent and the Web UI via WebSocket.

Responsibilities:
- Maintains WebSocket connections with frontend clients
- Pushes real-time updates from Orchestrator to UI
- Receives user actions (button clicks, timer overrides)
- Manages countdown timer UI updates
- Broadcasts pipeline state changes
"""
import asyncio
import logging
import json
import time
from collections import deque
from typing import Set, Dict, Any, List, Optional
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel

from agents.base_agent import BaseAgent


def safe_serialize(obj: Any) -> Any:
    """
    Safely serialize Pydantic models and other objects to JSON-compatible format.
    Makes the code robust against serialization errors.
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: safe_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [safe_serialize(item) for item in obj]
    else:
        return obj
from shared.a2a_protocol import A2ARequest, A2AResponse, A2AMessage
from shared.message_types import (
    AgentType,
    UIUpdate,
    UIUpdateType,
    PipelineState
)

logger = logging.getLogger(__name__)


class WebSocketConnection:
    """Represents a WebSocket connection"""

    def __init__(self, websocket: WebSocket, client_id: str):
        self.websocket = websocket
        self.client_id = client_id
        self.connected_at = datetime.utcnow()
        self.last_ping = datetime.utcnow()

    async def send_json(self, data: Dict[str, Any]) -> bool:
        """Send JSON data, return True if successful"""
        try:
            await self.websocket.send_json(data)
            return True
        except Exception as e:
            logger.error(f"Error sending to {self.client_id}: {e}")
            return False

    async def send_text(self, text: str) -> bool:
        """Send text data, return True if successful"""
        try:
            await self.websocket.send_text(text)
            return True
        except Exception as e:
            logger.error(f"Error sending to {self.client_id}: {e}")
            return False


class UIControllerAgent(BaseAgent):
    """
    UI Controller Agent - WebSocket Bridge

    Manages real-time communication between backend and frontend.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8102
    ):
        super().__init__(
            agent_type=AgentType.UI_CONTROLLER,
            name="ui_controller",
            host=host,
            port=port
        )
        self.app = FastAPI(title="UI Controller Agent")
        self.connections: Dict[str, WebSocketConnection] = {}
        self.timer_tasks: Dict[str, asyncio.Task] = {}
        self.telemetry_buffer: deque = deque(maxlen=200)
        self._setup_routes()

        # Orchestrator URL
        self.orchestrator_url = "http://127.0.0.1:8100"

    def _setup_routes(self) -> None:
        """Setup FastAPI routes"""
        app = self.app

        # CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """Main WebSocket endpoint for frontend"""
            await self._handle_websocket(websocket)

        @app.post("/telemetry")
        async def ingest_telemetry(event: Dict[str, Any]):
            """Ingest telemetry events from agents and broadcast."""
            await self._handle_telemetry(event)
            return {"success": True}

        @app.post("/broadcast")
        async def broadcast_update(update: Dict[str, Any]):
            """Broadcast update to all connected clients"""
            await self.broadcast(update)
            return {"success": True, "clients": len(self.connections)}

        @app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {
                "status": "healthy",
                "agent": self.name,
                "connections": len(self.connections)
            }

        @app.get("/connections")
        async def list_connections():
            """List active connections"""
            return {
                "count": len(self.connections),
                "clients": [
                    {
                        "client_id": conn.client_id,
                        "connected_at": conn.connected_at.isoformat()
                    }
                    for conn in self.connections.values()
                ]
            }

    async def _handle_websocket(self, websocket: WebSocket) -> None:
        """Handle WebSocket connection"""
        # Accept connection
        await websocket.accept()

        # Generate client ID
        client_id = f"client-{datetime.utcnow().timestamp()}"
        connection = WebSocketConnection(websocket, client_id)
        self.connections[client_id] = connection

        logger.info(f"Client connected: {client_id} (total: {len(self.connections)})")

        # Send welcome message
        await connection.send_json({
            "type": "connected",
            "client_id": client_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        # Replay recent telemetry buffer in send_ts order
        if self.telemetry_buffer:
            replay_events = sorted(list(self.telemetry_buffer), key=lambda e: e.get("send_ts", 0))
            await connection.send_json({
                "type": "telemetry_replay",
                "events": replay_events
            })

        heartbeat_task: Optional[asyncio.Task] = None
        try:
            heartbeat_task = asyncio.create_task(self._heartbeat_client(client_id))
            # Message loop
            while True:
                # Receive message
                data = await websocket.receive_json()

                # Handle message
                await self._handle_client_message(client_id, data)

        except WebSocketDisconnect:
            logger.info(f"Client disconnected: {client_id}")
        except Exception as e:
            logger.error(f"WebSocket error for {client_id}: {e}")
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
            # Clean up
            if client_id in self.connections:
                del self.connections[client_id]
            logger.info(f"Client removed: {client_id} (remaining: {len(self.connections)})")

    async def _handle_client_message(self, client_id: str, data: Dict[str, Any]) -> None:
        """Handle message from client"""
        msg_type = data.get("type")
        context_id = data.get("context_id")

        logger.info(f"Received from {client_id}: {msg_type}")

        try:
            if msg_type == "ping":
                # Respond to ping
                connection = self.connections.get(client_id)
                if connection:
                    connection.last_ping = datetime.utcnow()
                    await connection.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
            elif msg_type == "pong":
                connection = self.connections.get(client_id)
                if connection:
                    connection.last_ping = datetime.utcnow()

            elif msg_type == "validate_manual":
                # User manually triggered validation
                await self._trigger_action(context_id, "validate", manual=True)

            elif msg_type == "regenerate_manual":
                # User manually triggered regeneration
                await self._trigger_action(context_id, "regenerate", manual=True)

            elif msg_type == "cancel_timer":
                # User cancelled a timer
                action = data.get("action")
                await self._cancel_timer_ui(context_id, action)

            elif msg_type == "get_status":
                # Request pipeline status
                await self._send_status(client_id, context_id)

            elif msg_type == "auto_run_start":
                # Start auto-run pipeline
                await self._trigger_auto_run(client_id, data)

            elif msg_type == "auto_run_stop":
                # Stop auto-run pipeline
                await self._stop_auto_run(context_id)

            elif msg_type == "auto_run_status":
                # Get auto-run status
                await self._send_auto_run_status(client_id, context_id)

            else:
                logger.warning(f"Unknown message type: {msg_type}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            connection = self.connections.get(client_id)
            if connection:
                await connection.send_json({
                    "type": "error",
                    "message": str(e)
                })

    async def _trigger_action(
        self,
        context_id: str,
        action: str,
        manual: bool
    ) -> None:
        """Trigger action in orchestrator"""
        if not self.client:
            return

        try:
            # Call orchestrator API
            endpoint = f"{self.orchestrator_url}/pipeline/{context_id}/{action}"
            response = await self.client.post(
                endpoint,
                params={"manual": manual}
            )
            response.raise_for_status()

            logger.info(f"Triggered {action} for {context_id} (manual: {manual})")

        except Exception as e:
            logger.error(f"Error triggering {action}: {e}")

    async def _cancel_timer_ui(self, context_id: str, action: str) -> None:
        """Cancel timer in UI"""
        timer_key = f"{context_id}-{action}"
        if timer_key in self.timer_tasks:
            self.timer_tasks[timer_key].cancel()
            del self.timer_tasks[timer_key]

            # Broadcast cancellation
            await self.broadcast({
                "type": UIUpdateType.TIMER_CANCEL.value,
                "context_id": context_id,
                "data": {"action": action}
            })

    async def _send_status(self, client_id: str, context_id: str) -> None:
        """Send pipeline status to specific client"""
        connection = self.connections.get(client_id)
        if not connection or not self.client:
            return

        try:
            # Get status from orchestrator
            response = await self.client.get(
                f"{self.orchestrator_url}/pipeline/{context_id}/status"
            )
            response.raise_for_status()
            status = response.json()

            # Send to client
            await connection.send_json({
                "type": "status",
                "context_id": context_id,
                "data": status
            })

        except Exception as e:
            logger.error(f"Error getting status: {e}")

    async def _trigger_auto_run(self, client_id: str, data: Dict[str, Any]) -> None:
        """Trigger auto-run pipeline from client request."""
        connection = self.connections.get(client_id)
        if not self.client:
            return

        try:
            # Extract auto-run config from client data
            source_type = data.get("source_type", "url")
            source_data = data.get("source_data")
            
            # Validate input: check for empty or invalid source_data
            if source_type == "url":
                if not source_data or not source_data.strip():
                    error_msg = "Invalid Input. Please provide a valid API documentation link."
                    logger.warning(f"Invalid URL input: empty or None")
                    if connection:
                        await connection.send_json({
                            "type": "error",
                            "error": error_msg,
                            "context_id": data.get("context_id"),
                            "reset_pipeline": True
                        })
                    return
                # Basic URL validation
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(source_data.strip())
                    if not parsed.scheme or not parsed.netloc:
                        error_msg = "Invalid Input. Please provide a valid API documentation link."
                        logger.warning(f"Invalid URL format: {source_data}")
                        if connection:
                            await connection.send_json({
                                "type": "error",
                                "error": error_msg,
                                "context_id": data.get("context_id"),
                                "reset_pipeline": True
                            })
                        return
                except Exception as url_error:
                    error_msg = "Invalid Input. Please provide a valid API documentation link."
                    logger.warning(f"URL validation error: {url_error}")
                    if connection:
                        await connection.send_json({
                            "type": "error",
                            "error": error_msg,
                            "context_id": data.get("context_id"),
                            "reset_pipeline": True
                        })
                    return
            
            config = {
                "source_type": source_type,
                "source_data": source_data,
                "tools": data.get("tools"),
                "iterations": data.get("iterations", 5),
                "auto_validate": data.get("auto_validate", True),
                "auto_regenerate": data.get("auto_regenerate", True)
            }

            # Call orchestrator auto-run endpoint
            response = await self.client.post(
                f"{self.orchestrator_url}/pipeline/auto-run",
                json=config,
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()

            logger.info(f"🚀 Auto Run triggered: {result.get('context_id')}")

            # Send confirmation to client
            if connection:
                await connection.send_json({
                    "type": "auto_run_started",
                    "context_id": result.get("context_id"),
                    "iterations": config["iterations"],
                    "data": result
                })

        except Exception as e:
            logger.error(f"Error triggering auto-run: {e}")
            error_msg = f"Failed to start pipeline: {str(e)}"
            # Check if it's a validation/input error
            error_str = str(e).lower()
            if "invalid" in error_str or "empty" in error_str or "url" in error_str or "400" in error_str:
                error_msg = "Invalid Input. Please provide a valid API documentation link."
            if connection:
                await connection.send_json({
                    "type": "error",
                    "error": error_msg,
                    "context_id": data.get("context_id"),
                    "reset_pipeline": True
                })

    async def _stop_auto_run(self, context_id: str) -> None:
        """Stop auto-run pipeline."""
        if not self.client or not context_id:
            return

        try:
            response = await self.client.post(
                f"{self.orchestrator_url}/pipeline/{context_id}/auto-run/stop"
            )
            response.raise_for_status()
            
            logger.info(f"🛑 Auto Run stopped: {context_id}")

            # Broadcast stop notification
            await self.broadcast({
                "type": "auto_run_stopped",
                "context_id": context_id
            })

        except Exception as e:
            logger.error(f"Error stopping auto-run: {e}")

    async def _send_auto_run_status(self, client_id: str, context_id: str) -> None:
        """Send auto-run status to specific client."""
        connection = self.connections.get(client_id)
        if not connection or not self.client:
            return

        try:
            response = await self.client.get(
                f"{self.orchestrator_url}/pipeline/{context_id}/auto-run/status"
            )
            response.raise_for_status()
            status = response.json()

            await connection.send_json({
                "type": "auto_run_status",
                "context_id": context_id,
                "data": status
            })

        except Exception as e:
            logger.error(f"Error getting auto-run status: {e}")

    async def broadcast(self, data: Dict[str, Any]) -> None:
        """
        Broadcast message to all connected clients.
        ROBUST: Automatically serializes Pydantic models to prevent JSON errors.
        """
        if not self.connections:
            return

        logger.debug(f"Broadcasting to {len(self.connections)} clients: {data.get('type')}")

        # Safely serialize data to prevent "Object of type X is not JSON serializable" errors
        safe_data = safe_serialize(data)

        # Handle timer updates specially
        if safe_data.get("type") == UIUpdateType.TIMER_START.value:
            await self._handle_timer_start(safe_data)
        
        # Telemetry events are already buffered in _handle_telemetry
        # No need to buffer again here

        disconnected = []
        for client_id, connection in self.connections.items():
            try:
                success = await connection.send_json(safe_data)
                if not success:
                    disconnected.append(client_id)
            except Exception as e:
                logger.error(f"Broadcast send failed for {client_id}: {e}")
                disconnected.append(client_id)

        # Remove disconnected clients
        for client_id in disconnected:
            del self.connections[client_id]
            logger.info(f"Removed disconnected client: {client_id}")

    async def _heartbeat_client(self, client_id: str) -> None:
        """Send periodic ping to keep WebSocket alive and close stale clients."""
        while True:
            await asyncio.sleep(20)
            connection = self.connections.get(client_id)
            if not connection:
                return
            seconds_since_pong = (datetime.utcnow() - connection.last_ping).total_seconds()
            if seconds_since_pong > 40:
                logger.warning(f"Heartbeat timeout for {client_id}; closing connection.")
                try:
                    await connection.websocket.close(code=1001, reason="Heartbeat timeout")
                except Exception as e:
                    logger.error(f"Error closing websocket for {client_id}: {e}")
                return
            await connection.send_json({
                "type": "ping",
                "timestamp": datetime.utcnow().isoformat()
            })

    async def _handle_timer_start(self, data: Dict[str, Any]) -> None:
        """Handle timer start - begin countdown"""
        context_id = data.get("context_id")
        timer_data = data.get("data", {})
        action = timer_data.get("action")
        duration = timer_data.get("duration", 10)

        if not context_id or not action:
            return

        timer_key = f"{context_id}-{action}"

        # Cancel existing timer if any
        if timer_key in self.timer_tasks:
            self.timer_tasks[timer_key].cancel()

        # Start new countdown task
        self.timer_tasks[timer_key] = asyncio.create_task(
            self._countdown_task(context_id, action, duration)
        )

    async def _countdown_task(
        self,
        context_id: str,
        action: str,
        duration: int
    ) -> None:
        """Countdown task - broadcasts tick updates"""
        timer_key = f"{context_id}-{action}"

        try:
            for remaining in range(duration, 0, -1):
                # Broadcast tick
                await self.broadcast({
                    "type": UIUpdateType.TIMER_TICK.value,
                    "context_id": context_id,
                    "data": {
                        "action": action,
                        "remaining": remaining,
                        "total": duration
                    }
                })

                # Wait 1 second
                await asyncio.sleep(1)

            # Timer expired
            logger.info(f"Timer expired: {timer_key}")

            # Clean up
            if timer_key in self.timer_tasks:
                del self.timer_tasks[timer_key]

        except asyncio.CancelledError:
            logger.info(f"Timer cancelled: {timer_key}")
        except Exception as e:
            logger.error(f"Timer error: {e}")

    async def handle_message(self, request: A2ARequest) -> A2AResponse:
        """Handle A2A message (for future use)"""
        return A2AResponse.success(
            request_id=request.request_id,
            result={"status": "ok"}
        )

    async def _handle_telemetry(self, event: Dict[str, Any]) -> None:
        """
        Handle telemetry events from orchestrator.
        
        MUST NOT modify, summarize, or fabricate logs.
        ONLY forwards telemetry events via WebSocket unchanged.
        """
        events: List[Dict[str, Any]] = []
        if isinstance(event, list):
            events = event
        else:
            events = [event]

        for ev in events:
            # Validate event has required fields (backend source of truth)
            if not ev.get("request_payload") or not ev.get("response_payload"):
                event_id = ev.get('event_id', 'unknown')
                logger.warning(f"Skipping invalid telemetry event (missing payloads): {event_id}")
                
                # Check if response_payload indicates an error
                response_payload = ev.get("response_payload")
                if isinstance(response_payload, dict):
                    error_info = response_payload.get("error")
                    if error_info:
                        error_msg = error_info.get("message", "Invalid Input. Please provide a valid API documentation link.") if isinstance(error_info, dict) else str(error_info)
                        # Extract context_id from request payload
                        context_id = None
                        request_payload = ev.get("request_payload", {})
                        if isinstance(request_payload, dict):
                            params = request_payload.get("params", {})
                            if isinstance(params, dict):
                                message = params.get("message", {})
                                if isinstance(message, dict):
                                    context_id = message.get("contextId")
                        
                        # Broadcast error to frontend
                        await self.broadcast({
                            "type": "error",
                            "error": error_msg,
                            "context_id": context_id,
                            "reset_pipeline": True
                        })
                continue
            
            # Buffer for replay (no modification)
            self._buffer_telemetry(ev)
            
            # Forward unchanged to frontend via WebSocket
            await self.broadcast({"type": "telemetry", "event": ev})

    def _buffer_telemetry(self, event: Dict[str, Any]) -> None:
        """Store telemetry in buffer with ordering by send_ts."""
        # De-dupe by event_id
        existing_ids = {e.get("event_id") for e in self.telemetry_buffer}
        if event.get("event_id") in existing_ids:
            return
        self.telemetry_buffer.append(event)

    async def run(self) -> None:
        """Run the UI controller agent server"""
        await self.start()
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        logger.info(f"UI Controller Agent running on {self.base_url}")
        await server.serve()


# Standalone execution
async def main():
    agent = UIControllerAgent()
    await agent.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
