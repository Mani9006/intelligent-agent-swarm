"""Priority-based task queue with support for concurrent access patterns."""

from __future__ import annotations

import heapq
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from src.tasks.task import Task, TaskPriority, TaskStatus

logger = structlog.get_logger(__name__)


@dataclass(order=True)
class _QueueEntry:
    """Internal wrapper for priority queue entries."""

    priority: int
    created_at: datetime = field(compare=True)
    task: Task = field(compare=False)


class TaskQueue:
    """Thread-safe priority queue for task management.

    Supports priority ordering, FIFO within same priority, and O(1) lookups
    by task ID.
    """

    def __init__(self) -> None:
        self._heap: List[_QueueEntry] = []
        self._task_map: Dict[str, _QueueEntry] = {}
        self._lock = threading.RLock()
        self._sequence = 0
        self._metrics: Dict[str, int] = {
            "enqueued": 0,
            "dequeued": 0,
            "peeked": 0,
            "requeued": 0,
        }

    def enqueue(self, task: Task) -> None:
        """Add a task to the queue.

        Args:
            task: The task to enqueue.

        Raises:
            ValueError: If task with same ID already exists.
        """
        with self._lock:
            if task.id in self._task_map:
                raise ValueError(f"Task {task.id} already in queue")

            task.status = TaskStatus.QUEUED
            entry = _QueueEntry(
                priority=task.priority.value,
                created_at=datetime.utcnow(),
                task=task,
            )
            heapq.heappush(self._heap, entry)
            self._task_map[task.id] = entry
            self._metrics["enqueued"] += 1
            logger.debug(
                "task_enqueued",
                task_id=task.id,
                priority=task.priority.name,
                queue_size=len(self._heap),
            )

    def dequeue(self) -> Optional[Task]:
        """Remove and return the highest-priority task.

        Returns:
            The next task, or None if queue is empty.
        """
        with self._lock:
            while self._heap:
                entry = heapq.heappop(self._heap)
                task = entry.task
                if task.id in self._task_map:
                    del self._task_map[task.id]
                    self._metrics["dequeued"] += 1
                    logger.debug(
                        "task_dequeued",
                        task_id=task.id,
                        priority=task.priority.name,
                        queue_size=len(self._heap),
                    )
                    return task
            return None

    def peek(self) -> Optional[Task]:
        """Return the highest-priority task without removing it.

        Returns:
            The next task, or None if queue is empty.
        """
        with self._lock:
            self._metrics["peeked"] += 1
            for entry in self._heap:
                if entry.task.id in self._task_map:
                    return entry.task
            return None

    def requeue(self, task: Task) -> None:
        """Re-insert a task with its current priority.

        Args:
            task: The task to requeue.
        """
        with self._lock:
            if task.id in self._task_map:
                del self._task_map[task.id]
            task.status = TaskStatus.QUEUED
            entry = _QueueEntry(
                priority=task.priority.value,
                created_at=datetime.utcnow(),
                task=task,
            )
            heapq.heappush(self._heap, entry)
            self._task_map[task.id] = entry
            self._metrics["requeued"] += 1
            logger.debug("task_requeued", task_id=task.id)

    def get_task(self, task_id: str) -> Optional[Task]:
        """Look up a task by ID.

        Args:
            task_id: The task identifier.

        Returns:
            The task if found, else None.
        """
        with self._lock:
            entry = self._task_map.get(task_id)
            return entry.task if entry else None

    def remove(self, task_id: str) -> bool:
        """Remove a task from the queue by ID.

        Args:
            task_id: The task identifier.

        Returns:
            True if the task was removed.
        """
        with self._lock:
            if task_id in self._task_map:
                del self._task_map[task_id]
                logger.debug("task_removed", task_id=task_id)
                return True
            return False

    def get_by_priority(self, priority: TaskPriority) -> List[Task]:
        """Get all tasks with a specific priority.

        Args:
            priority: The priority level to filter by.

        Returns:
            List of matching tasks.
        """
        with self._lock:
            return [
                e.task
                for e in self._heap
                if e.task.id in self._task_map
                and e.task.priority == priority
            ]

    def get_by_type(self, task_type: str) -> List[Task]:
        """Get all tasks of a specific type.

        Args:
            task_type: The task type to filter by.

        Returns:
            List of matching tasks.
        """
        with self._lock:
            return [
                e.task
                for e in self._heap
                if e.task.id in self._task_map
                and e.task.task_type == task_type
            ]

    def list_all(self) -> List[Task]:
        """Return all tasks in priority order.

        Returns:
            Ordered list of tasks.
        """
        with self._lock:
            return [
                e.task
                for e in sorted(self._heap)
                if e.task.id in self._task_map
            ]

    def clear(self) -> None:
        """Remove all tasks from the queue."""
        with self._lock:
            self._heap.clear()
            self._task_map.clear()
            logger.info("queue_cleared")

    def __len__(self) -> int:
        """Return the number of tasks in the queue."""
        with self._lock:
            return len(self._task_map)

    def is_empty(self) -> bool:
        """Check if the queue is empty."""
        return len(self) == 0

    @property
    def metrics(self) -> Dict[str, int]:
        """Return queue operation metrics."""
        with self._lock:
            return self._metrics.copy()

    def get_priority_distribution(self) -> Dict[str, int]:
        """Count tasks by priority level.

        Returns:
            Mapping of priority names to counts.
        """
        with self._lock:
            dist: Dict[str, int] = {}
            for entry in self._heap:
                if entry.task.id in self._task_map:
                    name = entry.task.priority.name
                    dist[name] = dist.get(name, 0) + 1
            return dist
