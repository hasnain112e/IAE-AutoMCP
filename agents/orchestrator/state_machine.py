"""
Pipeline State Machine

Implements deterministic state transitions and retry logic for the MCP generation pipeline.
"""
import asyncio
import logging
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum

from shared.message_types import (
    PipelineState,
    PipelineContext,
    PipelineConfig,
    PipelineEvent,
    TimerEvent,
    HITLDecision,
    HITLEvent,
    Tool,
    ValidationResponse,
    UIUpdateType,
    UIUpdate
)

logger = logging.getLogger(__name__)


class StateTransition:
    """Represents a state transition"""

    def __init__(
        self,
        from_state: PipelineState,
        to_state: PipelineState,
        condition: Optional[Callable[[PipelineContext], bool]] = None,
        action: Optional[Callable[[PipelineContext], Any]] = None
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition or (lambda ctx: True)
        self.action = action

    def can_transition(self, context: PipelineContext) -> bool:
        """Check if transition is allowed"""
        return context.state == self.from_state and self.condition(context)

    async def execute(self, context: PipelineContext) -> None:
        """Execute transition action"""
        if self.action:
            result = self.action(context)
            if asyncio.iscoroutine(result):
                await result


class Timer:
    """Countdown timer for auto-actions"""

    def __init__(
        self,
        timer_id: str,
        context_id: str,
        action: str,
        duration: int,
        callback: Callable[[], Any]
    ):
        self.timer_id = timer_id
        self.context_id = context_id
        self.action = action
        self.duration = duration
        self.callback = callback
        self.started_at = datetime.utcnow()
        self.expires_at = self.started_at + timedelta(seconds=duration)
        self.cancelled = False
        self.completed = False
        self.task: Optional[asyncio.Task] = None

    @property
    def remaining_seconds(self) -> int:
        """Get remaining seconds"""
        if self.cancelled or self.completed:
            return 0
        remaining = (self.expires_at - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))

    async def start(self) -> None:
        """Start timer countdown"""
        try:
            logger.info(f"Timer {self.timer_id} started: {self.action} in {self.duration}s")

            # Countdown loop
            for remaining in range(self.duration, 0, -1):
                if self.cancelled:
                    logger.info(f"Timer {self.timer_id} cancelled at {remaining}s")
                    return

                await asyncio.sleep(1)

            # Timer expired - execute callback
            if not self.cancelled:
                logger.info(f"Timer {self.timer_id} expired, executing {self.action}")
                self.completed = True
                result = self.callback()
                if asyncio.iscoroutine(result):
                    await result

        except asyncio.CancelledError:
            logger.info(f"Timer {self.timer_id} task cancelled")
            self.cancelled = True
        except Exception as e:
            logger.error(f"Timer {self.timer_id} error: {e}")
            self.cancelled = True

    def cancel(self) -> None:
        """Cancel timer"""
        self.cancelled = True
        if self.task and not self.task.done():
            self.task.cancel()
            logger.info(f"Timer {self.timer_id} cancelled")


class PipelineStateMachine:
    """
    Manages pipeline state transitions and retry logic

    Features:
    - Deterministic state transitions
    - Auto-validation after code generation (10s timer)
    - Auto-regeneration after rejection (10s timer)
    - Max 3 regeneration attempts
    - Human override capability
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.contexts: Dict[str, PipelineContext] = {}
        self.timers: Dict[str, Timer] = {}
        self.transitions: List[StateTransition] = self._define_transitions()
        self.event_callbacks: Dict[str, List[Callable]] = {}
        self.logger = logging.getLogger("state_machine")

    def _define_transitions(self) -> List[StateTransition]:
        """Define all valid state transitions"""
        return [
            # Initial -> Input Received
            StateTransition(
                PipelineState.INITIAL,
                PipelineState.INPUT_RECEIVED
            ),
            # Input Received -> Collecting Tools
            StateTransition(
                PipelineState.INPUT_RECEIVED,
                PipelineState.COLLECTING_TOOLS
            ),
            # Collecting Tools -> Tools Ready
            StateTransition(
                PipelineState.COLLECTING_TOOLS,
                PipelineState.TOOLS_READY
            ),
            # Tools Ready -> Generating Code
            StateTransition(
                PipelineState.TOOLS_READY,
                PipelineState.GENERATING_CODE
            ),
            # Generating Code -> Awaiting Validation
            StateTransition(
                PipelineState.GENERATING_CODE,
                PipelineState.AWAITING_VALIDATION
            ),
            # Awaiting Validation -> Validating Code
            StateTransition(
                PipelineState.AWAITING_VALIDATION,
                PipelineState.VALIDATING_CODE
            ),
            # Validating Code -> Validation Result
            StateTransition(
                PipelineState.VALIDATING_CODE,
                PipelineState.VALIDATION_RESULT
            ),
            # Validation Result -> Done (if approved)
            StateTransition(
                PipelineState.VALIDATION_RESULT,
                PipelineState.DONE,
                condition=lambda ctx: ctx.validation_result and ctx.validation_result.approved
            ),
            # Validation Result -> Awaiting Regen (if rejected and iterations < max)
            StateTransition(
                PipelineState.VALIDATION_RESULT,
                PipelineState.AWAITING_REGEN,
                condition=lambda ctx: (
                    ctx.validation_result and
                    not ctx.validation_result.approved and
                    ctx.iteration < ctx.config.max_iterations
                )
            ),
            # Validation Result -> Failed Final (if rejected and max iterations reached)
            StateTransition(
                PipelineState.VALIDATION_RESULT,
                PipelineState.FAILED_FINAL,
                condition=lambda ctx: (
                    ctx.validation_result and
                    not ctx.validation_result.approved and
                    ctx.iteration >= ctx.config.max_iterations
                )
            ),
            # Awaiting Regen -> Regenerating Code
            StateTransition(
                PipelineState.AWAITING_REGEN,
                PipelineState.REGENERATING_CODE
            ),
            # Regenerating Code -> Generating Code (actual regeneration)
            StateTransition(
                PipelineState.REGENERATING_CODE,
                PipelineState.GENERATING_CODE
            ),
            # Regenerating Code -> Awaiting Validation (loop back after generation)
            StateTransition(
                PipelineState.REGENERATING_CODE,
                PipelineState.AWAITING_VALIDATION
            ),
            # Generating Code -> Failed Final (if AI fails completely)
            StateTransition(
                PipelineState.GENERATING_CODE,
                PipelineState.FAILED_FINAL
            ),
        ]

    def create_context(self, context_id: Optional[str] = None) -> PipelineContext:
        """Create new pipeline context"""
        context = PipelineContext(
            context_id=context_id or f"ctx-{datetime.utcnow().timestamp()}",
            config=self.config
        )
        self.contexts[context.context_id] = context
        self.logger.info(f"Created pipeline context: {context.context_id}")
        return context

    def get_context(self, context_id: str) -> Optional[PipelineContext]:
        """Get pipeline context by ID"""
        return self.contexts.get(context_id)

    async def transition(
        self,
        context_id: str,
        to_state: PipelineState,
        emit_event: bool = True
    ) -> bool:
        """
        Transition to new state

        Args:
            context_id: Pipeline context ID
            to_state: Target state
            emit_event: Whether to emit state change event

        Returns:
            True if transition successful
        """
        context = self.get_context(context_id)
        if not context:
            self.logger.error(f"Context not found: {context_id}")
            return False

        # Find valid transition
        transition = None
        for t in self.transitions:
            if t.can_transition(context) and t.to_state == to_state:
                transition = t
                break

        if not transition:
            self.logger.warning(
                f"No valid transition from {context.state} to {to_state}"
            )
            return False

        # Execute transition
        old_state = context.state
        context.update_state(to_state)

        self.logger.info(
            f"Context {context_id}: {old_state} -> {to_state}"
        )

        # Execute transition action
        await transition.execute(context)

        # Emit event
        if emit_event:
            await self._emit_event(
                context_id,
                "state_change",
                {"from_state": old_state.value, "to_state": to_state.value}
            )

        return True

    async def start_validation_timer(
        self,
        context_id: str,
        callback: Callable[[], Any]
    ) -> str:
        """
        Start auto-validation timer

        Args:
            context_id: Pipeline context ID
            callback: Function to call when timer expires

        Returns:
            Timer ID
        """
        context = self.get_context(context_id)
        if not context or not context.config.auto_validate:
            return ""

        timer_id = f"timer-validate-{context_id}"

        # Cancel existing timer if any
        await self._cancel_timer(timer_id)

        # Create new timer
        timer = Timer(
            timer_id=timer_id,
            context_id=context_id,
            action="validate",
            duration=context.config.validation_timeout,
            callback=callback
        )

        self.timers[timer_id] = timer

        # Start timer task
        timer.task = asyncio.create_task(timer.start())

        await self._emit_event(
            context_id,
            "timer_start",
            {
                "timer_id": timer_id,
                "action": "validate",
                "duration": context.config.validation_timeout
            }
        )

        return timer_id

    async def start_regeneration_timer(
        self,
        context_id: str,
        callback: Callable[[], Any]
    ) -> str:
        """
        Start auto-regeneration timer

        Args:
            context_id: Pipeline context ID
            callback: Function to call when timer expires

        Returns:
            Timer ID
        """
        context = self.get_context(context_id)
        if not context or not context.config.auto_regenerate:
            return ""

        timer_id = f"timer-regen-{context_id}"

        # Cancel existing timer if any
        await self._cancel_timer(timer_id)

        # Create new timer
        timer = Timer(
            timer_id=timer_id,
            context_id=context_id,
            action="regenerate",
            duration=context.config.regeneration_timeout,
            callback=callback
        )

        self.timers[timer_id] = timer

        # Start timer task
        timer.task = asyncio.create_task(timer.start())

        await self._emit_event(
            context_id,
            "timer_start",
            {
                "timer_id": timer_id,
                "action": "regenerate",
                "duration": context.config.regeneration_timeout
            }
        )

        return timer_id

    async def cancel_timer(self, context_id: str, action: str) -> None:
        """
        Cancel timer for specific action

        Args:
            context_id: Pipeline context ID
            action: Action type ("validate" or "regenerate")
        """
        timer_id = f"timer-{action}-{context_id}"
        await self._cancel_timer(timer_id)

    async def _cancel_timer(self, timer_id: str) -> None:
        """Internal timer cancellation"""
        if timer_id in self.timers:
            timer = self.timers[timer_id]
            timer.cancel()
            await self._emit_event(
                timer.context_id,
                "timer_cancel",
                {"timer_id": timer_id, "action": timer.action}
            )
            del self.timers[timer_id]

    def get_timer(self, context_id: str, action: str) -> Optional[Timer]:
        """Get active timer"""
        timer_id = f"timer-{action}-{context_id}"
        return self.timers.get(timer_id)

    def on_event(self, event_type: str, callback: Callable) -> None:
        """Register event callback"""
        if event_type not in self.event_callbacks:
            self.event_callbacks[event_type] = []
        self.event_callbacks[event_type].append(callback)

    async def _emit_event(self, context_id: str, event_type: str, data: Dict[str, Any]) -> None:
        """Emit event to callbacks"""
        if event_type in self.event_callbacks:
            for callback in self.event_callbacks[event_type]:
                try:
                    result = callback(context_id, data)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    self.logger.error(f"Event callback error: {e}")

    async def handle_hitl_decision(
        self,
        context_id: str,
        action: str,
        decision: HITLDecision
    ) -> None:
        """
        Handle human-in-the-loop decision

        Args:
            context_id: Pipeline context ID
            action: Action type
            decision: User decision
        """
        self.logger.info(
            f"HITL decision for {context_id}: {action} = {decision}"
        )

        if decision == HITLDecision.MANUAL:
            # User clicked button - cancel timer
            await self.cancel_timer(context_id, action)

        await self._emit_event(
            context_id,
            "hitl_decision",
            {"action": action, "decision": decision.value}
        )

    def can_regenerate(self, context_id: str) -> bool:
        """Check if regeneration is allowed"""
        context = self.get_context(context_id)
        if not context:
            return False
        return context.iteration < context.config.max_iterations

    def increment_iteration(self, context_id: str) -> int:
        """Increment iteration counter"""
        context = self.get_context(context_id)
        if not context:
            return 0
        context.iteration += 1
        self.logger.info(
            f"Context {context_id}: iteration {context.iteration}/{context.config.max_iterations}"
        )
        return context.iteration

    async def reset_context(self, context_id: str) -> None:
        """Reset pipeline context for new run"""
        context = self.get_context(context_id)
        if context:
            # Cancel all timers
            for timer_id in list(self.timers.keys()):
                if context_id in timer_id:
                    await self._cancel_timer(timer_id)

            # Reset context
            context.state = PipelineState.INITIAL
            context.iteration = 0
            context.tools = []
            context.generated_code = None
            context.validation_result = None
            context.error = None
            context.updated_at = datetime.utcnow()

            self.logger.info(f"Reset context: {context_id}")
