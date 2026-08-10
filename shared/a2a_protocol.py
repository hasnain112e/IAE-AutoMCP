"""
A2A (Agent-to-Agent) Protocol Utilities

Implements JSON-RPC 2.0 messaging for agent communication
using Google ADK's A2A protocol standards.
"""
import uuid
import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MessageRole(str, Enum):
    """Message roles in A2A protocol"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class PartKind(str, Enum):
    """Part kinds in message content"""
    TEXT = "text"
    DATA = "data"
    CODE = "code"
    IMAGE = "image"


class A2AMessage:
    """
    A2A Message wrapper for JSON-RPC 2.0 format

    Follows Google ADK A2A specification for agent-to-agent communication.
    """

    def __init__(
        self,
        message_id: Optional[str] = None,
        context_id: Optional[str] = None,
        role: MessageRole = MessageRole.USER,
        parts: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.message_id = message_id or self._generate_id()
        self.context_id = context_id or "default"
        self.role = role
        self.parts = parts or []
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow().isoformat()

    @staticmethod
    def _generate_id() -> str:
        """Generate unique message ID"""
        return f"msg-{uuid.uuid4().hex[:12]}"

    def add_text_part(self, text: str) -> 'A2AMessage':
        """Add text part to message"""
        self.parts.append({
            "kind": PartKind.TEXT.value,
            "text": text
        })
        return self

    def add_code_part(self, code: str, language: str = "python") -> 'A2AMessage':
        """Add code part to message"""
        self.parts.append({
            "kind": PartKind.CODE.value,
            "code": code,
            "language": language
        })
        return self

    def add_data_part(self, data: Dict[str, Any]) -> 'A2AMessage':
        """Add structured data part"""
        self.parts.append({
            "kind": PartKind.DATA.value,
            "data": data
        })
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "messageId": self.message_id,
            "contextId": self.context_id,
            "role": self.role.value,
            "parts": self.parts,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'A2AMessage':
        """Create message from dictionary"""
        msg = cls(
            message_id=data.get("messageId"),
            context_id=data.get("contextId"),
            role=MessageRole(data.get("role", "user")),
            parts=data.get("parts", []),
            metadata=data.get("metadata", {})
        )
        if "timestamp" in data:
            msg.timestamp = data["timestamp"]
        return msg


class A2ARequest:
    """
    JSON-RPC 2.0 Request for A2A communication
    """

    def __init__(
        self,
        method: str,
        message: A2AMessage,
        request_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ):
        self.jsonrpc = "2.0"
        self.method = method
        self.request_id = request_id or f"req-{uuid.uuid4().hex[:12]}"
        self.params = params or {}
        self.params["message"] = message.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-RPC 2.0 format"""
        return {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "id": self.request_id,
            "params": self.params
        }

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'A2ARequest':
        """Create request from dictionary"""
        message_data = data.get("params", {}).get("message", {})
        message = A2AMessage.from_dict(message_data)

        params = data.get("params", {}).copy()
        if "message" in params:
            del params["message"]

        return cls(
            method=data["method"],
            message=message,
            request_id=data.get("id"),
            params=params if params else None
        )


class A2AResponse:
    """
    JSON-RPC 2.0 Response for A2A communication
    """

    def __init__(
        self,
        request_id: str,
        result: Optional[Any] = None,
        error: Optional[Dict[str, Any]] = None
    ):
        self.jsonrpc = "2.0"
        self.request_id = request_id
        self.result = result
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-RPC 2.0 format"""
        response = {
            "jsonrpc": self.jsonrpc,
            "id": self.request_id
        }

        if self.error:
            response["error"] = self.error
        else:
            response["result"] = self.result

        return response

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'A2AResponse':
        """Create response from dictionary"""
        return cls(
            request_id=data["id"],
            result=data.get("result"),
            error=data.get("error")
        )

    @classmethod
    def success(cls, request_id: str, result: Any) -> 'A2AResponse':
        """Create success response"""
        return cls(request_id=request_id, result=result)

    @classmethod
    def error(cls, request_id: str, code: int, message: str, data: Optional[Any] = None) -> 'A2AResponse':
        """Create error response"""
        error = {
            "code": code,
            "message": message
        }
        if data:
            error["data"] = data
        return cls(request_id=request_id, error=error)


class A2AProtocol:
    """
    High-level A2A protocol helper

    Provides convenient methods for common A2A operations.
    """

    @staticmethod
    def create_task_message(
        text: str,
        context_id: str = "pipeline",
        metadata: Optional[Dict[str, Any]] = None
    ) -> A2ARequest:
        """
        Create a task/send message request

        Args:
            text: Message text content
            context_id: Context identifier
            metadata: Additional metadata

        Returns:
            A2ARequest ready to send
        """
        message = A2AMessage(
            context_id=context_id,
            role=MessageRole.USER,
            metadata=metadata or {}
        ).add_text_part(text)

        return A2ARequest(method="tasks/send", message=message)

    @staticmethod
    def create_code_generation_request(
        tools: List[Dict[str, Any]],
        context_id: str = "pipeline",
        iteration: int = 1,
        feedback: Optional[Union[str, Dict[str, Any]]] = None,
        previous_code: Optional[str] = None,
        fix_instructions: Optional[List[Dict[str, Any]]] = None,
        regeneration_hints: Optional[List[str]] = None
    ) -> A2ARequest:
        """
        Create code generation request for Generator Agent

        Args:
            tools: List of tool definitions
            context_id: Context identifier
            iteration: Current iteration number
            feedback: Feedback from previous validation (string or structured dict)

        Returns:
            A2ARequest for code generation
        """
        if iteration > 1 and feedback:
            # Regeneration with structured feedback
            if isinstance(feedback, dict):
                # Build detailed regeneration prompt from structured feedback
                feedback_text = f"**REGENERATION ITERATION {iteration}**\n\n"
                feedback_text += f"Previous Quality Score: {feedback.get('quality_score', 0)}/100 (Target: ≥90)\n"
                feedback_text += f"Status: {'APPROVED' if feedback.get('approved') else 'REJECTED - NEEDS IMPROVEMENT'}\n\n"
                
                errors = feedback.get('errors', [])
                if errors:
                    feedback_text += "**🔴 CRITICAL ERRORS (MUST FIX):**\n"
                    for i, error in enumerate(errors, 1):
                        line_info = f"Line {error.get('line', '?')}: " if error.get('line') else ""
                        code_snippet = f"\n   Code: {error.get('code_snippet', '')}" if error.get('code_snippet') else ""
                        suggestion = f"\n   Fix: {error.get('suggestion', '')}" if error.get('suggestion') else ""
                        feedback_text += f"{i}. {line_info}{error.get('description') or error.get('message', str(error))}{code_snippet}{suggestion}\n"
                    feedback_text += "\n"
                
                warnings = feedback.get('warnings', [])
                if warnings:
                    feedback_text += "**🟡 WARNINGS (SHOULD FIX):**\n"
                    for i, warning in enumerate(warnings, 1):
                        line_info = f"Line {warning.get('line', '?')}: " if warning.get('line') else ""
                        code_snippet = f"\n   Code: {warning.get('code_snippet', '')}" if warning.get('code_snippet') else ""
                        suggestion = f"\n   Fix: {warning.get('suggestion', '')}" if warning.get('suggestion') else ""
                        feedback_text += f"{i}. {line_info}{warning.get('description') or warning.get('message', str(warning))}{code_snippet}{suggestion}\n"
                    feedback_text += "\n"
                
                llm_validation = feedback.get('llm_validation', {})
                if llm_validation:
                    reasoning = llm_validation.get('reasoning', '')
                    improvements = llm_validation.get('improvements', [])
                    if reasoning:
                        feedback_text += f"**🤔 VALIDATOR ANALYSIS:**\n{reasoning}\n\n"
                    if improvements:
                        feedback_text += "**🚀 RECOMMENDED IMPROVEMENTS:**\n"
                        for i, improvement in enumerate(improvements, 1):
                            feedback_text += f"{i}. {improvement}\n"
                        feedback_text += "\n"
                
                prompt = f"Regenerate MCP server code addressing the following validation issues (Iteration {iteration}/5):\n\n"
                prompt += feedback_text
                prompt += "\n**REQUIREMENTS:**\n"
                prompt += "1. Fix ALL critical errors listed above\n"
                prompt += "2. Address warnings to improve quality score\n"
                prompt += "3. Consider implementing suggested improvements\n"
                prompt += "4. Generate complete, corrected code\n"
                prompt += "5. Target quality score: 90/100 or higher\n\n"
                
                # NEW: Include fix_instructions if provided
                if fix_instructions:
                    prompt += "**🔧 SPECIFIC FIX INSTRUCTIONS (MUST FOLLOW):**\n"
                    for i, fix in enumerate(fix_instructions, 1):
                        prompt += f"\n{i}. **{fix.get('error_code', 'ERROR')}** at line {fix.get('line', '?')}\n"
                        prompt += f"   - Issue: {fix.get('message', 'Unknown')}\n"
                        prompt += f"   - Fix: {fix.get('fix_instruction', 'No instruction')}\n"
                        if fix.get('suggested_code'):
                            prompt += f"   - Example: `{fix.get('suggested_code')}`\n"
                        if fix.get('context'):
                            prompt += f"   - Context: {fix.get('context')}\n"
                    prompt += "\n"
                
                # NEW: Include regeneration hints if provided
                if regeneration_hints:
                    prompt += "**💡 REGENERATION HINTS:**\n"
                    for hint in regeneration_hints:
                        prompt += f"- {hint}\n"
                    prompt += "\n"
                
                prompt += "**Tools to generate code for:**\n"
                prompt += json.dumps(tools, indent=2)
            else:
                # Legacy string feedback
                prompt = f"Regenerate MCP server code (Iteration {iteration}/5):\n\n"
                prompt += f"Previous validation feedback:\n{feedback}\n\n"
                prompt += "Please regenerate the code addressing ALL issues mentioned above.\n\n"
                prompt += "**Tools:**\n"
                prompt += json.dumps(tools, indent=2)
        else:
            # Initial generation
            prompt = f"Generate MCP server code from the following API tools (Iteration {iteration}/5):\n\n"
            prompt += json.dumps(tools, indent=2)

        metadata = {
            "task": "generate_code",
            "iteration": iteration,
            "tool_count": len(tools),
            "has_feedback": feedback is not None
        }

        message = A2AMessage(
            context_id=context_id,
            role=MessageRole.USER,
            metadata=metadata
        ).add_text_part(prompt).add_data_part({"tools": tools})

        # Add structured feedback as data if available
        if feedback and isinstance(feedback, dict):
            message.add_data_part({"validation_feedback": feedback})
        
        # Add previous code if available (for iterative refactoring)
        if previous_code:
            message.add_code_part(previous_code, "python")
            metadata["has_previous_code"] = True

        return A2ARequest(method="tasks/send", message=message)

    @staticmethod
    def create_validation_request(
        code: str,
        context_id: str = "pipeline",
        iteration: int = 1,
        previous_code: Optional[str] = None,
        best_code: Optional[str] = None,
        best_score: int = 0
    ) -> A2ARequest:
        """
        Create validation request for Validator Agent

        Args:
            code: Generated MCP code to validate
            context_id: Context identifier
            iteration: Current iteration number

        Returns:
            A2ARequest for validation
        """
        prompt = f"Validate the following MCP server code (Iteration {iteration}/3):\n\n"
        prompt += f"```python\n{code}\n```"

        metadata = {
            "task": "validate_code",
            "iteration": iteration,
            "code_length": len(code)
        }

        message = A2AMessage(
            context_id=context_id,
            role=MessageRole.USER,
            metadata=metadata
        ).add_code_part(code, "python")
        
        # Add previous code for regression testing
        if previous_code:
            message.add_data_part({"previous_code": previous_code})
            metadata["has_previous_code"] = True
        
        # Add best code for regression testing
        if best_code:
            message.add_data_part({"best_code": best_code, "best_score": best_score})
            metadata["has_best_code"] = True

        return A2ARequest(method="tasks/send", message=message)

    @staticmethod
    def parse_validation_response(response: A2AResponse) -> Dict[str, Any]:
        """
        Parse validation response into structured format

        Args:
            response: A2A response from validator

        Returns:
            Validation result dictionary
        """
        if response.error:
            return {
                "approved": False,
                "error": response.error["message"],
                "quality_score": 0
            }

        result = response.result
        if isinstance(result, dict):
            return result

        # Try to extract from message parts
        if isinstance(result, dict) and "message" in result:
            msg = result["message"]
            if "parts" in msg:
                for part in msg["parts"]:
                    if part.get("kind") == "data" and "data" in part:
                        return part["data"]

        return {"approved": False, "error": "Could not parse validation response"}

    @staticmethod
    def parse_generated_code(response: A2AResponse) -> Optional[str]:
        """
        Extract generated code from response

        Args:
            response: A2A response from generator

        Returns:
            Generated code string or None
        """
        if response.error:
            logger.error(f"Code generation error: {response.error}")
            return None

        result = response.result

        # Check if result has code directly
        if isinstance(result, str):
            return result

        # Check if result is dict with code field
        if isinstance(result, dict):
            if "code" in result:
                return result["code"]

            # Check message parts for code
            if "message" in result and "parts" in result["message"]:
                for part in result["message"]["parts"]:
                    if part.get("kind") == "code":
                        return part.get("code")
                    elif part.get("kind") == "text":
                        text = part.get("text", "")
                        # Try to extract code from markdown code blocks
                        if "```python" in text:
                            start = text.find("```python") + 9
                            end = text.find("```", start)
                            if end > start:
                                return text[start:end].strip()

        logger.warning("Could not extract code from response")
        return None


# Convenience functions
def create_message(text: str, role: MessageRole = MessageRole.USER) -> A2AMessage:
    """Quick message creation"""
    return A2AMessage(role=role).add_text_part(text)


def create_request(method: str, text: str) -> A2ARequest:
    """Quick request creation"""
    message = create_message(text)
    return A2ARequest(method=method, message=message)


def create_success_response(request_id: str, data: Any) -> A2AResponse:
    """Quick success response"""
    return A2AResponse.success(request_id, data)


def create_error_response(request_id: str, message: str) -> A2AResponse:
    """Quick error response"""
    return A2AResponse.error(request_id, -32000, message)
