"""Performance tracking and metrics collection for the swarm."""

from __future__ import annotations

import statistics
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AgentPerformanceRecord:
    """Performance data for a single agent."""

    agent_id: str
    agent_type: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_retried: int = 0
    total_duration_seconds: float = 0.0
    task_durations: List[float] = field(default_factory=list)
    avg_task_duration: float = 0.0
    min_task_duration: float = float("inf")
    max_task_duration: float = 0.0
    std_task_duration: float = 0.0
    success_rate: float = 0.0
    throughput_per_minute: float = 0.0
    capability_scores: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))
    last_updated: datetime = field(default_factory=datetime.utcnow)
    first_task_at: Optional[datetime] = None
    last_task_at: Optional[datetime] = None

    def add_task(
        self,
        success: bool,
        duration: float,
        retry_count: int = 0,
    ) -> None:
        """Record a completed task.

        Args:
            success: Whether the task succeeded.
            duration: Task execution time in seconds.
            retry_count: Number of retries before completion.
        """
        now = datetime.utcnow()
        if self.first_task_at is None:
            self.first_task_at = now
        self.last_task_at = now

        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1

        self.tasks_retried += retry_count
        self.total_duration_seconds += duration
        self.task_durations.append(duration)

        self.min_task_duration = min(self.min_task_duration, duration)
        self.max_task_duration = max(self.max_task_duration, duration)

        total = self.tasks_completed + self.tasks_failed
        self.success_rate = self.tasks_completed / max(total, 1)
        self.avg_task_duration = self.total_duration_seconds / max(total, 1)

        if len(self.task_durations) > 1:
            self.std_task_duration = statistics.stdev(self.task_durations)

        # Calculate throughput (tasks per minute)
        if self.first_task_at and self.last_task_at:
            elapsed = (self.last_task_at - self.first_task_at).total_seconds()
            if elapsed > 0:
                self.throughput_per_minute = (total / elapsed) * 60

        self.last_updated = now

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "tasks_retried": self.tasks_retried,
            "total_duration_seconds": round(self.total_duration_seconds, 3),
            "avg_task_duration": round(self.avg_task_duration, 3),
            "min_task_duration": round(self.min_task_duration, 3),
            "max_task_duration": round(self.max_task_duration, 3),
            "std_task_duration": round(self.std_task_duration, 3),
            "success_rate": round(self.success_rate, 3),
            "throughput_per_minute": round(self.throughput_per_minute, 3),
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class SwarmMetrics:
    """Aggregate metrics for the entire swarm."""

    total_tasks_submitted: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    total_tasks_retried: int = 0
    total_tasks_cancelled: int = 0
    total_delegations: int = 0
    total_consensus: int = 0
    active_agents: int = 0
    busy_agents: int = 0
    avg_system_load: float = 0.0
    avg_success_rate: float = 0.0
    total_messages_exchanged: int = 0
    avg_task_latency_seconds: float = 0.0
    throughput_per_minute: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_tasks_submitted": self.total_tasks_submitted,
            "total_tasks_completed": self.total_tasks_completed,
            "total_tasks_failed": self.total_tasks_failed,
            "total_tasks_retried": self.total_tasks_retried,
            "total_tasks_cancelled": self.total_tasks_cancelled,
            "total_delegations": self.total_delegations,
            "total_consensus": self.total_consensus,
            "active_agents": self.active_agents,
            "busy_agents": self.busy_agents,
            "avg_system_load": round(self.avg_system_load, 3),
            "avg_success_rate": round(self.avg_success_rate, 3),
            "total_messages_exchanged": self.total_messages_exchanged,
            "avg_task_latency_seconds": round(self.avg_task_latency_seconds, 3),
            "throughput_per_minute": round(self.throughput_per_minute, 3),
            "timestamp": self.timestamp.isoformat(),
        }


class PerformanceTracker:
    """Tracks and reports performance metrics for agents and the swarm.

    Collects execution times, success rates, throughput, and load
    distribution data for analysis and optimization.
    """

    def __init__(self, window_size: int = 1000) -> None:
        self._agent_records: Dict[str, AgentPerformanceRecord] = {}
        self._swarm_metrics = SwarmMetrics()
        self._task_latencies: List[float] = []
        self._window_size = window_size
        self._lock = threading.RLock()
        self._start_time = datetime.utcnow()
        self._callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        self._log = logger

    def record_task_result(
        self,
        agent_id: str,
        agent_type: str,
        success: bool,
        duration: float,
        retry_count: int = 0,
    ) -> None:
        """Record the result of a task execution.

        Args:
            agent_id: The executing agent's ID.
            agent_type: The agent type.
            success: Whether execution succeeded.
            duration: Execution time in seconds.
            retry_count: Number of retries.
        """
        with self._lock:
            record = self._agent_records.get(agent_id)
            if record is None:
                record = AgentPerformanceRecord(
                    agent_id=agent_id,
                    agent_type=agent_type,
                )
                self._agent_records[agent_id] = record

            record.add_task(success, duration, retry_count)

            if success:
                self._swarm_metrics.total_tasks_completed += 1
            else:
                self._swarm_metrics.total_tasks_failed += 1

            if retry_count > 0:
                self._swarm_metrics.total_tasks_retried += 1

            self._task_latencies.append(duration)
            if len(self._task_latencies) > self._window_size:
                self._task_latencies = self._task_latencies[-self._window_size:]

            self._update_aggregate_metrics()

    def record_task_submitted(self) -> None:
        """Increment the task submission counter."""
        with self._lock:
            self._swarm_metrics.total_tasks_submitted += 1

    def record_task_cancelled(self) -> None:
        """Increment the task cancellation counter."""
        with self._lock:
            self._swarm_metrics.total_tasks_cancelled += 1

    def record_delegation(self) -> None:
        """Increment the delegation counter."""
        with self._lock:
            self._swarm_metrics.total_delegations += 1

    def record_consensus(self) -> None:
        """Increment the consensus counter."""
        with self._lock:
            self._swarm_metrics.total_consensus += 1

    def record_message_exchanged(self, count: int = 1) -> None:
        """Increment the message exchange counter.

        Args:
            count: Number of messages to add.
        """
        with self._lock:
            self._swarm_metrics.total_messages_exchanged += count

    def update_agent_counts(self, active: int, busy: int) -> None:
        """Update the active/busy agent counters.

        Args:
            active: Number of active agents.
            busy: Number of busy agents.
        """
        with self._lock:
            self._swarm_metrics.active_agents = active
            self._swarm_metrics.busy_agents = busy

    def _update_aggregate_metrics(self) -> None:
        """Recalculate aggregate performance metrics."""
        records = list(self._agent_records.values())
        if not records:
            return

        self._swarm_metrics.avg_success_rate = statistics.mean(
            r.success_rate for r in records
        ) if records else 0.0

        self._swarm_metrics.avg_task_latency_seconds = statistics.mean(
            self._task_latencies
        ) if self._task_latencies else 0.0

        self._swarm_metrics.throughput_per_minute = sum(
            r.throughput_per_minute for r in records
        )

        elapsed = (datetime.utcnow() - self._start_time).total_seconds()
        if elapsed > 0 and self._swarm_metrics.active_agents > 0:
            self._swarm_metrics.avg_system_load = (
                self._swarm_metrics.busy_agents
                / max(self._swarm_metrics.active_agents, 1)
            )

        self._swarm_metrics.timestamp = datetime.utcnow()

    def get_agent_performance(self, agent_id: str) -> Optional[AgentPerformanceRecord]:
        """Get performance data for a specific agent.

        Args:
            agent_id: The agent to look up.

        Returns:
            Performance record, or None.
        """
        with self._lock:
            return self._agent_records.get(agent_id)

    def get_all_agent_performance(self) -> Dict[str, AgentPerformanceRecord]:
        """Get performance data for all agents.

        Returns:
            Mapping of agent ID to performance record.
        """
        with self._lock:
            return dict(self._agent_records)

    def get_swarm_metrics(self) -> SwarmMetrics:
        """Get aggregate swarm metrics.

        Returns:
            Current swarm metrics snapshot.
        """
        with self._lock:
            return self._swarm_metrics

    def get_top_performers(
        self,
        metric: str = "success_rate",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get top-performing agents by a specific metric.

        Args:
            metric: Metric to sort by (success_rate, throughput, etc.).
            limit: Maximum results.

        Returns:
            List of agent performance data.
        """
        with self._lock:
            records = list(self._agent_records.values())

        if not records:
            return []

        reverse = True
        if metric == "avg_task_duration":
            reverse = False  # Lower is better

        try:
            sorted_records = sorted(
                records,
                key=lambda r: getattr(r, metric, 0),
                reverse=reverse,
            )
        except AttributeError:
            sorted_records = records

        return [r.to_dict() for r in sorted_records[:limit]]

    def get_bottlenecks(self) -> List[Dict[str, Any]]:
        """Identify potential bottlenecks in the swarm.

        Returns:
            List of bottleneck descriptions.
        """
        with self._lock:
            records = list(self._agent_records.values())
            bottlenecks = []

            for record in records:
                if record.success_rate < 0.5 and record.tasks_completed + record.tasks_failed > 5:
                    bottlenecks.append({
                        "type": "low_success_rate",
                        "agent_id": record.agent_id,
                        "agent_type": record.agent_type,
                        "success_rate": round(record.success_rate, 3),
                        "recommendation": "Investigate failure patterns",
                    })

                if record.avg_task_duration > 10.0 and record.tasks_completed > 0:
                    bottlenecks.append({
                        "type": "slow_execution",
                        "agent_id": record.agent_id,
                        "agent_type": record.agent_type,
                        "avg_duration": round(record.avg_task_duration, 3),
                        "recommendation": "Consider optimization or scaling",
                    })

            if self._swarm_metrics.avg_system_load > 0.8:
                bottlenecks.append({
                    "type": "high_system_load",
                    "load": round(self._swarm_metrics.avg_system_load, 3),
                    "recommendation": "Add more agents or reduce task submission",
                })

            return bottlenecks

    def get_load_distribution(self) -> Dict[str, float]:
        """Calculate the load distribution across agent types.

        Returns:
            Mapping of agent type to load percentage.
        """
        with self._lock:
            type_loads: Dict[str, List[float]] = defaultdict(list)
            for record in self._agent_records.values():
                type_loads[record.agent_type].append(record.throughput_per_minute)

            totals = {t: sum(loads) for t, loads in type_loads.items()}
            grand_total = sum(totals.values())

            if grand_total == 0:
                return {t: 0.0 for t in type_loads}

            return {
                t: round(v / grand_total, 3)
                for t, v in totals.items()
            }

    def register_callback(
        self, callback: Callable[[str, Dict[str, Any]], None]
    ) -> None:
        """Register a callback for metric change notifications.

        Args:
            callback: Function receiving (event_type, data).
        """
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def reset(self) -> None:
        """Clear all performance data."""
        with self._lock:
            self._agent_records.clear()
            self._swarm_metrics = SwarmMetrics()
            self._task_latencies.clear()
            self._start_time = datetime.utcnow()
            self._log.info("performance_tracker_reset")

    def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive performance report.

        Returns:
            Report dictionary.
        """
        with self._lock:
            return {
                "swarm": self._swarm_metrics.to_dict(),
                "agents": {
                    aid: rec.to_dict()
                    for aid, rec in self._agent_records.items()
                },
                "top_performers": self.get_top_performers(),
                "bottlenecks": self.get_bottlenecks(),
                "load_distribution": self.get_load_distribution(),
            }
