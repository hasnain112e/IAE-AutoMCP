# Edited by Dr. Wasim
"""
Orchestrator Agent

The master controller that manages the entire MCP generation pipeline.

Responsibilities:
- Receives user input and decides pipeline flow
- Manages state machine transitions
- Routes messages to appropriate agents
- Handles human-in-the-loop gates
- Tracks retry count and timeout logic
- Sends status updates to UI
"""
import asyncio
import logging
import uuid
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel


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

from agents.base_agent import BaseAgent
from agents.orchestrator.state_machine import PipelineStateMachine
from shared.a2a_protocol import (
    A2ARequest,
    A2AResponse,
    A2AMessage,
    A2AProtocol,
    MessageRole
)
from shared.message_types import (
    AgentType,
    PipelineState,
    PipelineContext,
    PipelineConfig,
    SourceType,
    Tool,
    ToolsCollectionRequest,
    CodeGenerationRequest,
    ValidationRequest,
    HITLDecision,
    UIUpdate,
    UIUpdateType,
    create_ui_update
)

logger = logging.getLogger(__name__)


class StartPipelineBody(BaseModel):
    source_type: SourceType
    source_data: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None


class AutoRunConfig(BaseModel):
    """Configuration for Auto Run automation loop."""
    source_type: SourceType = SourceType.URL
    source_data: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    iterations: int = 5  # Default 5 iterations
    auto_validate: bool = True  # Automatically trigger validation
    auto_regenerate: bool = True  # Automatically regenerate on failure


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent - Pipeline Master Controller

    Manages the complete pipeline from input to final MCP code generation.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8100,
        config: Optional[PipelineConfig] = None
    ):
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            name="orchestrator",
            host=host,
            port=port
        )
        self.state_machine = PipelineStateMachine(config)
        self.app = FastAPI(title="Orchestrator Agent")
        self.websocket_connections: List[WebSocket] = []
        self._setup_routes()
        self._setup_event_handlers()

        # Agent endpoints
        # Use candidates to survive Windows localhost/::1 vs 127.0.0.1 binding differences.
        self.backend_urls = ["http://127.0.0.1:8000", "http://localhost:8000"]
        self.generator_urls = ["http://127.0.0.1:8101/a2a", "http://localhost:8101/a2a"]
        self.validator_urls = ["http://127.0.0.1:8002/a2a", "http://localhost:8002/a2a"]
        self.ui_controller_urls = ["http://127.0.0.1:8102", "http://localhost:8102"]

    def _target_agent_from_url(self, target_url: str) -> str:
        """
        Map target URL to agent name for telemetry labeling.
        """
        for url in self.generator_urls:
            if url in target_url:
                return "generator"
        for url in self.validator_urls:
            if url in target_url:
                return "validator"
        for url in self.backend_urls:
            if url in target_url:
                return "backend"
        return target_url

    def _is_placeholder_tool(self, tool: Tool) -> bool:
        name = (tool.name or "").strip().lower()
        return name == "raw_url_docs"

    def _is_sdk_tool(self, tool: Tool) -> bool:
        meta = tool.metadata or {}
        source = (meta.get("source") or "").strip().lower()
        return source == "python_sdk" or bool(meta.get("sdk_module")) or bool(meta.get("sdk_function"))

    def _has_only_placeholder_tools(self, tools: List[Tool]) -> bool:
        if not tools:
            return False
        return all(self._is_placeholder_tool(tool) for tool in tools)

    def _has_functional_api_tools(self, tools: List[Tool]) -> bool:
        if not tools or self._has_only_placeholder_tools(tools):
            return False
        allowed_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        for tool in tools:
            if self._is_placeholder_tool(tool):
                continue
            if self._is_sdk_tool(tool):
                return True
            method = (tool.method or "").strip().upper()
            path = (tool.path or "").strip()
            if method in allowed_methods and path:
                return True
        return False

    async def _fail_no_endpoints(self, context_id: str) -> None:
        context = self.state_machine.get_context(context_id)
        if context:
            context.error = "No API endpoints could be extracted. Please check your URL and try again."
        await self.broadcast_ui_update(
            UIUpdateType.ERROR,
            context_id,
            {
                "error": "No API endpoints could be extracted. Please check your URL and try again.",
                "reset_pipeline": True,
            },
        )
        try:
            await self.state_machine.transition(context_id, PipelineState.FAILED_FINAL)
        except Exception as transition_error:
            logger.warning(f"Error transitioning to FAILED_FINAL: {transition_error}")

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
        Emit a single immutable A2A telemetry event per exchange.
        
        SOURCE OF TRUTH: This is the ONLY place where A2A telemetry is created.
        The UI must display ONLY these events - no UI-generated, no inferred logs.
        """
        # Extract context_id from request payload
        context_id = (
            request_payload.get("params", {})
            .get("message", {})
            .get("contextId")
        )
        request_id = request_payload.get("id")
        correlation_id = f"{context_id}:{request_id}" if context_id and request_id else (request_id or "")

        # Create structured telemetry event (EXACT payloads from backend)
        event = {
            "event_id": f"a2a-{uuid.uuid4().hex}",
            "context_id": context_id,
            "correlation_id": correlation_id,
            "from_agent": self.name,
            "to_agent": self._target_agent_from_url(target_url),
            "request_payload": request_payload,  # EXACT request payload sent
            "response_payload": response_payload,  # EXACT response payload received
            "send_ts": send_ts,
            "recv_ts": recv_ts,
            "latency_ms": max(recv_ts - send_ts, 0),
            "status": status,
        }

        if not self.client:
            return

        # Forward to UI Controller (best-effort, non-blocking)
        for base in self.ui_controller_urls:
            try:
                await self.client.post(f"{base}/telemetry", json=event, timeout=5.0)
                break
            except Exception as e:
                logger.warning(f"Failed to forward A2A telemetry to UI Controller via {base}: {e}")

    @property
    def generator_url(self) -> str:
        """
        Backwards-compatible single generator URL.

        Some older code paths referenced `self.generator_url`; keep this as an alias
        to the first candidate in `self.generator_urls`.
        """
        return self.generator_urls[0]

    @property
    def validator_url(self) -> str:
        """
        Backwards-compatible single validator URL.

        Some older code paths referenced `self.validator_url`; keep this as an alias
        to the first candidate in `self.validator_urls`.
        """
        return self.validator_urls[0]

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

        @app.post("/a2a")
        async def handle_a2a_message(request_dict: Dict[str, Any]) -> Dict[str, Any]:
            """Handle incoming A2A messages"""
            try:
                request = A2ARequest.from_dict(request_dict)
                response = await self.handle_message(request)
                return response.to_dict()
            except Exception as e:
                logger.error(f"Error handling A2A message: {e}")
                return A2AResponse.error(
                    request_id=request_dict.get("id", "unknown"),
                    code=-32000,
                    message=str(e)
                ).to_dict()

        @app.post("/pipeline/start")
        async def start_pipeline(
            source_type: SourceType = SourceType.URL,
            source_data: Optional[str] = None,
            body: Optional[StartPipelineBody] = None,
        ) -> Dict[str, Any]:
            """Start new pipeline"""
            try:
                if body is not None:
                    source_type = body.source_type
                    source_data = body.source_data

                # Create new context and run pipeline asynchronously so the HTTP call returns immediately.
                context = self.state_machine.create_context()
                asyncio.create_task(self._run_pipeline(context.context_id, source_type, source_data, body.tools if body else None))
                return {"success": True, "context_id": context.context_id}
            except Exception as e:
                logger.error(f"Error starting pipeline: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/pipeline/{context_id}/validate")
        async def trigger_validation(context_id: str, manual: bool = True) -> Dict[str, Any]:
            """Manually trigger validation"""
            try:
                await self.trigger_validation(context_id, manual)
                return {"success": True, "message": "Validation triggered"}
            except Exception as e:
                logger.error(f"Error triggering validation: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/pipeline/{context_id}/regenerate")
        async def trigger_regeneration(context_id: str, manual: bool = True) -> Dict[str, Any]:
            """Manually trigger regeneration"""
            try:
                await self.trigger_regeneration(context_id, manual)
                return {"success": True, "message": "Regeneration triggered"}
            except Exception as e:
                logger.error(f"Error triggering regeneration: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/pipeline/{context_id}/status")
        async def get_pipeline_status(context_id: str) -> Dict[str, Any]:
            """Get pipeline status"""
            context = self.state_machine.get_context(context_id)
            if not context:
                raise HTTPException(status_code=404, detail="Context not found")

            return {
                "context_id": context.context_id,
                "state": context.state.value,
                "iteration": context.iteration,
                "max_iterations": context.config.max_iterations,
                "tools_count": len(context.tools),
                "has_code": context.generated_code is not None,
                "validation_result": context.validation_result.model_dump() if context.validation_result else None,
                "error": context.error,
            }

        @app.get("/pipeline/{context_id}/code")
        async def get_pipeline_code(context_id: str) -> Dict[str, Any]:
            """Get generated code for a pipeline context (if available)."""
            context = self.state_machine.get_context(context_id)
            if not context:
                raise HTTPException(status_code=404, detail="Context not found")
            if not context.generated_code:
                raise HTTPException(status_code=404, detail="No generated code available yet")

            return {
                "context_id": context.context_id,
                "iteration": context.iteration,
                "code": context.generated_code,  # Full code, no truncation
                "code_length": len(context.generated_code),
                "line_count": context.generated_code.count('\n') + 1
            }

        @app.post("/pipeline/auto-run")
        async def auto_run_pipeline(config: AutoRunConfig) -> Dict[str, Any]:
            """
            AUTO RUN: Automated pipeline execution with multiple iterations.
            
            Runs the complete pipeline (generate → validate → regenerate) for
            the specified number of iterations automatically without user intervention.
            
            Args:
                config: AutoRunConfig with source_type, source_data, tools, iterations
                
            Returns:
                context_id and status information
            """
            try:
                # Validate input: check for empty or invalid source_data
                if config.source_type == SourceType.URL:
                    if not config.source_data or not config.source_data.strip():
                        raise HTTPException(
                            status_code=400,
                            detail="Invalid Input. Please provide a valid API documentation link."
                        )
                    # Basic URL validation
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(config.source_data.strip())
                        if not parsed.scheme or not parsed.netloc:
                            raise HTTPException(
                                status_code=400,
                                detail="Invalid Input. Please provide a valid API documentation link."
                            )
                    except HTTPException:
                        raise
                    except Exception:
                        raise HTTPException(
                            status_code=400,
                            detail="Invalid Input. Please provide a valid API documentation link."
                        )
                
                # Create new context
                context = self.state_machine.create_context()
                context_id = context.context_id
                
                # Store auto-run config in context metadata
                context.metadata["auto_run"] = True
                context.metadata["auto_run_iterations"] = config.iterations
                context.metadata["auto_run_current"] = 0
                context.metadata["auto_validate"] = config.auto_validate
                context.metadata["auto_regenerate"] = config.auto_regenerate
                
                # Start the auto-run pipeline asynchronously
                asyncio.create_task(self._run_auto_pipeline(
                    context_id=context_id,
                    source_type=config.source_type,
                    source_data=config.source_data,
                    tools=[t for t in config.tools] if config.tools else None,
                    max_iterations=config.iterations
                ))
                
                logger.info(f"🚀 AUTO RUN started: context={context_id}, iterations={config.iterations}")
                
                return {
                    "success": True,
                    "context_id": context_id,
                    "message": f"Auto Run started for {config.iterations} iterations",
                    "auto_run": True,
                    "iterations": config.iterations
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error starting auto-run: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/pipeline/{context_id}/auto-run/status")
        async def get_auto_run_status(context_id: str) -> Dict[str, Any]:
            """Get status of auto-run pipeline."""
            context = self.state_machine.get_context(context_id)
            if not context:
                raise HTTPException(status_code=404, detail="Context not found")
            
            return {
                "context_id": context_id,
                "auto_run": context.metadata.get("auto_run", False),
                "current_iteration": context.metadata.get("auto_run_current", 0),
                "max_iterations": context.metadata.get("auto_run_iterations", 5),
                "state": context.state.value,
                "best_score": context.best_score,
                "approved": context.validation_result.approved if context.validation_result else False,
                "completed": context.state in [PipelineState.DONE, PipelineState.FAILED_FINAL]
            }

        @app.post("/pipeline/{context_id}/auto-run/stop")
        async def stop_auto_run(context_id: str) -> Dict[str, Any]:
            """Stop an auto-run pipeline."""
            context = self.state_machine.get_context(context_id)
            if not context:
                raise HTTPException(status_code=404, detail="Context not found")
            
            # Mark auto-run as stopped
            context.metadata["auto_run_stopped"] = True
            logger.info(f"🛑 AUTO RUN stopped by user: {context_id}")
            
            return {
                "success": True,
                "context_id": context_id,
                "message": "Auto Run stopped"
            }

        @app.post("/draft/submit")
        async def submit_draft(draft: Dict[str, Any]) -> Dict[str, Any]:
            """
            Accept a draft generated by System A (generator-only) and send directly to validation.
            """
            context_id = draft.get("context_id") or str(uuid.uuid4())
            draft_id = draft.get("draft_id") or str(uuid.uuid4())
            generated_output = draft.get("generated_output")
            if not generated_output:
                raise HTTPException(status_code=400, detail="generated_output is required")

            # Ensure context exists
            context = self.state_machine.get_context(context_id)
            if not context:
                context = self.state_machine.create_context(context_id=context_id)

            # Populate context with draft
            context.generated_code = generated_output
            context.iteration = max(context.iteration, 1)
            context.metadata["draft_id"] = draft_id
            context.metadata["source"] = "generator-only"
            context.metadata["tools_used"] = draft.get("tools_used", [])
            context.state = PipelineState.AWAITING_VALIDATION

            correlation_id = f"{context_id}:{draft_id}"

            await self.broadcast_ui_update(
                UIUpdateType.STATE_CHANGE,
                context_id,
                {"from_state": context.state.value, "to_state": PipelineState.AWAITING_VALIDATION.value, "draft_id": draft_id, "correlation_id": correlation_id},
            )

            await self.broadcast_agent_thinking(
                context_id,
                "orchestrator",
                f"Draft received from System A (draft_id={draft_id}). Sending to validator...",
                "draft_received"
            )

            # Validate immediately (skip generator)
            await self._validate_code(context_id, auto=True)

            return {"success": True, "context_id": context_id, "draft_id": draft_id, "correlation_id": correlation_id}

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket for real-time updates"""
            await websocket.accept()
            self.websocket_connections.append(websocket)
            logger.info("WebSocket client connected")

            try:
                while True:
                    # Keep connection alive
                    data = await websocket.receive_text()
                    # Echo back or handle commands
                    await websocket.send_text(f"Received: {data}")
            except WebSocketDisconnect:
                self.websocket_connections.remove(websocket)
                logger.info("WebSocket client disconnected")

    def _setup_event_handlers(self) -> None:
        """Setup state machine event handlers"""
        self.state_machine.on_event("state_change", self._on_state_change)
        self.state_machine.on_event("timer_start", self._on_timer_start)
        self.state_machine.on_event("timer_cancel", self._on_timer_cancel)
        self.state_machine.on_event("hitl_decision", self._on_hitl_decision)

    async def _on_state_change(self, context_id: str, data: Dict[str, Any]) -> None:
        """Handle state change event"""
        logger.info(f"State change: {data}")
        await self.broadcast_ui_update(
            UIUpdateType.STATE_CHANGE,
            context_id,
            data
        )

    async def _on_timer_start(self, context_id: str, data: Dict[str, Any]) -> None:
        """Handle timer start event"""
        logger.info(f"Timer started: {data}")
        await self.broadcast_ui_update(
            UIUpdateType.TIMER_START,
            context_id,
            data
        )

    async def _on_timer_cancel(self, context_id: str, data: Dict[str, Any]) -> None:
        """Handle timer cancel event"""
        logger.info(f"Timer cancelled: {data}")
        await self.broadcast_ui_update(
            UIUpdateType.TIMER_CANCEL,
            context_id,
            data
        )

    async def _on_hitl_decision(self, context_id: str, data: Dict[str, Any]) -> None:
        """Handle HITL decision event"""
        logger.info(f"HITL decision: {data}")

    async def handle_message(self, request: A2ARequest) -> A2AResponse:
        """Handle incoming A2A message"""
        method = request.method
        message = request.params.get("message", {})

        try:
            if method == "tasks/send":
                # Handle task from another agent
                return await self._handle_task(request)
            elif method == "tasks/response":
                # Handle response from agent
                return await self._handle_response(request)
            else:
                return A2AResponse.error(
                    request_id=request.request_id,
                    code=-32601,
                    message=f"Method not found: {method}"
                )
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return A2AResponse.error(
                request_id=request.request_id,
                code=-32000,
                message=str(e)
            )

    async def _handle_task(self, request: A2ARequest) -> A2AResponse:
        """Handle task message"""
        # For now, return success
        return A2AResponse.success(
            request_id=request.request_id,
            result={"status": "task_received"}
        )

    async def _handle_response(self, request: A2ARequest) -> A2AResponse:
        """Handle response from agent"""
        # For now, return success
        return A2AResponse.success(
            request_id=request.request_id,
            result={"status": "response_received"}
        )

    async def start_pipeline(
        self,
        source_type: SourceType,
        source_data: Optional[str] = None
    ) -> PipelineContext:
        """
        Start new pipeline execution

        Args:
            source_type: Type of input source
            source_data: Source data (URL, SDK name, or file content)

        Returns:
            Pipeline context
        """
        # Create new context
        context = self.state_machine.create_context()

        logger.info(f"Starting pipeline {context.context_id} with {source_type}")

        # Transition to input received
        await self.state_machine.transition(
            context.context_id,
            PipelineState.INPUT_RECEIVED
        )

        # Start tool collection
        await self._collect_tools(context.context_id, source_type, source_data)

        return context

    async def _run_auto_pipeline(
        self,
        context_id: str,
        source_type: SourceType,
        source_data: Optional[str],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_iterations: int = 5,
    ) -> None:
        """
        AUTO RUN: Execute automated pipeline with multiple iterations.
        
        This method runs the complete generate → validate → regenerate cycle
        automatically for the specified number of iterations.
        
        Args:
            context_id: Pipeline context ID
            source_type: Type of input source
            source_data: Source data (URL, SDK name, etc.)
            tools: Optional pre-loaded tools
            max_iterations: Maximum iterations to run (default 5)
        """
        context = self.state_machine.get_context(context_id)
        if not context:
            logger.error(f"Context not found for auto-run: {context_id}")
            return

        logger.info(f"🤖 AUTO RUN starting: {context_id} with {max_iterations} iterations")
        
        await self.broadcast_agent_thinking(
            context_id,
            "orchestrator",
            f"🚀 AUTO RUN started: Running {max_iterations} automated iterations",
            "auto_run_start"
        )

        try:
            # Phase 1: Collect tools (if not provided)
            await self.state_machine.transition(context_id, PipelineState.INPUT_RECEIVED)
            
            if tools:
                await self.state_machine.transition(context_id, PipelineState.COLLECTING_TOOLS)
                context.tools = [Tool(**t) for t in tools]
                if self._has_only_placeholder_tools(context.tools):
                    await self._fail_no_endpoints(context_id)
                    return
                if not self._has_functional_api_tools(context.tools):
                    await self._fail_no_endpoints(context_id)
                    return
                await self.state_machine.transition(context_id, PipelineState.TOOLS_READY)
                await self.broadcast_ui_update(
                    UIUpdateType.TOOLS_UPDATED,
                    context_id,
                    {"tools_count": len(context.tools), "count": len(context.tools)}
                )
            else:
                await self._collect_tools(context_id, source_type, source_data)
                # Wait for tools to be collected
                for _ in range(30):  # 30 second timeout
                    if context.state == PipelineState.TOOLS_READY:
                        break
                    await asyncio.sleep(1)
                if context.state == PipelineState.FAILED_FINAL:
                    return
            
            # Phase 2: Auto iteration loop
            for iteration in range(1, max_iterations + 1):
                # Check if stopped by user
                if context.metadata.get("auto_run_stopped"):
                    logger.info(f"🛑 AUTO RUN stopped by user at iteration {iteration}")
                    await self.broadcast_agent_thinking(
                        context_id,
                        "orchestrator",
                        f"🛑 Auto Run stopped by user at iteration {iteration}",
                        "auto_run_stopped"
                    )
                    break
                
                # Update current iteration
                context.metadata["auto_run_current"] = iteration
                
                await self.broadcast_agent_thinking(
                    context_id,
                    "orchestrator",
                    f"🔄 AUTO RUN iteration {iteration}/{max_iterations}",
                    "auto_run_iteration"
                )
                
                # Step 1: Generate code
                logger.info(f"[AutoRun] Iteration {iteration}: Generating code...")
                await self._generate_code(context_id)
                
                # Wait for code generation to complete
                for _ in range(120):  # 2 minute timeout
                    if context.state == PipelineState.AWAITING_VALIDATION:
                        break
                    if context.state == PipelineState.FAILED_FINAL:
                        logger.error(f"[AutoRun] Generation failed at iteration {iteration}")
                        break
                    await asyncio.sleep(1)
                
                if context.state == PipelineState.FAILED_FINAL:
                    break
                
                # Step 2: Validate code (auto-trigger)
                if context.metadata.get("auto_validate", True):
                    logger.info(f"[AutoRun] Iteration {iteration}: Validating code...")
                    await self._validate_code(context_id, auto=True)
                    
                    # Wait for validation to complete
                    for _ in range(120):  # 2 minute timeout
                        if context.state in [PipelineState.VALIDATION_RESULT, PipelineState.DONE, 
                                            PipelineState.AWAITING_REGEN, PipelineState.FAILED_FINAL]:
                            break
                        await asyncio.sleep(1)
                
                # Check if validation passed
                if context.validation_result and context.validation_result.approved:
                    logger.info(f"✅ AUTO RUN completed successfully at iteration {iteration}!")
                    await self.broadcast_agent_thinking(
                        context_id,
                        "orchestrator",
                        f"✅ AUTO RUN SUCCESS! Code approved at iteration {iteration} with score {context.validation_result.quality_score}/100",
                        "auto_run_success"
                    )
                    break
                
                # Check if we're at max iterations
                if iteration >= max_iterations:
                    logger.info(f"[AutoRun] Reached max iterations ({max_iterations})")
                    await self.broadcast_agent_thinking(
                        context_id,
                        "orchestrator",
                        f"🏁 AUTO RUN completed: {max_iterations} iterations. Best score: {context.best_score}/100",
                        "auto_run_complete"
                    )
                    break
                
                # Step 3: Prepare for regeneration (if not approved)
                if context.state == PipelineState.AWAITING_REGEN:
                    logger.info(f"[AutoRun] Iteration {iteration}: Preparing regeneration...")
                    await self.state_machine.transition(context_id, PipelineState.REGENERATING_CODE)
                
                # Small delay between iterations
                await asyncio.sleep(1)
            
            # Final status broadcast
            final_status = "SUCCESS" if (context.validation_result and context.validation_result.approved) else "INCOMPLETE"
            await self.broadcast_ui_update(
                UIUpdateType.INFO,
                context_id,
                {
                    "auto_run_complete": True,
                    "status": final_status,
                    "iterations_completed": context.metadata.get("auto_run_current", 0),
                    "best_score": context.best_score,
                    "approved": context.validation_result.approved if context.validation_result else False
                }
            )
            
        except Exception as e:
            logger.error(f"AUTO RUN error: {e}")
            error_str = str(e)
            
            # Provide user-friendly error message
            error_msg = error_str
            if "400" in error_str or "invalid" in error_str.lower() or "empty" in error_str.lower():
                error_msg = "Invalid Input. Please provide a valid API documentation link."
            elif "404" in error_str or "not found" in error_str.lower():
                error_msg = "Invalid Input. The provided URL could not be found. Please provide a valid API documentation link."
            
            context.error = error_msg
            await self.broadcast_ui_update(
                UIUpdateType.ERROR, 
                context_id, 
                {
                    "error": error_msg,
                    "auto_run": True,
                    "reset_pipeline": True,
                    "original_error": error_str
                }
            )

    async def _run_pipeline(
        self,
        context_id: str,
        source_type: SourceType,
        source_data: Optional[str],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Run pipeline in background task.

        If `tools` is provided, skip backend tool collection and go straight to generation.
        """
        try:
            await self.state_machine.transition(context_id, PipelineState.INPUT_RECEIVED)

            if tools:
                context = self.state_machine.get_context(context_id)
                if not context:
                    return

                # Keep state machine transitions valid (INPUT_RECEIVED -> COLLECTING_TOOLS -> TOOLS_READY)
                await self.state_machine.transition(context_id, PipelineState.COLLECTING_TOOLS)
                context.tools = [Tool(**t) for t in tools]
                if self._has_only_placeholder_tools(context.tools):
                    await self._fail_no_endpoints(context_id)
                    return
                if not self._has_functional_api_tools(context.tools):
                    await self._fail_no_endpoints(context_id)
                    return
                await self.state_machine.transition(context_id, PipelineState.TOOLS_READY)
                await self.broadcast_ui_update(
                    UIUpdateType.TOOLS_UPDATED,
                    context_id,
                    {"tools_count": len(context.tools), "count": len(context.tools)},
                )
                await self._generate_code(context_id)
                return

            await self._collect_tools(context_id, source_type, source_data)

        except Exception as e:
            context = self.state_machine.get_context(context_id)
            if context:
                context.error = str(e)
            await self.broadcast_ui_update(UIUpdateType.ERROR, context_id, {"error": str(e)})
            logger.error(f"Pipeline {context_id} failed: {e}")

    async def _collect_tools(
        self,
        context_id: str,
        source_type: SourceType,
        source_data: Optional[str]
    ) -> None:
        """Collect tools from source"""
        context = self.state_machine.get_context(context_id)
        if not context:
            return

        self.logger.info(f"Collecting tools for {context_id}: source_type={source_type} source_data={source_data!r}")

        # Transition to collecting
        await self.state_machine.transition(
            context_id,
            PipelineState.COLLECTING_TOOLS
        )

        try:
            # Call backend API to collect tools
            if not self.client:
                raise RuntimeError("Agent not started")

            # Build request based on source type
            if source_type == SourceType.FILE:
                # For file, source_data should be file content
                # In real implementation, handle file upload
                self.logger.warning("SourceType.FILE not implemented yet; skipping tool collection.")
            elif source_type == SourceType.URL:
                last_exc: Optional[Exception] = None
                for backend_base in self.backend_urls:
                    try:
                        self.logger.info(f"Calling backend collect-tools: {backend_base}/collect-tools")
                        response = await self.client.post(
                            f"{backend_base}/collect-tools",
                            data={"url": source_data, "source_type": "url", "output_format": "json"},
                            timeout=120.0,
                        )
                        response.raise_for_status()
                        data = response.json()
                        tools = [Tool(**t) for t in data.get("tools", [])]
                        context.tools = tools
                        last_exc = None
                        break
                    except Exception as e:
                        last_exc = e
                        self.logger.warning(f"Backend collect-tools failed for {backend_base}: {e}")
                if last_exc is not None:
                    raise last_exc
            elif source_type == SourceType.SDK:
                last_exc: Optional[Exception] = None
                for backend_base in self.backend_urls:
                    try:
                        self.logger.info(f"Calling backend collect-tools: {backend_base}/collect-tools")
                        response = await self.client.post(
                            f"{backend_base}/collect-tools",
                            data={"sdk_name": source_data, "source_type": "sdk", "output_format": "json"},
                            timeout=120.0,
                        )
                        response.raise_for_status()
                        data = response.json()
                        tools = [Tool(**t) for t in data.get("tools", [])]
                        context.tools = tools
                        last_exc = None
                        break
                    except Exception as e:
                        last_exc = e
                        self.logger.warning(f"Backend collect-tools failed for {backend_base}: {e}")
                if last_exc is not None:
                    raise last_exc

            if self._has_only_placeholder_tools(context.tools):
                await self._fail_no_endpoints(context_id)
                return
            if not self._has_functional_api_tools(context.tools):
                await self._fail_no_endpoints(context_id)
                return

            # Transition to tools ready
            await self.state_machine.transition(
                context_id,
                PipelineState.TOOLS_READY
            )

            # Broadcast tools update
            await self.broadcast_ui_update(
                UIUpdateType.TOOLS_UPDATED,
                context_id,
                {"tools_count": len(context.tools), "count": len(context.tools)}
            )

            # Auto-start code generation
            await self._generate_code(context_id)

        except Exception as e:
            logger.error(f"Error collecting tools: {e}")
            error_str = str(e)
            
            # Provide user-friendly error message
            error_msg = error_str
            if "400" in error_str or "invalid" in error_str.lower() or "empty" in error_str.lower():
                error_msg = "Invalid Input. Please provide a valid API documentation link."
            elif "404" in error_str or "not found" in error_str.lower():
                error_msg = "Invalid Input. The provided URL could not be found. Please provide a valid API documentation link."
            elif "timeout" in error_str.lower():
                error_msg = "Request timed out. Please check your connection and try again."
            
            context.error = error_msg
            await self.broadcast_ui_update(
                UIUpdateType.ERROR,
                context_id,
                {
                    "error": error_msg,
                    "reset_pipeline": True,
                    "original_error": error_str
                }
            )
            
            # Transition to failed state
            try:
                await self.state_machine.transition(context_id, PipelineState.FAILED_FINAL)
            except Exception as transition_error:
                logger.warning(f"Error transitioning to FAILED_FINAL: {transition_error}")

    async def _generate_code(self, context_id: str) -> None:
        """Generate MCP code"""
        context = self.state_machine.get_context(context_id)
        if not context:
            return
        if self._has_only_placeholder_tools(context.tools):
            await self._fail_no_endpoints(context_id)
            return
        if not self._has_functional_api_tools(context.tools):
            await self._fail_no_endpoints(context_id)
            return

        self.logger.info(f"Generating code for {context_id}: tools={len(context.tools)} iteration={context.iteration + 1}")
        self.logger.info(f"Calling generator agent (candidates): {self.generator_urls}")

        # Transition to generating
        await self.state_machine.transition(
            context_id,
            PipelineState.GENERATING_CODE
        )

        try:
            # Prepare code generation request with MEMORY-AUGMENTED CONTEXT
            tools_dict = [t.model_dump() if hasattr(t, 'model_dump') else t.dict() for t in context.tools]
            validation_feedback = None
            
            # GOLDEN CODE RETENTION: Always use best version as baseline
            previous_code = None
            previous_score = 0
            previous_errors = []
            previous_warnings = []
            has_regression = False
            regression_message = None
            
            if context.iteration > 0:
                # Use golden code (best version) as the baseline
                if context.best_code and context.best_score > 0:
                    previous_code = context.best_code
                    previous_score = context.best_score
                    logger.info(f"🏆 Using GOLDEN CODE (iter {context.best_iteration}, score {context.best_score}) as baseline")
                    await self.broadcast_agent_thinking(
                        context_id,
                        "orchestrator",
                        f"Using golden code (iteration {context.best_iteration}, score {context.best_score}) as baseline",
                        "golden_code_used"
                    )
                elif context.generated_code:
                    previous_code = context.generated_code
                    previous_score = context.validation_result.quality_score if context.validation_result else 0
                    logger.info(f"Using previous code (score {previous_score}) as baseline")
                else:
                    logger.warning(f"No previous code available for iteration {context.iteration + 1}")
                
                # Check for regression in last iteration
                if context.metadata.get("last_regression"):
                    regression_info = context.metadata["last_regression"]
                    has_regression = True
                    regression_message = regression_info.get("regression_message", "")
                    logger.warning(f"⚠️ Last iteration caused regression. Will include regression message to Generator.")
                
                # Get validation feedback from best/golden code validation
                # Try to get from current validation result, or from code history
                if context.validation_result:
                    previous_errors = [e.model_dump() if hasattr(e, 'model_dump') else (e.dict() if hasattr(e, 'dict') else e) for e in context.validation_result.errors]
                    previous_warnings = [w.model_dump() if hasattr(w, 'model_dump') else (w.dict() if hasattr(w, 'dict') else w) for w in context.validation_result.warnings]
            
            # STRUCTURED VALIDATION FEEDBACK for Generator (Memory-Augmented Context)
            # Always include feedback structure for iterations 2+ to ensure Generator has context
            if context.iteration > 0 and previous_code:  # Only include feedback for iterations 2+ with previous code
                # NEW: Extract fix_instructions and regeneration_hints from validation metadata
                fix_instructions = []
                regeneration_hints = []
                if context.validation_result and context.validation_result.metadata:
                    fix_instructions = context.validation_result.metadata.get("fix_instructions", [])
                    regeneration_hints = context.validation_result.metadata.get("regeneration_hints", [])
                
                # Safely serialize suggestions (might contain ValidationIssue objects)
                suggestions = getattr(context.validation_result, 'suggestions', []) if context.validation_result else []
                safe_suggestions = safe_serialize(suggestions)
                
                validation_feedback = {
                    "approved": context.validation_result.approved if context.validation_result else False,
                    "quality_score": previous_score,  # Score from golden/best code
                    "previous_score": previous_score,  # Explicit previous score (critical for comparison)
                    "iteration": context.iteration,  # Current iteration number
                    "errors": previous_errors,  # Specific errors from Validator (already serialized above)
                    "warnings": previous_warnings,  # Specific warnings from Validator (already serialized above)
                    "suggestions": safe_suggestions,  # Safely serialized suggestions
                    "fix_instructions": fix_instructions,  # NEW: Actionable fix instructions from Ruff/MCP Inspector
                    "regeneration_hints": regeneration_hints,  # NEW: High-level hints for regeneration
                    "llm_validation": context.validation_result.llm_validation.model_dump() if context.validation_result and context.validation_result.llm_validation else None,
                    "feedback": context.validation_result.feedback if context.validation_result else None,
                    "has_regression": has_regression,  # Flag indicating last iteration caused regression
                    "regression_message": regression_message,  # Explicit message to Generator about regression (if applicable)
                    # NEW: Complete history so Generator knows what was tried before
                    "history": safe_serialize(context.code_history[-5:] if context.code_history else []),  # Last 5 iterations (safely serialized)
                    "best_score": context.best_score,  # Best score achieved so far
                    "best_iteration": context.best_iteration,  # Iteration where best code was generated
                    "total_iterations": context.iteration,  # Total iterations so far
                }
                
                # CRITICAL: Apply safe_serialize to entire feedback dict to catch any nested Pydantic models
                validation_feedback = safe_serialize(validation_feedback)
                logger.info(f"📋 Memory-augmented feedback prepared: previous_score={previous_score}, errors={len(previous_errors)}, warnings={len(previous_warnings)}, fix_instructions={len(fix_instructions)}, regression={has_regression}, history_entries={len(context.code_history)}")
            elif context.iteration == 0:
                # First iteration - no feedback needed
                validation_feedback = None

            # Create A2A request for generator with iterative context
            a2a_request = A2AProtocol.create_code_generation_request(
                tools=tools_dict,
                context_id=context_id,
                iteration=context.iteration + 1,
                feedback=validation_feedback,
                previous_code=previous_code if context.iteration > 0 else None  # Include previous code for refactoring
            )

            # Broadcast thinking log
            action = "REFACTORING" if context.iteration > 0 and context.generated_code else "GENERATING"
            await self.broadcast_agent_thinking(
                context_id,
                "orchestrator",
                f"{action} code for iteration {context.iteration + 1}...",
                "generation_request"
            )
            
            # Send to generator agent (try multiple candidates)
            last_resp: Optional[A2AResponse] = None
            for gen_url in self.generator_urls:
                self.logger.info(f"Sending codegen request to {gen_url}")
                try:
                    if context.iteration > 0:
                        await self.broadcast_agent_thinking(
                            context_id,
                            "generator",
                            f"Refactoring previous code to fix {len(validation_feedback.get('errors', [])) if validation_feedback else 0} errors...",
                            "refactoring"
                        )
                    else:
                        await self.broadcast_agent_thinking(
                            context_id,
                            "generator",
                            f"Generating new MCP server code for {len(tools_dict)} tools...",
                            "generating"
                        )
                    resp = await self.send_message(gen_url, a2a_request, timeout=120.0)
                    last_resp = resp
                    code_try = A2AProtocol.parse_generated_code(resp)
                    if code_try:
                        response = resp
                        code = code_try
                        break
                except Exception as e:
                    self.logger.error(f"Error sending to {gen_url}: {e}")
            else:
                response = last_resp
                code = None

            if code and code.strip():
                # Store code temporarily (will be validated and potentially rejected if regression)
                context.generated_code = code
                self.state_machine.increment_iteration(context_id)
                
                # Initialize golden code on first iteration if not set
                if context.best_code is None:
                    context.best_code = code
                    context.best_score = 0  # Will be updated after validation
                    context.best_iteration = context.iteration
                    logger.info(f"🏆 Initializing golden code (iteration {context.iteration})")

                # SAVE CODE TO DISK - mcp-generator/mcp_server_generated.py
                try:
                    from pathlib import Path
                    
                    # Determine output path
                    mcp_generator_dir = Path(__file__).parent.parent.parent / "mcp-generator"
                    mcp_generator_dir.mkdir(exist_ok=True)
                    
                    # Always overwrite main file
                    output_file = mcp_generator_dir / "mcp_server_generated.py"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(code)
                    logger.info(f"✅ Code saved to {output_file} ({len(code)} chars, {code.count(chr(10)) + 1} lines)")
                    
                    # Always create unique iteration-specific file for tracking changes
                    iteration_file = mcp_generator_dir / f"mcp_server_generated_iter_{context.iteration}.py"
                    with open(iteration_file, 'w', encoding='utf-8') as f:
                        f.write(code)
                    logger.info(f"✅ Iteration {context.iteration} saved to {iteration_file}")
                    
                except Exception as save_error:
                    logger.error(f"⚠️ Failed to save code to disk: {save_error}")
                    # Don't fail the pipeline if file save fails

                # Broadcast code generated
                await self.broadcast_ui_update(
                    UIUpdateType.CODE_GENERATED,
                    context_id,
                    {"iteration": context.iteration, "code_length": len(code)}
                )

                # Transition to awaiting validation
                await self.state_machine.transition(
                    context_id,
                    PipelineState.AWAITING_VALIDATION
                )

                # Manual mode - user must click "Validate Code Now" button
                logger.info(f"⏸️  Code generated (iteration {context.iteration}). Waiting for user to click 'Validate Code Now' button.")
            else:
                # ============================================================
                # STRICT AI-ONLY GENERATION - NO FALLBACK ALLOWED
                # ============================================================
                # If AI generator returns empty/error, HARD STOP the pipeline.
                # Do NOT proceed with empty code.
                error_msg = "AI Generator failed to produce code. No fallback allowed. Pipeline STOPPED."
                if response and hasattr(response, 'error') and response.error:
                    error_msg = f"AI Generator error: {response.error.get('message', 'Unknown error')}. Pipeline STOPPED."
                
                logger.error(f"❌ {error_msg}")
                context.error = error_msg
                
                await self.broadcast_ui_update(
                    UIUpdateType.ERROR,
                    context_id,
                    {
                        "error": error_msg,
                        "iteration": context.iteration + 1,
                        "fatal": True,  # Indicate this is a fatal error
                        "action_required": "Check AI API key/quota and retry"
                    }
                )
                
                # Transition to failed state
                await self.state_machine.transition(
                    context_id,
                    PipelineState.FAILED_FINAL
                )
                return  # HARD STOP - do not continue

        except Exception as e:
            logger.error(f"Error generating code: {e}")
            context.error = str(e)
            await self.broadcast_ui_update(
                UIUpdateType.ERROR,
                context_id,
                {"error": str(e)}
            )

    async def _validate_code(self, context_id: str, auto: bool = False) -> None:
        """Validate generated code"""
        context = self.state_machine.get_context(context_id)
        if not context or not context.generated_code:
            return

        # Cancel timer if manual trigger
        if not auto:
            await self.state_machine.cancel_timer(context_id, "validate")

        # Transition to validating
        await self.state_machine.transition(
            context_id,
            PipelineState.VALIDATING_CODE
        )

        try:
            # Create A2A request for validator with regression testing context
            previous_code = None
            if context.iteration > 1 and context.code_history:
                # Get previous iteration code for regression testing
                prev_iter_entry = next((h for h in context.code_history if h["iteration"] == context.iteration - 1), None)
                # We need to get the actual code from the history, but we don't store it there
                # Instead, we'll use best_code as the baseline for regression testing
                previous_code = context.best_code if context.best_code else None
            
            a2a_request = A2AProtocol.create_validation_request(
                code=context.generated_code,
                context_id=context_id,
                iteration=context.iteration,
                previous_code=previous_code,
                best_code=context.best_code,
                best_score=context.best_score
            )

            try:
                # Broadcast thinking log
                await self.broadcast_agent_thinking(
                    context_id,
                    "orchestrator",
                    f"Sending code to Validator for iteration {context.iteration}...",
                    "validation_request"
                )
                
                # Send to validator agent
                response = await self.send_message(self.validator_url, a2a_request, timeout=120.0)

                # Broadcast thinking log
                await self.broadcast_agent_thinking(
                    context_id,
                    "validator",
                    "Analyzing code structure and MCP compliance...",
                    "analyzing"
                )

                # Parse validation result
                result_dict = A2AProtocol.parse_validation_response(response)
                
                # Broadcast score calculation thinking
                quality_score = result_dict.get("quality_score", 0)
                await self.broadcast_agent_thinking(
                    context_id,
                    "validator",
                    f"Calculating progressive score: base=50 + category bonuses...",
                    "scoring"
                )
                
            except Exception as e:
                raise

            from shared.message_types import ValidationResponse
            context.validation_result = ValidationResponse(**result_dict)
            
            # GOLDEN CODE RETENTION: Track best version and reject regressions
            current_score = context.validation_result.quality_score
            current_code = context.generated_code
            
            # Record this iteration in code history with COMPLETE information
            # This history will be sent to Generator so it knows what was tried before
            history_entry = {
                "iteration": context.iteration,
                "score": current_score,
                "approved": context.validation_result.approved,
                "code": current_code[:500] if current_code else "",  # Store first 500 chars as preview
                "code_length": len(current_code) if current_code else 0,
                "timestamp": datetime.utcnow().isoformat(),
                "errors": [e.model_dump() if hasattr(e, 'model_dump') else (e.dict() if hasattr(e, 'dict') else e) for e in context.validation_result.errors[:3]],  # Top 3 errors
                "warnings": [w.model_dump() if hasattr(w, 'model_dump') else (w.dict() if hasattr(w, 'dict') else w) for w in context.validation_result.warnings[:3]],  # Top 3 warnings
                "errors_count": len(context.validation_result.errors),
                "warnings_count": len(context.validation_result.warnings),
                "suggestions_count": len(getattr(context.validation_result, 'suggestions', [])),
            }
            context.code_history.append(history_entry)
            
            # Update golden code if this is better
            is_improvement = current_score > context.best_score
            if is_improvement and current_code:
                context.best_code = current_code
                context.best_score = current_score
                context.best_iteration = context.iteration
                await self.broadcast_agent_thinking(
                    context_id,
                    "orchestrator",
                    f"🏆 NEW GOLDEN CODE! Score improved to {current_score}/100 (iteration {context.iteration})",
                    "golden_code_update"
                )
                logger.info(f"🏆 Golden code updated: iteration {context.iteration}, score {current_score}/100")
            elif current_score < context.best_score and context.best_score > 0:
                # GATEKEEPER LOGIC: REGRESSION DETECTED - Reject and instruct Generator to try different approach
                score_drop = context.best_score - current_score
                regression_msg = f"❌ GATEKEEPER: REGRESSION DETECTED - Score dropped from {context.best_score} to {current_score} (drop: -{score_drop}). REJECTING this version."
                logger.warning(regression_msg)
                await self.broadcast_agent_thinking(
                    context_id,
                    "orchestrator",
                    regression_msg,
                    "regression_detected"
                )
                
                # Store rejected code and validation result for analysis
                rejected_code = context.generated_code
                rejected_validation = context.validation_result
                
                # Revert to golden code
                context.generated_code = context.best_code
                
                # Get previous validation result (from best iteration)
                # Note: We need to store validation results in code_history
                previous_errors = rejected_validation.errors if rejected_validation else []
                previous_warnings = rejected_validation.warnings if rejected_validation else []
                
                # Mark this as a regression with detailed information for Generator
                context.metadata["last_regression"] = {
                    "iteration": context.iteration,
                    "rejected_score": current_score,
                    "golden_score": context.best_score,
                    "golden_iteration": context.best_iteration,
                    "score_drop": score_drop,
                    "rejected_errors": [e.model_dump() if hasattr(e, 'model_dump') else (e.dict() if hasattr(e, 'dict') else e) for e in previous_errors],
                    "rejected_warnings": [w.model_dump() if hasattr(w, 'model_dump') else (w.dict() if hasattr(w, 'dict') else w) for w in previous_warnings],
                    "regression_message": f"Your last fix caused a regression (score dropped from {context.best_score} to {current_score}). Revert to golden code (iteration {context.best_iteration}) and try a DIFFERENT approach to fix the issues WITHOUT breaking existing functionality."
                }
                
                # Keep the rejected validation result for comparison, but use golden code
                logger.info(f"🔄 Reverted to golden code (iteration {context.best_iteration}, score {context.best_score})")
            
            # Broadcast score change notification
            previous_score = context.metadata.get("last_score", None)
            if previous_score is not None and previous_score != current_score:
                await self.broadcast_ui_update(
                    UIUpdateType.SCORE_CHANGE,
                    context_id,
                    {
                        "previous_score": previous_score,
                        "current_score": current_score,
                        "change": current_score - previous_score,
                        "iteration": context.iteration,
                        "is_regression": current_score < previous_score,
                        "best_score": context.best_score,
                        "best_iteration": context.best_iteration
                    }
                )
                change_msg = f"Score changed: {previous_score} → {current_score} ({'+' if current_score > previous_score else ''}{current_score - previous_score})"
                if current_score < previous_score:
                    change_msg += f" | 🏆 Best: {context.best_score} (iter {context.best_iteration})"
                await self.broadcast_agent_thinking(
                    context_id,
                    "orchestrator",
                    change_msg,
                    "score_change"
                )
            context.metadata["last_score"] = current_score

            # Transition to validation result
            await self.state_machine.transition(
                context_id,
                PipelineState.VALIDATION_RESULT
            )

            # Build COMPLETE validation result for UI (ensure all fields are included)
            complete_validation_result = {
                "approved": context.validation_result.approved,
                "quality_score": context.validation_result.quality_score,
                "iteration": context.validation_result.iteration or context.iteration,
                "errors": [e.model_dump() if hasattr(e, 'model_dump') else (e.dict() if hasattr(e, 'dict') else e) for e in context.validation_result.errors],
                "warnings": [w.model_dump() if hasattr(w, 'model_dump') else (w.dict() if hasattr(w, 'dict') else w) for w in context.validation_result.warnings],
                "suggestions": [s.model_dump() if hasattr(s, 'model_dump') else (s.dict() if hasattr(s, 'dict') else s) for s in getattr(context.validation_result, 'suggestions', [])],
                "feedback": context.validation_result.feedback,
                "llm_validation": context.validation_result.llm_validation.model_dump() if context.validation_result.llm_validation else None,
                # Add metadata for UI
                "context_id": context_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            logger.info(f"📊 Validation Result: score={context.validation_result.quality_score}, approved={context.validation_result.approved}, errors={len(context.validation_result.errors)}, warnings={len(context.validation_result.warnings)}")

            # Broadcast COMPLETE validation result to UI
            await self.broadcast_ui_update(
                UIUpdateType.VALIDATION_RESULT,
                context_id,
                complete_validation_result
            )

            # Determine next state
            if context.validation_result.approved:
                # Success!
                await self.state_machine.transition(
                    context_id,
                    PipelineState.DONE
                )
            elif self.state_machine.can_regenerate(context_id):
                # Can regenerate
                await self.state_machine.transition(
                    context_id,
                    PipelineState.AWAITING_REGEN
                )

                # ============================================================
                # 10-SECOND AUTO-REGENERATION TIMER (DISABLED FOR MANUAL MODE)
                # ============================================================
                # Uncomment the lines below to enable automatic regeneration after 10 seconds
                # await self.state_machine.start_regeneration_timer(
                #     context_id,
                #     lambda: asyncio.create_task(self._regenerate_code(context_id, auto=True))
                # )
                # ============================================================

                logger.info(f"⏸️  Auto-regeneration DISABLED. Please click 'Regenerate Code' button manually.")
            else:
                # Max iterations reached
                await self.state_machine.transition(
                    context_id,
                    PipelineState.FAILED_FINAL
                )

        except Exception as e:
            logger.error(f"Error validating code: {e}")
            context.error = str(e)
            await self.broadcast_ui_update(
                UIUpdateType.ERROR,
                context_id,
                {"error": str(e)}
            )

    async def _regenerate_code(self, context_id: str, auto: bool = False) -> None:
        """Regenerate code with feedback"""
        # Cancel timer if manual trigger
        if not auto:
            await self.state_machine.cancel_timer(context_id, "regenerate")

        # Transition to regenerating
        await self.state_machine.transition(
            context_id,
            PipelineState.REGENERATING_CODE
        )

        # Generate code again (with feedback from validation)
        await self._generate_code(context_id)

    async def trigger_validation(self, context_id: str, manual: bool = True) -> None:
        """Manually trigger validation"""
        if manual:
            await self.state_machine.handle_hitl_decision(
                context_id,
                "validate",
                HITLDecision.MANUAL
            )
        await self._validate_code(context_id, auto=not manual)

    async def trigger_regeneration(self, context_id: str, manual: bool = True) -> None:
        """Manually trigger regeneration"""
        if manual:
            await self.state_machine.handle_hitl_decision(
                context_id,
                "regenerate",
                HITLDecision.MANUAL
            )
        await self._regenerate_code(context_id, auto=not manual)

    async def broadcast_agent_thinking(
        self,
        context_id: str,
        agent_name: str,
        thinking: str,
        stage: Optional[str] = None
    ) -> None:
        """
        Broadcast real-time thinking logs from agents to UI.
        
        Args:
            context_id: Pipeline context ID
            agent_name: Name of the agent (orchestrator, generator, validator)
            thinking: Thinking/reasoning message
            stage: Optional stage identifier (e.g., "scoring", "analyzing", "refactoring")
        """
        await self.broadcast_ui_update(
            UIUpdateType.AGENT_THINKING,
            context_id,
            {
                "agent": agent_name,
                "thinking": thinking,
                "stage": stage,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        logger.debug(f"[{agent_name}] {stage or 'thinking'}: {thinking[:100]}...")

    async def broadcast_ui_update(
        self,
        update_type: UIUpdateType,
        context_id: str,
        data: Dict[str, Any]
    ) -> None:
        """
        Broadcast update to:
        - any clients connected to this orchestrator's WebSocket (/ws)
        - UI Controller Agent (so the React UI can receive updates via ws://127.0.0.1:8102/ws)
        
        ROBUST: Automatically serializes Pydantic models to prevent JSON errors.
        """
        # Safely serialize all data to prevent "Object of type X is not JSON serializable" errors
        safe_data = safe_serialize(data)
        
        update = create_ui_update(update_type, context_id, safe_data)
        message = update.json()

        payload = {
            "type": update_type.value,
            "context_id": context_id,
            "data": safe_data,
        }

        disconnected = []
        for ws in self.websocket_connections:
            try:
                await ws.send_text(message)
            except Exception as e:
                logger.warning(f"Error sending to WebSocket: {e}")
                disconnected.append(ws)

        # Remove disconnected clients
        for ws in disconnected:
            self.websocket_connections.remove(ws)

        # Forward to UI Controller Agent (best-effort).
        if self.client:
            for base in self.ui_controller_urls:
                try:
                    await self.client.post(f"{base}/broadcast", json=payload, timeout=5.0)
                    break
                except Exception as e:
                    logger.warning(f"Failed to forward UI update to UI Controller via {base}: {e}")

    async def run(self) -> None:
        """Run the orchestrator agent server"""
        await self.start()
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        logger.info(f"Orchestrator Agent running on {self.base_url}")
        await server.serve()


# Standalone execution
async def main():
    agent = OrchestratorAgent()
    await agent.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
