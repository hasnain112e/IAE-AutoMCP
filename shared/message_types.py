"""
Message Type Schemas for the Agentic Pipeline

Defines Pydantic models for all message types exchanged between agents.
"""
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class PipelineState(str, Enum):
    """Pipeline state machine states"""
    INITIAL = "initial"
    INPUT_RECEIVED = "input_received"
    COLLECTING_TOOLS = "collecting_tools"
    TOOLS_READY = "tools_ready"
    GENERATING_CODE = "generating_code"
    AWAITING_VALIDATION = "awaiting_validation"
    VALIDATING_CODE = "validating_code"
    VALIDATION_RESULT = "validation_result"
    AWAITING_REGEN = "awaiting_regen"
    REGENERATING_CODE = "regenerating_code"
    DONE = "done"
    FAILED_FINAL = "failed_final"


class SourceType(str, Enum):
    """Input source types"""
    FILE = "file"
    URL = "url"
    SDK = "sdk"
    DEFAULT = "default"


class AgentType(str, Enum):
    """Agent types in the system"""
    ORCHESTRATOR = "orchestrator"
    GENERATOR = "generator"
    VALIDATOR = "validator"
    UI_CONTROLLER = "ui_controller"
    TIMER = "timer"


class TaskType(str, Enum):
    """Task types for agents"""
    COLLECT_TOOLS = "collect_tools"
    GENERATE_CODE = "generate_code"
    VALIDATE_CODE = "validate_code"
    REGENERATE_CODE = "regenerate_code"
    UPDATE_UI = "update_ui"


# ============================================================================
# Tool-related messages
# ============================================================================

class ToolParameter(BaseModel):
    """API tool parameter definition"""
    name: str
    type: str
    required: bool = False
    description: Optional[str] = None
    default: Optional[str] = None


class Tool(BaseModel):
    """API tool definition"""
    name: str
    description: str
    method: Optional[str] = None
    path: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parameters: List[ToolParameter] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolsCollectionRequest(BaseModel):
    """Request to collect tools from a source"""
    source_type: SourceType
    source_data: Optional[str] = None  # URL, SDK name, or file content
    output_format: str = "json"
    context_id: str = "default"


class ToolsCollectionResponse(BaseModel):
    """Response from tool collection"""
    success: bool
    tools: List[Tool]
    source_type: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Code generation messages
# ============================================================================

class CodeGenerationRequest(BaseModel):
    """Request to generate MCP code"""
    tools: List[Tool]
    iteration: int = 1
    feedback: Optional[str] = None
    context_id: str = "pipeline"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CodeGenerationResponse(BaseModel):
    """Response from code generation"""
    success: bool
    code: Optional[str] = None
    iteration: int
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Validation messages
# ============================================================================

class ValidationRequest(BaseModel):
    """Request to validate MCP code"""
    code: str
    iteration: int = 1
    context_id: str = "pipeline"
    use_llm: bool = True


class ValidationIssue(BaseModel):
    """A validation issue found in code"""
    severity: str  # "error", "warning", "info", "suggestion"
    message: str
    line: Optional[int] = None
    code: Optional[str] = None  # Error code identifier
    category: Optional[str] = None  # "security", "error_handling", "code_quality", etc.
    code_snippet: Optional[str] = None  # Actual code snippet showing the issue
    suggestion: Optional[str] = None  # How to fix the issue
    points_deducted: Optional[int] = None  # Points deducted for this issue
    description: Optional[str] = None  # Detailed description (alias for message)


class FixInstruction(BaseModel):
    """
    Actionable fix instruction for the Generator Agent.
    
    PHILOSOPHY: No code is worthless - provide detailed instructions
    to enable the Generator to learn and improve.
    """
    error_code: str  # e.g., "F821", "E999"
    message: str  # Human-readable error message
    line: int = 0  # Line number where error occurred
    column: int = 0  # Column number where error occurred
    fix_instruction: str  # Detailed instruction on how to fix
    suggested_code: Optional[str] = None  # Example code showing the fix
    context: Optional[str] = None  # Code context around the error
    priority: str = "high"  # "critical", "high", "medium", "low"


class LLMValidationResult(BaseModel):
    """LLM validation details"""
    reasoning: Optional[str] = None
    risk_assessment: Optional[str] = None
    improvements: List[str] = Field(default_factory=list)
    quality_breakdown: Dict[str, int] = Field(default_factory=dict)


class ValidationResponse(BaseModel):
    """Response from code validation"""
    approved: bool
    quality_score: int = 0
    iteration: int = 1
    errors: List[ValidationIssue] = Field(default_factory=list)
    warnings: List[ValidationIssue] = Field(default_factory=list)
    suggestions: List[ValidationIssue] = Field(default_factory=list)  # Added by Dr. Wasim
    fix_instructions: List[FixInstruction] = Field(default_factory=list)  # NEW: Actionable instructions
    regeneration_hints: List[str] = Field(default_factory=list)  # NEW: High-level hints
    llm_validation: Optional[LLMValidationResult] = None
    feedback: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Pipeline orchestration messages
# ============================================================================

class PipelineConfig(BaseModel):
    """Pipeline configuration"""
    max_iterations: int = 10  # Increased to give more chances for improvement
    validation_timeout: int = 10  # seconds
    regeneration_timeout: int = 10  # seconds
    auto_validate: bool = True
    auto_regenerate: bool = True


class PipelineContext(BaseModel):
    """Pipeline execution context with Golden Code tracking"""
    context_id: str = Field(default_factory=lambda: f"ctx-{datetime.utcnow().timestamp()}")
    state: PipelineState = PipelineState.INITIAL
    iteration: int = 0
    config: PipelineConfig = Field(default_factory=PipelineConfig)
    tools: List[Tool] = Field(default_factory=list)
    generated_code: Optional[str] = None
    validation_result: Optional[ValidationResponse] = None
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Golden Code tracking for degenerative behavior prevention
    best_code: Optional[str] = None  # Best performing code version
    best_score: int = 0  # Best score achieved so far
    best_iteration: int = 0  # Iteration where best code was generated
    code_history: List[Dict[str, Any]] = Field(default_factory=list)  # Track all code versions and scores

    def update_state(self, new_state: PipelineState) -> None:
        """Update pipeline state"""
        self.state = new_state
        self.updated_at = datetime.utcnow()


class PipelineEvent(BaseModel):
    """Pipeline state change event"""
    event_id: str = Field(default_factory=lambda: f"evt-{datetime.utcnow().timestamp()}")
    context_id: str
    event_type: str  # "state_change", "timer_start", "timer_cancel", "error", etc.
    from_state: Optional[PipelineState] = None
    to_state: Optional[PipelineState] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TimerEvent(BaseModel):
    """Timer event for auto-actions"""
    timer_id: str
    context_id: str
    action: str  # "validate", "regenerate"
    duration: int  # seconds
    started_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    cancelled: bool = False


# ============================================================================
# UI update messages
# ============================================================================

class UIUpdateType(str, Enum):
    """UI update message types"""
    STATE_CHANGE = "state_change"
    TIMER_START = "timer_start"
    TIMER_TICK = "timer_tick"
    TIMER_CANCEL = "timer_cancel"
    TOOLS_UPDATED = "tools_updated"
    CODE_GENERATED = "code_generated"
    VALIDATION_RESULT = "validation_result"
    AGENT_THINKING = "agent_thinking"  # Real-time thinking logs from agents
    SCORE_CHANGE = "score_change"  # Score change notifications
    ERROR = "error"
    INFO = "info"
    UI_UPDATE = "ui_update"  # Generic UI update (includes A2A messages)


class UIUpdate(BaseModel):
    """UI update message"""
    update_type: UIUpdateType
    context_id: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Agent communication messages
# ============================================================================

class AgentMessage(BaseModel):
    """Generic agent message"""
    message_id: str = Field(default_factory=lambda: f"msg-{datetime.utcnow().timestamp()}")
    from_agent: AgentType
    to_agent: AgentType
    task_type: TaskType
    context_id: str
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    requires_response: bool = True


class AgentResponse(BaseModel):
    """Generic agent response"""
    response_id: str = Field(default_factory=lambda: f"rsp-{datetime.utcnow().timestamp()}")
    in_response_to: str  # message_id
    from_agent: AgentType
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Human-in-the-loop messages
# ============================================================================

class HITLDecision(str, Enum):
    """Human-in-the-loop decision types"""
    AUTO = "auto"  # Let timer expire
    MANUAL = "manual"  # User clicked button
    CANCEL = "cancel"  # User cancelled action


class HITLEvent(BaseModel):
    """Human-in-the-loop event"""
    event_id: str = Field(default_factory=lambda: f"hitl-{datetime.utcnow().timestamp()}")
    context_id: str
    action: str  # "validate", "regenerate"
    decision: HITLDecision
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Utility functions
# ============================================================================

def create_tool_from_dict(data: Dict[str, Any]) -> Tool:
    """Create Tool from dictionary"""
    params = [ToolParameter(**p) for p in data.get("parameters", [])]
    return Tool(
        name=data["name"],
        description=data["description"],
        method=data.get("method"),
        path=data.get("path"),
        tags=data.get("tags", []),
        parameters=params,
        metadata=data.get("metadata", {})
    )


def create_pipeline_context(context_id: Optional[str] = None) -> PipelineContext:
    """Create new pipeline context"""
    return PipelineContext(
        context_id=context_id or f"ctx-{datetime.utcnow().timestamp()}"
    )


def create_ui_update(
    update_type: UIUpdateType,
    context_id: str,
    data: Optional[Dict[str, Any]] = None
) -> UIUpdate:
    """Create UI update message"""
    return UIUpdate(
        update_type=update_type,
        context_id=context_id,
        data=data or {}
    )
