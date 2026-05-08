"""Core task definitions for the agent swarm system."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Self
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)


class TaskStatus(Enum):
    """Lifecycle states of a task within the swarm."""

    PENDING = "pending"
    DECOMPOSING = "decomposing"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    AWAITING_CONSENSUS = "awaiting_consensus"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Priority levels for task scheduling."""

    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    BACKGROUND = 5


@dataclass
class TaskResult:
    """Result produced by an agent after executing a task."""

    task_id: str
    agent_id: Optional[str]
    success: bool
    output: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_seconds: float = 0.0
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "success": self.success,
            "output": self.output,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Self:
        """Deserialize result from dictionary."""
        return cls(
            task_id=data["task_id"],
            agent_id=data.get("agent_id"),
            success=data["success"],
            output=data.get("output", ""),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            duration_seconds=data.get("duration_seconds", 0.0),
            retry_count=data.get("retry_count", 0),
        )


@dataclass
class Task:
    """Represents a unit of work within the agent swarm."""

    description: str
    task_type: str
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    required_capabilities: List[str] = field(default_factory=list)
    assigned_agent_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    subtask_ids: List[str] = field(default_factory=list)
    max_retries: int = 3
    current_retry: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    context: Dict[str, Any] = field(default_factory=dict)
    result: Optional[TaskResult] = None
    consensus_required: bool = False
    min_consensus_votes: int = 2
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        """Initialize derived fields after creation."""
        if not self.required_capabilities:
            self.required_capabilities = self._infer_capabilities()

    def _infer_capabilities(self) -> List[str]:
        """Infer required capabilities from task type."""
        capability_map = {
            "research": ["information_retrieval", "analysis", "web_search"],
            "code": ["programming", "debugging", "testing", "architecture"],
            "review": ["quality_assurance", "analysis", "documentation"],
            "write": ["content_creation", "documentation", "communication"],
            "plan": ["strategy", "scheduling", "resource_management"],
            "analysis": ["data_analysis", "statistics", "visualization"],
            "design": ["ui_ux", "prototyping", "creativity"],
            "testing": ["qa", "automation", "debugging"],
        }
        return capability_map.get(self.task_type.lower(), ["general"])

    def mark_started(self) -> None:
        """Transition task to in-progress state."""
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()
        logger.info("task_started", task_id=self.id, task_type=self.task_type)

    def mark_completed(self, result: TaskResult) -> None:
        """Transition task to completed state."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.result = result
        if self.started_at:
            result.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()
        logger.info("task_completed", task_id=self.id, success=result.success)

    def mark_failed(self, reason: str = "") -> None:
        """Transition task to failed state."""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.utcnow()
        logger.warning("task_failed", task_id=self.id, reason=reason)

    def mark_retrying(self) -> None:
        """Transition task to retrying state."""
        self.current_retry += 1
        self.status = TaskStatus.RETRYING
        logger.info(
            "task_retrying",
            task_id=self.id,
            retry=self.current_retry,
            max_retries=self.max_retries,
        )

    def can_retry(self) -> bool:
        """Check if the task can be retried."""
        return self.current_retry < self.max_retries

    def add_subtask(self, task_id: str) -> None:
        """Register a subtask ID."""
        self.subtask_ids.append(task_id)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize task to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "task_type": self.task_type,
            "priority": self.priority.name,
            "status": self.status.value,
            "required_capabilities": self.required_capabilities,
            "assigned_agent_id": self.assigned_agent_id,
            "parent_task_id": self.parent_task_id,
            "subtask_ids": self.subtask_ids,
            "max_retries": self.max_retries,
            "current_retry": self.current_retry,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "context": self.context,
            "consensus_required": self.consensus_required,
            "min_consensus_votes": self.min_consensus_votes,
            "result": self.result.to_dict() if self.result else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Self:
        """Deserialize task from dictionary."""
        task = cls(
            description=data["description"],
            task_type=data["task_type"],
            priority=TaskPriority[data["priority"]],
            status=TaskStatus(data["status"]),
            required_capabilities=data.get("required_capabilities", []),
            assigned_agent_id=data.get("assigned_agent_id"),
            parent_task_id=data.get("parent_task_id"),
            max_retries=data.get("max_retries", 3),
            current_retry=data.get("current_retry", 0),
            consensus_required=data.get("consensus_required", False),
            min_consensus_votes=data.get("min_consensus_votes", 2),
            id=data["id"],
        )
        task.subtask_ids = data.get("subtask_ids", [])
        task.context = data.get("context", {})
        if data.get("result"):
            task.result = TaskResult.from_dict(data["result"])
        if data.get("created_at"):
            task.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("started_at"):
            task.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            task.completed_at = datetime.fromisoformat(data["completed_at"])
        return task
