"""Tests for the swarm orchestrator."""

from __future__ import annotations

import time
from typing import Any

import pytest

from src.agents.coder import CoderAgent
from src.agents.planner import PlannerAgent
from src.agents.researcher import ResearcherAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.writer import WriterAgent
from src.orchestrator import SwarmOrchestrator
from src.tasks.task import Task, TaskPriority, TaskStatus


class TestSwarmOrchestrator:
    """Test suite for the SwarmOrchestrator."""

    def test_orchestrator_creation(self) -> None:
        """Test creating an orchestrator with default settings."""
        orch = SwarmOrchestrator()
        assert orch.max_workers == 10
        assert orch.auto_decompose is True
        assert orch.selection_strategy == "weighted"
        assert orch.enable_load_balancing is True

    def test_orchestrator_start_stop(self) -> None:
        """Test starting and stopping the orchestrator."""
        orch = SwarmOrchestrator()
        orch.start()
        assert orch._running is True
        orch.stop()
        assert orch._running is False

    def test_orchestrator_context_manager(self) -> None:
        """Test using orchestrator as context manager."""
        with SwarmOrchestrator() as orch:
            assert orch._running is True
        assert orch._running is False

    def test_register_agent(self) -> None:
        """Test agent registration."""
        orch = SwarmOrchestrator()
        agent = ResearcherAgent("TestAgent")
        orch.register_agent(agent)
        assert len(orch.registry) == 1
        assert orch.registry.get_agent(agent.id) == agent

    def test_register_multiple_agents(self) -> None:
        """Test registering multiple agents."""
        orch = SwarmOrchestrator()
        agents = [
            ResearcherAgent("R1"),
            CoderAgent("C1"),
            ReviewerAgent("Rev1"),
            WriterAgent("W1"),
            PlannerAgent("P1"),
        ]
        for a in agents:
            orch.register_agent(a)

        assert len(orch.registry) == 5
        assert len(orch.registry.get_agent_types()) == 5

    def test_submit_task(self) -> None:
        """Test task submission."""
        orch = SwarmOrchestrator(auto_decompose=False)
        orch.register_agent(ResearcherAgent("R1"))

        task = Task(
            description="Test research task",
            task_type="research",
            priority=TaskPriority.HIGH,
        )
        task_id = orch.submit_task(task)
        assert task_id == task.id
        assert len(orch.task_queue) == 1

    def test_submit_task_simple(self) -> None:
        """Test simple task submission."""
        orch = SwarmOrchestrator(auto_decompose=False)
        orch.register_agent(CoderAgent("C1"))

        task_id = orch.submit_task_simple(
            description="Simple coding task",
            task_type="code",
            priority=TaskPriority.MEDIUM,
        )
        assert task_id is not None
        assert len(orch.task_queue) == 1

    def test_task_execution(self) -> None:
        """Test full task execution cycle."""
        orch = SwarmOrchestrator()
        orch.register_agent(ResearcherAgent("R1"))
        orch.start()

        orch.submit_task_simple(
            description="Quick research task",
            task_type="research",
            priority=TaskPriority.HIGH,
        )

        # Wait for processing
        orch.wait_for_empty(timeout=5.0)
        orch.stop()

        metrics = orch.get_metrics()
        assert metrics["swarm"]["total_tasks_submitted"] == 1

    def test_task_decomposition(self) -> None:
        """Test that complex tasks are decomposed."""
        orch = SwarmOrchestrator(auto_decompose=True)
        orch.register_agent(PlannerAgent("P1"))

        task = Task(
            description="Create a comprehensive plan with multiple phases",
            task_type="plan",
            priority=TaskPriority.HIGH,
        )
        task_id = orch.submit_task(task)

        # Complex tasks should be decomposed
        stats = orch.decomposer.get_stats()
        assert stats["total_decompositions"] >= 1

    def test_task_retry(self) -> None:
        """Test task retry mechanism."""
        orch = SwarmOrchestrator()
        assert orch.retry_policy["max_retries"] == 3
        assert orch.retry_policy["backoff_factor"] == 2.0

    def test_metrics_collection(self) -> None:
        """Test that metrics are collected during operation."""
        orch = SwarmOrchestrator()
        orch.register_agent(ResearcherAgent("R1"))
        orch.register_agent(CoderAgent("C1"))
        orch.start()

        orch.submit_task_simple("Task 1", "research")
        orch.submit_task_simple("Task 2", "code")

        orch.wait_for_empty(timeout=5.0)
        orch.stop()

        metrics = orch.get_metrics()
        assert "swarm" in metrics
        assert "registry" in metrics
        assert "queue" in metrics

    def test_health_check(self) -> None:
        """Test health status reporting."""
        orch = SwarmOrchestrator()
        orch.register_agent(ResearcherAgent("R1"))
        orch.start()

        health = orch.get_health()
        assert "status" in health
        assert "is_running" in health
        assert health["is_running"] is True

        orch.stop()

    def test_task_priority_queue(self) -> None:
        """Test that priority ordering is respected."""
        orch = SwarmOrchestrator(auto_decompose=False)
        orch.register_agent(ResearcherAgent("R1"))

        orch.submit_task(Task("Low task", task_type="research", priority=TaskPriority.LOW))
        orch.submit_task(Task("High task", task_type="research", priority=TaskPriority.HIGH))
        orch.submit_task(Task("Critical task", task_type="research", priority=TaskPriority.CRITICAL))

        tasks = orch.task_queue.list_all()
        assert tasks[0].priority == TaskPriority.CRITICAL
        assert tasks[1].priority == TaskPriority.HIGH
        assert tasks[2].priority == TaskPriority.LOW

    def test_on_completion_callback(self) -> None:
        """Test completion callback registration."""
        orch = SwarmOrchestrator()
        orch.register_agent(ResearcherAgent("R1"))
        orch.start()

        completed: list[Any] = []

        def callback(task: Task, result: Any) -> None:
            completed.append((task.id, result.success))

        orch.on_completion(callback)

        orch.submit_task_simple("Callback test", "research")
        orch.wait_for_empty(timeout=5.0)
        orch.stop()

        assert len(completed) > 0

    def test_load_balancing_enabled(self) -> None:
        """Test load balancing is active."""
        orch = SwarmOrchestrator(enable_load_balancing=True)
        orch.register_agent(ResearcherAgent("R1"))
        orch.register_agent(ResearcherAgent("R2"))
        assert orch.enable_load_balancing is True

    def test_full_swarm_run(self) -> None:
        """Test a full swarm execution with multiple agents and tasks."""
        orch = SwarmOrchestrator(max_workers=20, selection_strategy="weighted")

        # Register agents of each type
        for name in ["R1", "R2"]:
            orch.register_agent(ResearcherAgent(name))
        for name in ["C1", "C2"]:
            orch.register_agent(CoderAgent(name))
        for name in ["Rev1"]:
            orch.register_agent(ReviewerAgent(name))
        for name in ["W1"]:
            orch.register_agent(WriterAgent(name))
        for name in ["P1"]:
            orch.register_agent(PlannerAgent(name))

        orch.start()

        # Submit diverse tasks
        orch.submit_task_simple("Research AI trends", "research", TaskPriority.HIGH)
        orch.submit_task_simple("Implement auth module", "code", TaskPriority.HIGH)
        orch.submit_task_simple("Review PR", "review", TaskPriority.MEDIUM)
        orch.submit_task_simple("Write docs", "write", TaskPriority.MEDIUM)
        orch.submit_task_simple("Create plan", "plan", TaskPriority.HIGH)

        orch.wait_for_empty(timeout=10.0)
        orch.stop()

        metrics = orch.get_metrics()
        swarm = metrics["swarm"]
        assert swarm["total_tasks_submitted"] == 5
        assert swarm["total_tasks_completed"] > 0

    def test_consensus_task(self) -> None:
        """Test task execution with consensus."""
        orch = SwarmOrchestrator(auto_decompose=False)
        orch.register_agent(ResearcherAgent("R1"))
        orch.register_agent(ReviewerAgent("Rev1"))
        orch.register_agent(PlannerAgent("P1"))
        orch.start()

        task = Task(
            description="Critical architecture decision",
            task_type="plan",
            priority=TaskPriority.CRITICAL,
            consensus_required=True,
            min_consensus_votes=2,
        )
        orch.submit_task(task)

        orch.wait_for_empty(timeout=10.0)
        orch.stop()

        assert orch.consensus.metrics["initiated"] >= 1
