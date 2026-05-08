"""Tests for the agent selector."""

from __future__ import annotations

import pytest

from src.agent_selector import AgentSelector
from src.agents.coder import CoderAgent
from src.agents.researcher import ResearcherAgent
from src.agents.reviewer import ReviewerAgent
from src.tasks.task import Task, TaskPriority


class TestAgentSelector:
    """Test suite for the AgentSelector."""

    def test_create_selector(self) -> None:
        """Test creating a selector."""
        selector = AgentSelector()
        stats = selector.get_stats()
        assert stats["total_selections"] == 0

    def test_select_best_match(self) -> None:
        """Test best-match selection strategy."""
        selector = AgentSelector()
        researcher = ResearcherAgent("R1")
        coder = CoderAgent("C1")

        task = Task(
            description="Research AI trends",
            task_type="research",
            priority=TaskPriority.HIGH,
        )

        result = selector.select(
            candidates=[researcher, coder],
            task=task,
            strategy="best_match",
        )
        assert result is not None
        assert result.strategy == "best_match"
        assert result.agent.agent_type == "researcher"

    def test_select_no_candidates(self) -> None:
        """Test selection with no candidates."""
        selector = AgentSelector()
        task = Task(description="Test", task_type="code")

        result = selector.select([], task, strategy="best_match")
        assert result is None

    def test_select_least_loaded(self) -> None:
        """Test least-loaded selection strategy."""
        selector = AgentSelector()
        r1 = ResearcherAgent("R1")
        r2 = ResearcherAgent("R2")

        # Load up r1
        r1._current_tasks["dummy"] = Task("dummy", "research")  # type: ignore

        task = Task(description="Research task", task_type="research")
        result = selector.select(
            candidates=[r1, r2],
            task=task,
            strategy="least_loaded",
        )
        assert result is not None
        assert result.agent.id == r2.id  # r2 is less loaded

    def test_select_weighted(self) -> None:
        """Test weighted selection strategy."""
        selector = AgentSelector()
        researcher = ResearcherAgent("R1")
        task = Task(description="Research task", task_type="research")

        result = selector.select(
            candidates=[researcher],
            task=task,
            strategy="weighted",
        )
        assert result is not None
        assert 0.0 <= result.score <= 1.0

    def test_select_random(self) -> None:
        """Test random selection strategy."""
        selector = AgentSelector()
        r1 = ResearcherAgent("R1")
        r2 = CoderAgent("C1")
        task = Task(description="Task", task_type="code")

        # Run multiple times to verify randomness works
        results = []
        for _ in range(5):
            result = selector.select(
                candidates=[r1, r2],
                task=task,
                strategy="random",
            )
            if result:
                results.append(result.agent.id)

        assert len(results) == 5

    def test_select_multiple(self) -> None:
        """Test selecting multiple agents."""
        selector = AgentSelector()
        r1 = ResearcherAgent("R1")
        r2 = ResearcherAgent("R2")
        r3 = ReviewerAgent("Rev1")
        task = Task(description="Collaborative task", task_type="research")

        results = selector.select_multiple(
            candidates=[r1, r2, r3],
            task=task,
            count=2,
        )
        assert len(results) == 2
        assert results[0].agent != results[1].agent

    def test_select_capability_then_load(self) -> None:
        """Test capability-then-load strategy."""
        selector = AgentSelector()
        r1 = ResearcherAgent("R1")
        task = Task(
            description="Research task",
            task_type="research",
            required_capabilities=["information_retrieval"],
        )

        result = selector.select(
            candidates=[r1],
            task=task,
            strategy="capability_then_load",
        )
        assert result is not None
        assert result.score > 0.5  # Strong capability match

    def test_stats_updated(self) -> None:
        """Test that selection stats are tracked."""
        selector = AgentSelector()
        researcher = ResearcherAgent("R1")
        task = Task(description="Research task", task_type="research")

        selector.select([researcher], task, strategy="best_match")

        stats = selector.get_stats()
        assert stats["total_selections"] == 1
        assert stats["strategy_distribution"]["best_match"] == 1

    def test_reset_counters(self) -> None:
        """Test resetting counters."""
        selector = AgentSelector()
        researcher = ResearcherAgent("R1")
        task = Task(description="Research task", task_type="research")

        selector.select([researcher], task, strategy="best_match")
        selector.reset_counters()

        stats = selector.get_stats()
        assert stats["total_selections"] == 0

    def test_available_strategies(self) -> None:
        """Test that documented strategies exist."""
        selector = AgentSelector()
        stats = selector.get_stats()
        strategies = stats["available_strategies"]

        assert "best_match" in strategies
        assert "least_loaded" in strategies
        assert "weighted" in strategies
        assert "random" in strategies
        assert "round_robin" in strategies
