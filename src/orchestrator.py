"""Orchestrator that manages the agent swarm lifecycle and task delegation."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Dict, List, Optional, Callable

import structlog

from src.agent_registry import AgentRegistry
from src.agent_selector import AgentSelector
from src.agents.base_agent import BaseAgent
from src.consensus import ConsensusMechanism, ConsensusResult, VoteValue
from src.message_bus import MessageBus, Message, MessageType
from src.performance import PerformanceTracker
from src.task_decomposer import TaskDecomposer
from src.tasks.task import Task, TaskPriority, TaskResult, TaskStatus
from src.tasks.task_queue import TaskQueue

logger = structlog.get_logger(__name__)


class SwarmOrchestrator:
    """Central orchestrator for the agent swarm.

    Manages the full lifecycle: task ingestion, decomposition, agent selection,
    delegation with retry, consensus coordination, and performance tracking.
    """

    def __init__(
        self,
        max_workers: int = 10,
        auto_decompose: bool = True,
        selection_strategy: str = "weighted",
        enable_load_balancing: bool = True,
        retry_policy: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.registry = AgentRegistry()
        self.task_queue = TaskQueue()
        self.message_bus = MessageBus()
        self.decomposer = TaskDecomposer()
        self.selector = AgentSelector()
        self.consensus = ConsensusMechanism()
        self.tracker = PerformanceTracker()

        self.max_workers = max_workers
        self.auto_decompose = auto_decompose
        self.selection_strategy = selection_strategy
        self.enable_load_balancing = enable_load_balancing
        self.retry_policy = retry_policy or {
            "max_retries": 3,
            "backoff_factor": 2.0,
            "retryable_statuses": ["failed", "error"],
        }

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="swarm_worker",
        )
        self._running = False
        self._orchestrator_thread: Optional[threading.Thread] = None
        self._delegation_callbacks: List[Callable[[Task, str], None]] = []
        self._completion_callbacks: List[Callable[[Task, TaskResult], None]] = []
        self._lock = threading.RLock()
        self._log = logger

    def start(self) -> None:
        """Start the orchestrator and all subsystems."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self.message_bus.start()
            self._orchestrator_thread = threading.Thread(
                target=self._orchestration_loop,
                daemon=True,
                name="SwarmOrchestrator",
            )
            self._orchestrator_thread.start()

            self._log.info(
                "orchestrator_started",
                workers=self.max_workers,
                strategy=self.selection_strategy,
            )

    def stop(self) -> None:
        """Gracefully shut down the orchestrator."""
        with self._lock:
            self._running = False

            if self._orchestrator_thread:
                self._orchestrator_thread.join(timeout=5.0)
                self._orchestrator_thread = None

            self._executor.shutdown(wait=False)
            self.message_bus.stop()
            self.registry.shutdown_all()

            self._log.info("orchestrator_stopped")

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent and wire up messaging.

        Args:
            agent: The agent to register.
        """
        self.registry.register(agent)

        # Subscribe agent to message bus
        self.message_bus.subscribe(
            subscriber_id=agent.id,
            handler=lambda msg, a=agent: self._on_agent_message(a, msg),
            message_types=[
                MessageType.DIRECT,
                MessageType.TASK_REQUEST,
                MessageType.STATUS_UPDATE,
                MessageType.COORDINATION,
            ],
        )

        # Wire agent's send to message bus
        agent.register_message_handler(
            lambda sender_id, content, bus=self.message_bus: None
        )

        self._log.info("agent_registered_with_orchestrator", agent_id=agent.id)

    def submit_task(
        self,
        task: Task,
        callback: Optional[Callable[[Task, TaskResult], None]] = None,
    ) -> str:
        """Submit a task for execution by the swarm.

        Args:
            task: The task to execute.
            callback: Optional completion callback.

        Returns:
            The task ID.
        """
        self.tracker.record_task_submitted()

        if callback:
            with self._lock:
                self._completion_callbacks.append(callback)

        # Auto-decompose if enabled and applicable
        if self.auto_decompose and self.decomposer.should_decompose(task):
            subtasks = self.decomposer.decompose(task)
            for subtask in subtasks:
                self.task_queue.enqueue(subtask)
            self._log.info(
                "task_decomposed",
                task_id=task.id,
                subtask_count=len(subtasks),
            )
        else:
            self.task_queue.enqueue(task)

        self._log.info(
            "task_submitted",
            task_id=task.id,
            task_type=task.task_type,
            priority=task.priority.name,
        )
        return task.id

    def submit_task_simple(
        self,
        description: str,
        task_type: str = "general",
        priority: TaskPriority = TaskPriority.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create and submit a task with minimal parameters.

        Args:
            description: Task description.
            task_type: Task category.
            priority: Task priority.
            context: Additional context.

        Returns:
            The task ID.
        """
        task = Task(
            description=description,
            task_type=task_type,
            priority=priority,
            context=context or {},
        )
        return self.submit_task(task)

    def _orchestration_loop(self) -> None:
        """Main loop that continuously processes tasks."""
        while self._running:
            try:
                task = self.task_queue.dequeue()
                if task:
                    self._process_task(task)
                else:
                    time.sleep(0.1)

                # Update performance metrics periodically
                self._update_system_metrics()

            except Exception as exc:
                self._log.error("orchestration_error", error=str(exc))
                time.sleep(0.5)

    def _process_task(self, task: Task) -> None:
        """Process a single task through the full lifecycle.

        Args:
            task: The task to process.
        """
        try:
            # Step 1: Find candidates
            candidates = self.registry.find_agents(
                capabilities=task.required_capabilities,
                available_only=True,
            )

            if not candidates:
                self._log.warning(
                    "no_candidates_available",
                    task_id=task.id,
                    capabilities=task.required_capabilities,
                )
                # Requeue with slight delay indication
                task.status = TaskStatus.QUEUED
                self.task_queue.requeue(task)
                time.sleep(0.5)
                return

            # Step 2: Apply load balancing if enabled
            if self.enable_load_balancing:
                candidates = self._balance_load(candidates)

            # Step 3: Select best agent
            selection = self.selector.select(
                candidates=candidates,
                task=task,
                strategy=self.selection_strategy,
            )

            if not selection:
                self._log.warning("no_agent_selected", task_id=task.id)
                self.task_queue.requeue(task)
                return

            selected_agent = selection.agent
            self.tracker.record_delegation()

            self._log.info(
                "task_delegated",
                task_id=task.id,
                agent_id=selected_agent.id,
                score=selection.score,
                strategy=selection.strategy,
            )

            # Step 4: Execute
            if task.consensus_required:
                self._execute_with_consensus(task, selected_agent)
            else:
                self._execute_task(task, selected_agent)

        except Exception as exc:
            self._log.error("task_processing_error", task_id=task.id, error=str(exc))
            if task.can_retry():
                task.mark_retrying()
                self.task_queue.requeue(task)
            else:
                task.mark_failed(str(exc))

    def _execute_task(self, task: Task, agent: BaseAgent) -> None:
        """Execute a task on a selected agent.

        Args:
            task: The task to execute.
            agent: The selected agent.
        """
        future = self._executor.submit(agent.execute_task, task)

        def on_done(f: Future[TaskResult]) -> None:
            try:
                result = f.result()
                self._handle_task_result(task, agent, result)
            except Exception as exc:
                error_result = TaskResult(
                    task_id=task.id,
                    agent_id=agent.id,
                    success=False,
                    output="",
                    metadata={"error": str(exc)},
                    duration_seconds=0.0,
                )
                self._handle_task_result(task, agent, error_result)

        future.add_done_callback(on_done)

    def _execute_with_consensus(
        self, task: Task, primary_agent: BaseAgent
    ) -> None:
        """Execute a task using consensus among multiple agents.

        Args:
            task: The task to execute.
            primary_agent: The primary selected agent.
        """
        # Select additional agents for consensus
        candidates = self.registry.find_agents(
            capabilities=task.required_capabilities,
            available_only=True,
        )
        # Exclude primary agent
        candidates = [a for a in candidates if a.id != primary_agent.id]

        consensus_size = min(task.min_consensus_votes - 1, len(candidates))
        collaborators = candidates[:consensus_size]
        all_participants = [primary_agent] + collaborators

        # Initiate consensus
        consensus_result = self.consensus.initiate(
            topic=f"execution_plan:{task.id}",
            participants=all_participants,
            strategy="simple_majority",
        )

        task.status = TaskStatus.AWAITING_CONSENSUS
        self.tracker.record_consensus()

        # Have each participant vote
        for participant in all_participants:
            score = participant.composite_score(task.required_capabilities)
            vote = VoteValue.YES if score > 0.5 else VoteValue.ABSTAIN
            self.consensus.collect_vote(
                consensus_id=consensus_result.consensus_id,
                agent=participant,
                vote_value=vote,
                justification=f"Capability match score: {score:.2f}",
            )

        # Check consensus result
        final_result = self.consensus.get_result(consensus_result.consensus_id)
        if final_result and final_result.state.value == "consensus_achieved":
            self._execute_task(task, primary_agent)
            # Also have collaborators review
            for collaborator in collaborators:
                review_task = Task(
                    description=f"Review task {task.id}",
                    task_type="review",
                    priority=TaskPriority.MEDIUM,
                    context={"original_task_id": task.id},
                )
                self._execute_task(review_task, collaborator)
        else:
            # No consensus, execute with primary only
            self._log.info(
                "no_consensus_fallback",
                task_id=task.id,
                consensus_id=consensus_result.consensus_id,
            )
            self._execute_task(task, primary_agent)

    def _handle_task_result(
        self, task: Task, agent: BaseAgent, result: TaskResult
    ) -> None:
        """Process task execution result.

        Args:
            task: The executed task.
            agent: The executing agent.
            result: Execution result.
        """
        result.retry_count = task.current_retry

        self.tracker.record_task_result(
            agent_id=agent.id,
            agent_type=agent.agent_type,
            success=result.success,
            duration=result.duration_seconds,
            retry_count=task.current_retry,
        )

        if result.success:
            task.mark_completed(result)
            self._notify_completion(task, result)
        elif task.can_retry():
            self._log.info(
                "task_retry",
                task_id=task.id,
                retry=task.current_retry + 1,
            )
            task.mark_retrying()

            # Exponential backoff
            backoff = self.retry_policy.get("backoff_factor", 2.0)
            sleep_time = (backoff ** task.current_retry) * 0.1
            time.sleep(sleep_time)

            self.task_queue.requeue(task)
        else:
            task.mark_failed(result.output or "Max retries exceeded")
            self._notify_completion(task, result)

    def _on_agent_message(self, agent: BaseAgent, message: Message) -> None:
        """Handle incoming message bus messages for an agent.

        Args:
            agent: The receiving agent.
            message: The message.
        """
        # Filter: only deliver direct messages to the intended recipient
        if message.recipient_id and message.recipient_id != agent.id:
            return

        agent.receive_message(message.sender_id, message.to_dict())
        self.tracker.record_message_exchanged()

    def _balance_load(self, candidates: List[BaseAgent]) -> List[BaseAgent]:
        """Apply load balancing to candidate ordering.

        Sorts candidates to prefer less-loaded agents while maintaining
        capability match quality.

        Args:
            candidates: Available agents.

        Returns:
            Reordered candidates.
        """
        if len(candidates) <= 1:
            return candidates

        # Sort by load factor ascending (prefer less loaded)
        return sorted(candidates, key=lambda a: a.load_factor)

    def _update_system_metrics(self) -> None:
        """Update aggregate system performance metrics."""
        agents = self.registry.get_all_agents()
        active = len(agents)
        busy = sum(1 for a in agents if not a.is_available)
        self.tracker.update_agent_counts(active, busy)

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a submitted task.

        Args:
            task_id: The task identifier.

        Returns:
            Status dictionary, or None.
        """
        task = self.task_queue.get_task(task_id)
        if task:
            return task.to_dict()
        return None

    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive system metrics.

        Returns:
            Metrics dictionary.
        """
        return {
            "swarm": self.tracker.get_swarm_metrics().to_dict(),
            "queue": {
                "size": len(self.task_queue),
                "metrics": self.task_queue.metrics,
                "priority_distribution": self.task_queue.get_priority_distribution(),
            },
            "registry": {
                "total_agents": len(self.registry),
                "types": self.registry.get_agent_types(),
                "capabilities": self.registry.get_all_capabilities(),
                "health": self.registry.get_health_status(),
            },
            "selector": self.selector.get_stats(),
            "decomposer": self.decomposer.get_stats(),
            "consensus": {
                "metrics": self.consensus.metrics,
                "active": self.consensus.active_count,
            },
            "message_bus": self.message_bus.metrics,
        }

    def get_health(self) -> Dict[str, Any]:
        """Get overall swarm health status.

        Returns:
            Health status dictionary.
        """
        metrics = self.tracker.get_swarm_metrics()
        bottlenecks = self.tracker.get_bottlenecks()

        status = "healthy"
        if bottlenecks:
            status = "degraded"
        if metrics.avg_system_load > 0.9:
            status = "critical"

        return {
            "status": status,
            "is_running": self._running,
            "metrics": metrics.to_dict(),
            "bottlenecks": bottlenecks,
            "agent_health": self.registry.get_health_status(),
        }

    def on_delegation(
        self, callback: Callable[[Task, str], None]
    ) -> None:
        """Register a callback for task delegation events.

        Args:
            callback: Function receiving (task, agent_id).
        """
        with self._lock:
            self._delegation_callbacks.append(callback)

    def on_completion(
        self, callback: Callable[[Task, TaskResult], None]
    ) -> None:
        """Register a callback for task completion events.

        Args:
            callback: Function receiving (task, result).
        """
        with self._lock:
            self._completion_callbacks.append(callback)

    def _notify_completion(self, task: Task, result: TaskResult) -> None:
        """Notify completion callbacks.

        Args:
            task: The completed task.
            result: The execution result.
        """
        for cb in self._completion_callbacks:
            try:
                cb(task, result)
            except Exception as exc:
                self._log.error("completion_callback_error", error=str(exc))

    def wait_for_empty(self, timeout: float = 30.0) -> bool:
        """Wait for the task queue to become empty.

        Args:
            timeout: Maximum wait time in seconds.

        Returns:
            True if queue emptied within timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.task_queue.is_empty():
                # Also wait for in-flight tasks
                time.sleep(0.5)
                return self.task_queue.is_empty()
            time.sleep(0.1)
        return False

    def __enter__(self) -> SwarmOrchestrator:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()
