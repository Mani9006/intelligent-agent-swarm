"""Base agent class and shared abstractions for the swarm system."""

from __future__ import annotations

import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Protocol

import structlog

from src.tasks.task import Task, TaskResult, TaskStatus

logger = structlog.get_logger(__name__)


class AgentState(Enum):
    """Runtime state of an agent."""

    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass
class AgentCapability:
    """Represents a skill that an agent possesses."""

    name: str
    proficiency: float = 1.0  # 0.0 to 1.0
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.proficiency <= 1.0:
            raise ValueError("Proficiency must be between 0.0 and 1.0")

    def match_score(self, requirement: str) -> float:
        """Calculate how well this capability matches a requirement.

        Args:
            requirement: The capability name being sought.

        Returns:
            Match score between 0.0 and 1.0.
        """
        if self.name.lower() == requirement.lower():
            return self.proficiency
        if requirement.lower() in self.description.lower():
            return self.proficiency * 0.5
        return 0.0


class MessageHandler(Protocol):
    """Protocol for objects that can handle agent messages."""

    def __call__(self, sender_id: str, message: Dict[str, Any]) -> None:
        ...


class BaseAgent(ABC):
    """Abstract base class for all swarm agents.

    Provides common functionality for lifecycle management, capability
    registration, task execution, and inter-agent communication.
    """

    def __init__(
        self,
        name: str,
        agent_type: str,
        capabilities: Optional[List[AgentCapability]] = None,
        max_concurrent_tasks: int = 1,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.id = f"{agent_type}_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.agent_type = agent_type
        self._capabilities: Dict[str, AgentCapability] = {}
        self.max_concurrent_tasks = max_concurrent_tasks
        self.config = config or {}
        self._state = AgentState.IDLE
        self._current_tasks: Dict[str, Task] = {}
        self._completed_tasks: List[str] = []
        self._failed_tasks: List[str] = []
        self._total_tasks_processed = 0
        self._lock = threading.RLock()
        self._message_handlers: List[MessageHandler] = []
        self._created_at = datetime.utcnow()
        self._last_active = datetime.utcnow()
        self._cpu_load = 0.0  # Simulated load 0.0-1.0
        self._memory_usage = 0.0  # Simulated usage 0.0-1.0

        self._log = logger.bind(agent_id=self.id, agent_type=agent_type)

        if capabilities:
            for cap in capabilities:
                self.register_capability(cap)

        self._log.info("agent_created", name=name)

    @property
    def state(self) -> AgentState:
        """Current runtime state."""
        with self._lock:
            return self._state

    @state.setter
    def state(self, value: AgentState) -> None:
        with self._lock:
            old = self._state
            self._state = value
            self._log.info("agent_state_changed", old=old.value, new=value.value)

    @property
    def is_available(self) -> bool:
        """Check if the agent can accept new work."""
        with self._lock:
            return (
                self._state == AgentState.IDLE
                and len(self._current_tasks) < self.max_concurrent_tasks
            )

    @property
    def load_factor(self) -> float:
        """Current load as a fraction of capacity (0.0-1.0)."""
        with self._lock:
            if self.max_concurrent_tasks == 0:
                return 1.0
            return len(self._current_tasks) / self.max_concurrent_tasks

    @property
    def capability_names(self) -> List[str]:
        """List of registered capability names."""
        with self._lock:
            return list(self._capabilities.keys())

    def register_capability(self, capability: AgentCapability) -> None:
        """Add a capability to this agent.

        Args:
            capability: The capability to register.
        """
        with self._lock:
            self._capabilities[capability.name] = capability
            self._log.debug("capability_registered", name=capability.name)

    def unregister_capability(self, name: str) -> bool:
        """Remove a capability from this agent.

        Args:
            name: The capability name to remove.

        Returns:
            True if the capability was removed.
        """
        with self._lock:
            if name in self._capabilities:
                del self._capabilities[name]
                return True
            return False

    def get_capability(self, name: str) -> Optional[AgentCapability]:
        """Retrieve a capability by name.

        Args:
            name: The capability name.

        Returns:
            The capability if found, else None.
        """
        with self._lock:
            return self._capabilities.get(name)

    def capability_score(self, requirement: str) -> float:
        """Calculate the best match score for a capability requirement.

        Args:
            requirement: The required capability name.

        Returns:
            Best match score (0.0-1.0).
        """
        with self._lock:
            if not self._capabilities:
                return 0.0
            return max(
                cap.match_score(requirement)
                for cap in self._capabilities.values()
            )

    def composite_score(self, requirements: List[str]) -> float:
        """Calculate an aggregate score across multiple requirements.

        Uses a weighted average that rewards breadth of capability matches.

        Args:
            requirements: List of required capability names.

        Returns:
            Aggregate score between 0.0 and 1.0.
        """
        if not requirements:
            return 0.0

        scores = [self.capability_score(req) for req in requirements]
        if not scores:
            return 0.0

        avg_score = sum(scores) / len(scores)
        coverage = sum(1 for s in scores if s > 0) / len(scores)

        # Weighted combination: 60% average score, 40% coverage
        return avg_score * 0.6 + coverage * 0.4

    def can_handle(self, task: Task) -> bool:
        """Check if this agent can handle a given task.

        Args:
            task: The task to evaluate.

        Returns:
            True if all required capabilities are present.
        """
        if not task.required_capabilities:
            return self.is_available

        scores = [
            self.capability_score(req)
            for req in task.required_capabilities
        ]
        return all(s > 0 for s in scores) and self.is_available

    def accept_task(self, task: Task) -> bool:
        """Attempt to accept a task for execution.

        Args:
            task: The task to accept.

        Returns:
            True if the task was accepted.
        """
        with self._lock:
            if not self.is_available:
                return False
            if not self.can_handle(task):
                return False

            self._current_tasks[task.id] = task
            task.assigned_agent_id = self.id
            task.mark_started()
            self.state = AgentState.BUSY
            self._last_active = datetime.utcnow()
            self._cpu_load = min(1.0, self.load_factor + 0.2)
            self._log.info(
                "task_accepted",
                task_id=task.id,
                current_load=len(self._current_tasks),
            )
            return True

    def execute_task(self, task: Task) -> TaskResult:
        """Execute a task and return the result.

        This method handles the execution lifecycle and delegates the
        actual work to _perform_task.

        Args:
            task: The task to execute.

        Returns:
            The task result.
        """
        start_time = time.monotonic()
        self._log.info("task_execution_started", task_id=task.id)

        try:
            result = self._perform_task(task)
        except Exception as exc:
            duration = time.monotonic() - start_time
            result = TaskResult(
                task_id=task.id,
                agent_id=self.id,
                success=False,
                output=f"",
                metadata={"error": str(exc), "error_type": type(exc).__name__},
                duration_seconds=duration,
            )
            self._log.error(
                "task_execution_error",
                task_id=task.id,
                error=str(exc),
            )

        duration = time.monotonic() - start_time
        result.duration_seconds = duration
        result.agent_id = self.id

        self._finalize_task(task, result)
        return result

    @abstractmethod
    def _perform_task(self, task: Task) -> TaskResult:
        """Override this to implement agent-specific task logic.

        Args:
            task: The task to execute.

        Returns:
            The task result.
        """
        ...

    def _finalize_task(self, task: Task, result: TaskResult) -> None:
        """Clean up after task execution.

        Args:
            task: The completed task.
            result: The execution result.
        """
        with self._lock:
            if task.id in self._current_tasks:
                del self._current_tasks[task.id]

            if result.success:
                self._completed_tasks.append(task.id)
            else:
                self._failed_tasks.append(task.id)

            self._total_tasks_processed += 1
            self._last_active = datetime.utcnow()

            if not self._current_tasks:
                self.state = AgentState.IDLE
                self._cpu_load = 0.0

            task.mark_completed(result)
            self._log.info(
                "task_finalized",
                task_id=task.id,
                success=result.success,
                duration=result.duration_seconds,
            )

    def send_message(self, recipient_id: str, content: Dict[str, Any]) -> None:
        """Send a message to another agent via the message bus.

        Args:
            recipient_id: Target agent ID.
            content: Message payload.
        """
        message = {
            "sender_id": self.id,
            "recipient_id": recipient_id,
            "timestamp": datetime.utcnow().isoformat(),
            "content": content,
        }
        self._log.debug("message_sent", to=recipient_id, msg_type=content.get("type"))
        for handler in self._message_handlers:
            handler(self.id, message)

    def register_message_handler(self, handler: MessageHandler) -> None:
        """Register a callback for incoming messages.

        Args:
            handler: Callable that accepts (sender_id, message).
        """
        with self._lock:
            if handler not in self._message_handlers:
                self._message_handlers.append(handler)

    def unregister_message_handler(self, handler: MessageHandler) -> None:
        """Remove a message handler.

        Args:
            handler: The handler to remove.
        """
        with self._lock:
            if handler in self._message_handlers:
                self._message_handlers.remove(handler)

    def receive_message(self, sender_id: str, message: Dict[str, Any]) -> None:
        """Handle an incoming message from another agent.

        Override for custom message handling logic.

        Args:
            sender_id: The sending agent's ID.
            message: The message payload.
        """
        self._log.debug(
            "message_received",
            from_agent=sender_id,
            msg_type=message.get("content", {}).get("type"),
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Return agent performance metrics.

        Returns:
            Dictionary of metric values.
        """
        with self._lock:
            uptime = (datetime.utcnow() - self._created_at).total_seconds()
            active_time = (
                (datetime.utcnow() - self._last_active).total_seconds()
                if self._last_active
                else 0
            )
            return {
                "agent_id": self.id,
                "agent_type": self.agent_type,
                "name": self.name,
                "state": self.state.value,
                "total_tasks": self._total_tasks_processed,
                "completed": len(self._completed_tasks),
                "failed": len(self._failed_tasks),
                "success_rate": (
                    len(self._completed_tasks) / max(self._total_tasks_processed, 1)
                ),
                "current_load": len(self._current_tasks),
                "max_load": self.max_concurrent_tasks,
                "load_factor": self.load_factor,
                "capabilities": self.capability_names,
                "uptime_seconds": uptime,
                "idle_seconds": active_time,
                "cpu_load": self._cpu_load,
            }

    def pause(self) -> None:
        """Pause the agent, preventing new task acceptance."""
        self.state = AgentState.PAUSED

    def resume(self) -> None:
        """Resume a paused agent."""
        if self._state == AgentState.PAUSED:
            self.state = (
                AgentState.IDLE if not self._current_tasks else AgentState.BUSY
            )

    def shutdown(self) -> None:
        """Gracefully shut down the agent."""
        self._log.info("agent_shutting_down")
        with self._lock:
            self._state = AgentState.OFFLINE
            self._current_tasks.clear()
            self._message_handlers.clear()

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}(id={self.id}, "
            f"type={self.agent_type}, state={self.state.value})>"
        )
