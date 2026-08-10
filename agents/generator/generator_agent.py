# Edited by Dr. Wasim
"""
Generator Agent with real-time telemetry.

Emits agent-native telemetry events to UI Controller for live timeline:
- request_received
- execution_started
- llm_call_started
- llm_call_heartbeat
- llm_call_completed
- response_sent
"""
import os
import json
import time
import uuid
import asyncio
import logging
from typing import Optional, Dict, Any, List, Union

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx
from dotenv import load_dotenv

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2ARequest, A2AResponse, A2AMessage, MessageRole
from shared.message_types import AgentType

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.error("OpenAI SDK not available. Install with: pip install openai")


class GeneratorAgent(BaseAgent):
    def __init__(self, host: str = "localhost", port: int = 8101, model: Optional[str] = None):
        super().__init__(agent_type=AgentType.GENERATOR, name="generator", host=host, port=port)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.openai_client: Optional[AsyncOpenAI] = None
        self.telemetry_client: Optional[httpx.AsyncClient] = None
        self.ui_controller_url = "http://127.0.0.1:8102/telemetry"
        self.app = FastAPI(title="Generator Agent")
        self._setup_routes()
        self._init_openai()

    def _init_openai(self) -> None:
        if not OPENAI_AVAILABLE:
            return
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY missing; generator disabled.")
            return
        self.openai_client = AsyncOpenAI(api_key=api_key)
        self.telemetry_client = httpx.AsyncClient(timeout=5.0)
        logger.info(f"Using OpenAI model: {self.model}")

    def _setup_routes(self) -> None:
        app = self.app
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.post("/a2a")
        async def handle_a2a_message(request_dict: Dict[str, Any]) -> Dict[str, Any]:
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

        @app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "agent": self.name,
                "openai_available": self.openai_client is not None,
                "model": self.model
            }

    async def handle_message(self, request: A2ARequest) -> A2AResponse:
        message = A2AMessage.from_dict(request.params.get("message", {}))
        context_id = message.context_id
        req_id = request.request_id
        await self._emit_telemetry(req_id, context_id, "request_received")
        tools: List[Dict[str, Any]] = []
        iteration = 1
        feedback: Optional[Union[str, Dict[str, Any]]] = None
        previous_code: Optional[str] = None

        feedback_dict = None
        for part in message.parts:
            if part.get("kind") == "data":
                data = part.get("data", {})
                if "tools" in data:
                    tools = data["tools"]
                if "validation_feedback" in data:
                    feedback_dict = data["validation_feedback"]
            elif part.get("kind") == "code":
                previous_code = part.get("code", "")
        metadata = message.metadata
        if metadata:
            iteration = metadata.get("iteration", 1)
            if metadata.get("has_feedback") or metadata.get("has_previous_code"):
                if feedback_dict:
                    feedback = feedback_dict
                    if isinstance(feedback_dict, dict) and "previous_code" in feedback_dict:
                        previous_code = feedback_dict.get("previous_code") or previous_code

        await self._emit_telemetry(req_id, context_id, "execution_started")
        code = await self.generate_code(tools, iteration, feedback, previous_code, req_id, context_id)
        if code:
            await self._emit_telemetry(req_id, context_id, "response_sent", {"status": "success"})
            result_message = A2AMessage(
                context_id=context_id,
                role=MessageRole.ASSISTANT
            ).add_code_part(code, "python")
            return A2AResponse.success(
                request_id=request.request_id,
                result={"code": code, "iteration": iteration, "message": result_message.to_dict()}
            )
        await self._emit_telemetry(req_id, context_id, "response_sent", {"status": "error", "reason": "Code generation failed"})
        return A2AResponse.error(
            request_id=request.request_id,
            code=-32001,
            message="Code generation failed"
        )

    async def generate_code(
        self,
        tools: List[Dict[str, Any]],
        iteration: int = 1,
        feedback: Optional[Union[str, Dict[str, Any]]] = None,
        previous_code: Optional[str] = None,
        request_id: Optional[str] = None,
        context_id: Optional[str] = None,
    ) -> Optional[str]:
        if not self.openai_client:
            logger.error("OpenAI client not initialized - cannot generate code")
            return None
        return await self._generate_with_openai(tools, iteration, feedback, previous_code, request_id, context_id)

    async def _generate_with_openai(
        self,
        tools: List[Dict[str, Any]],
        iteration: int,
        feedback: Optional[Union[str, Dict[str, Any]]],
        previous_code: Optional[str],
        request_id: Optional[str],
        context_id: Optional[str],
    ) -> Optional[str]:
        stop_heartbeat: Optional[asyncio.Event] = None
        heartbeat_task: Optional[asyncio.Task] = None
        try:
            prompt = self._build_generation_prompt(tools, iteration, feedback, previous_code)
            await self._emit_telemetry(request_id, context_id, "llm_call_started", {"iteration": iteration})
            stop_heartbeat = asyncio.Event()
            heartbeat_task = asyncio.create_task(self._llm_heartbeat(stop_heartbeat, request_id, context_id, iteration))

            # Build system prompt based on iteration
            if iteration > 1 and feedback:
                system_content = (
                    "You are a PURE PYTHON expert specializing in FastMCP server implementations. "
                    "You are in ITERATION MODE - fixing errors and improving code quality.\n\n"
                    "🎯 YOUR PRIMARY GOAL: FIX ALL ERRORS AND WARNINGS\n\n"
                    "CRITICAL RULES FOR ERROR FIXING:\n"
                    "1. READ THE FIX INSTRUCTIONS CAREFULLY - Each instruction tells you EXACTLY what to fix and HOW\n"
                    "2. PRESERVE WORKING CODE - Only modify the problematic parts, keep everything else intact\n"
                    "3. FOLLOW SUGGESTED SOLUTIONS - If a fix instruction provides example code, USE IT\n"
                    "4. TEST YOUR FIXES - Ensure each fix doesn't break other parts of the code\n"
                    "5. NEVER use JavaScript syntax - ALWAYS use Python 3.10+ syntax\n"
                    "6. ALWAYS produce valid Python that passes ast.parse()\n"
                    "7. If a previous fix caused regression, TRY A DIFFERENT APPROACH\n\n"
                    "CODE QUALITY STANDARDS:\n"
                    "- Import all required modules (FastMCP, httpx, json, asyncio, etc.)\n"
                    "- Use proper error handling (try/except)\n"
                    "- Add docstrings to functions\n"
                    "- Follow PEP 8 style guidelines\n"
                    "- Use type hints where appropriate\n\n"
                    "Remember: Your previous code had errors. Focus on fixing them WITHOUT breaking what works."
                )
                # Lower temperature for error fixing (more focused)
                temperature = 0.3
                top_p = 0.9
            else:
                system_content = (
                    "You are a PURE PYTHON expert specializing in FastMCP server implementations. "
                    "Generate production-ready, well-structured, and thoroughly documented code using ONLY standard Python 3.10+ syntax.\n\n"
                    "CRITICAL RULES:\n"
                    "- NEVER use JavaScript syntax\n"
                    "- ALWAYS produce valid Python that passes ast.parse()\n"
                    "- Import all required modules (FastMCP, httpx, json, asyncio, etc.)\n"
                    "- Use proper error handling with try/except blocks\n"
                    "- Add comprehensive docstrings to all functions\n"
                    "- Follow PEP 8 style guidelines\n"
                    "- Use type hints where appropriate\n"
                    "- Every tool MUST be defined with the @mcp.tool decorator pattern used by FastMCP\n"
                    "- For HTTP tools, only generate code when method+path are present\n"
                    "- For SDK tools (metadata source python_sdk or sdk_module/sdk_function), generate tools even if method/path are missing\n"
                    "- Ignore placeholder tools like raw_url_docs when building code\n"
                    "- If no tools are provided, DO NOT generate a fallback server; return only this exact error message: "
                    "'Generation failed: No valid API endpoints found.'\n"
                    "- If tools only include placeholders (e.g., raw_url_docs) and no HTTP or SDK tools are present, return only: "
                    "'Generation failed: No valid API endpoints found.'"
                )
                # Normal temperature for initial generation
                temperature = 0.7
                top_p = 0.95

            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                top_p=top_p,
                max_tokens=16000,
                presence_penalty=0.6,
                frequency_penalty=0.3,
            )

            if response and response.choices:
                response_text = response.choices[0].message.content
                code = self._extract_code_from_response(response_text)
                await self._emit_telemetry(request_id, context_id, "llm_call_completed", {"iteration": iteration})
                if code and code.strip():
                    lines = code.count("\n") + 1
                    logger.info(f"Generated {len(code)} chars, {lines} lines (iteration {iteration})")
                    if stop_heartbeat:
                        stop_heartbeat.set()
                        if heartbeat_task:
                            await heartbeat_task
                    return code
            await self._emit_telemetry(request_id, context_id, "llm_call_completed", {"iteration": iteration, "error": "empty_response"})
            if stop_heartbeat:
                stop_heartbeat.set()
                if heartbeat_task:
                    await heartbeat_task
            return None
        except Exception as e:
            logger.error(f"Error generating with OpenAI: {e}")
            await self._emit_telemetry(request_id, context_id, "llm_call_completed", {"iteration": iteration, "error": str(e)})
            if stop_heartbeat:
                stop_heartbeat.set()
                if heartbeat_task:
                    try:
                        await heartbeat_task
                    except Exception:
                        pass
            return None

    async def _llm_heartbeat(self, stop_event: asyncio.Event, request_id: Optional[str], context_id: Optional[str], iteration: int) -> None:
        while not stop_event.is_set():
            await self._emit_telemetry(request_id, context_id, "llm_call_in_progress", {"iteration": iteration})
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

    async def _emit_telemetry(self, request_id: Optional[str], context_id: Optional[str], event_type: str, extra: Optional[Dict[str, Any]] = None) -> None:
        if not self.telemetry_client:
            return
        payload = {
            "event_id": str(uuid.uuid4()),
            "agent": "generator",
            "event_type": event_type,
            "context_id": context_id,
            "request_id": request_id,
            "send_ts": int(time.time() * 1000),
        }
        if extra:
            payload.update(extra)
        try:
            await self.telemetry_client.post(self.ui_controller_url, json=payload)
        except Exception as e:
            logger.debug(f"Telemetry send failed: {e}")

    def _build_generation_prompt(
        self,
        tools: List[Dict[str, Any]],
        iteration: int,
        feedback: Optional[Union[str, Dict[str, Any]]],
        previous_code: Optional[str] = None,
    ) -> str:
        tools_count = len(tools)
        prompt = (
            f"Generate MCP server code for iteration {iteration}.\n"
            f"Tools count: {tools_count}\n\n"
            "HARD REQUIREMENTS:\n"
            "- If tools count is 0, return ONLY this exact error message and nothing else:\n"
            "  Generation failed: No valid API endpoints found.\n"
            "- If tools only include placeholder tools (e.g., raw_url_docs) OR if no tools have both an HTTP method+path and no SDK tools exist, return ONLY:\n"
            "  Generation failed: No valid API endpoints found.\n"
            "- For HTTP tools: only implement tools that have BOTH a valid HTTP method and a non-empty path.\n"
            "- For SDK tools (metadata source python_sdk or sdk_module/sdk_function), implement them even without method/path.\n"
            "- Ignore placeholder tools like raw_url_docs when generating code.\n"
            "- If tools are present, every tool MUST use the @mcp.tool decorator pattern required by FastMCP.\n"
            "- Do NOT generate generic fallback servers or placeholder MCPServer classes.\n\n"
            f"Tools:\n{json.dumps(tools, indent=2)}\n"
        )
        if iteration > 1 and previous_code:
            prompt += "\nPrevious code (refactor, do not rewrite completely):\n```python\n"
            prompt += previous_code
            prompt += "\n```\n"
        if feedback:
            prompt += "\nFeedback to address:\n"
            
            # NEW: Enhanced feedback with fix_instructions and COMPLETE HISTORY
            if isinstance(feedback, dict):
                # Extract structured components
                fix_instructions = feedback.get("fix_instructions", [])
                regeneration_hints = feedback.get("regeneration_hints", [])
                errors = feedback.get("errors", [])
                warnings = feedback.get("warnings", [])
                quality_score = feedback.get("quality_score", 0)
                history = feedback.get("history", [])
                best_score = feedback.get("best_score", 0)
                best_iteration = feedback.get("best_iteration", 0)
                total_iterations = feedback.get("total_iterations", 0)
                
                prompt += f"\n**Previous Quality Score: {quality_score}/100**\n"
                prompt += f"**Best Score So Far: {best_score}/100 (achieved in iteration {best_iteration})**\n"
                prompt += f"**Current Progress: Iteration {total_iterations}**\n\n"
                
                # Add HISTORY so Generator knows what was tried before
                if history:
                    prompt += "\n📊 **ITERATION HISTORY** (Learn from past attempts):\n"
                    prompt += "=" * 60 + "\n"
                    for h in history:
                        iter_num = h.get("iteration", "?")
                        score = h.get("score", 0)
                        approved = h.get("approved", False)
                        errors_count = h.get("errors_count", 0)
                        warnings_count = h.get("warnings_count", 0)
                        
                        status = "✅ Approved" if approved else "❌ Rejected"
                        prompt += f"\nIteration {iter_num}: Score {score}/100 {status}\n"
                        prompt += f"  - Errors: {errors_count}, Warnings: {warnings_count}\n"
                        
                        # Show specific errors from history
                        hist_errors = h.get("errors", [])
                        if hist_errors:
                            prompt += f"  - Issues: "
                            for e in hist_errors[:2]:  # First 2 errors
                                msg = e.get("message", str(e)) if isinstance(e, dict) else str(e)
                                prompt += f"{msg}; "
                            prompt += "\n"
                    prompt += "=" * 60 + "\n"
                    prompt += f"\n⚠️ **KEY INSIGHT**: You've tried {len(history)} times. Learn from these mistakes!\n\n"
                
                # Add fix_instructions with high priority
                if fix_instructions:
                    prompt += "\n**🔧 CRITICAL FIX INSTRUCTIONS (MUST ADDRESS):**\n"
                    for i, fix in enumerate(fix_instructions, 1):
                        error_code = fix.get("error_code", "UNKNOWN")
                        line = fix.get("line", "?")
                        message = fix.get("message", "Unknown error")
                        instruction = fix.get("fix_instruction", "No instruction")
                        suggested = fix.get("suggested_code", "")
                        
                        prompt += f"\n{i}. **{error_code}** at line {line}\n"
                        prompt += f"   - Problem: {message}\n"
                        prompt += f"   - Solution: {instruction}\n"
                        if suggested:
                            prompt += f"   - Example: `{suggested}`\n"
                
                # Add regeneration hints
                if regeneration_hints:
                    prompt += "\n**💡 IMPORTANT HINTS:**\n"
                    for hint in regeneration_hints:
                        prompt += f"- {hint}\n"
                
                # Add errors and warnings
                if errors:
                    prompt += "\n**🔴 ERRORS TO FIX:**\n"
                    for err in errors[:5]:  # Limit to first 5
                        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                        prompt += f"- {msg}\n"
                
                if warnings:
                    prompt += "\n**🟡 WARNINGS TO ADDRESS:**\n"
                    for warn in warnings[:5]:  # Limit to first 5
                        msg = warn.get("message", str(warn)) if isinstance(warn, dict) else str(warn)
                        prompt += f"- {msg}\n"
                
                prompt += "\n"
            else:
                prompt += str(feedback)
        
        return prompt

    def _extract_code_from_response(self, response_text: str) -> str:
        if "```python" in response_text:
            start = response_text.find("```python") + 9
            end = response_text.find("```", start)
            if end > start:
                return response_text[start:end].strip()
        if "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end > start:
                return response_text[start:end].strip()
        return response_text.strip()

    async def run(self) -> None:
        await self.start()
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        server = uvicorn.Server(config)
        logger.info(f"Generator Agent running on {self.base_url}")
        await server.serve()


async def main():
    agent = GeneratorAgent()
    await agent.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
