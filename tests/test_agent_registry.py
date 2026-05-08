"""Tests for the agent registry."""

from __future__ import annotations

import pytest

from src.agent_registry import AgentRegistry
from src.agents.coder import CoderAgent
from src.agents.researcher import ResearcherAgent
from src.agents.reviewer import ReviewerAgent


class TestAgentRegistry:
    """Test suite for the AgentRegistry."""

    def test_create_registry(self) -> None:
        """Test creating an empty registry."""
        registry = AgentRegistry()
        assert len(registry) == 0
        assert registry.get_all_agents() == []

    def test_register_single_agent(self) -> None:
        """Test registering a single agent."""
        registry = AgentRegistry()
        agent = ResearcherAgent("TestAgent")
        registry.register(agent)

        assert len(registry) == 1
        assert agent.id in registry
        assert registry.get_agent(agent.id) == agent

    def test_register_duplicate_raises(self) -> None:
        """Test that registering duplicate agent raises error."""
        registry = AgentRegistry()
        agent = ResearcherAgent("TestAgent")
        registry.register(agent)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(agent)

    def test_deregister_agent(self) -> None:
        """Test deregistering an agent."""
        registry = AgentRegistry()
        agent = ResearcherAgent("TestAgent")
        registry.register(agent)

        result = registry.deregister(agent.id)
        assert result is True
        assert len(registry) == 0
        assert agent.id not in registry

    def test_deregister_nonexistent(self) -> None:
        """Test deregistering an unknown agent."""
        registry = AgentRegistry()
        result = registry.deregister("nonexistent")
        assert result is False

    def test_get_by_type(self) -> None:
        """Test finding agents by type."""
        registry = AgentRegistry()
        r1 = ResearcherAgent("R1")
        r2 = ResearcherAgent("R2")
        c1 = CoderAgent("C1")

        registry.register(r1)
        registry.register(r2)
        registry.register(c1)

        researchers = registry.get_by_type("researcher")
        assert len(researchers) == 2
        coders = registry.get_by_type("coder")
        assert len(coders) == 1

    def test_get_by_capability(self) -> None:
        """Test finding agents by capability."""
        registry = AgentRegistry()
        r1 = ResearcherAgent("R1")
        c1 = CoderAgent("C1")

        registry.register(r1)
        registry.register(c1)

        researchers = registry.get_by_capability("information_retrieval")
        assert len(researchers) == 1

        coders = registry.get_by_capability("programming")
        assert len(coders) == 1

    def test_find_agents_with_criteria(self) -> None:
        """Test finding agents with multiple criteria."""
        registry = AgentRegistry()
        r1 = ResearcherAgent("R1")
        c1 = CoderAgent("C1")
        rev1 = ReviewerAgent("Rev1")

        registry.register(r1)
        registry.register(c1)
        registry.register(rev1)

        # Find available agents with specific capabilities
        results = registry.find_agents(
            capabilities=["information_retrieval"],
            available_only=True,
        )
        assert len(results) == 1
        assert results[0].agent_type == "researcher"

    def test_find_agents_by_type(self) -> None:
        """Test finding agents filtered by type."""
        registry = AgentRegistry()
        registry.register(ResearcherAgent("R1"))
        registry.register(ResearcherAgent("R2"))
        registry.register(CoderAgent("C1"))

        results = registry.find_agents(agent_type="researcher")
        assert len(results) == 2
        for r in results:
            assert r.agent_type == "researcher"

    def test_get_all_capabilities(self) -> None:
        """Test listing all known capabilities."""
        registry = AgentRegistry()
        registry.register(ResearcherAgent("R1"))
        registry.register(CoderAgent("C1"))

        caps = registry.get_all_capabilities()
        assert "information_retrieval" in caps
        assert "programming" in caps

    def test_get_agent_types(self) -> None:
        """Test listing all agent types."""
        registry = AgentRegistry()
        registry.register(ResearcherAgent("R1"))
        registry.register(CoderAgent("C1"))
        registry.register(ReviewerAgent("Rev1"))

        types = registry.get_agent_types()
        assert sorted(types) == sorted(["researcher", "coder", "reviewer"])

    def test_get_agent_count(self) -> None:
        """Test counting agents."""
        registry = AgentRegistry()
        registry.register(ResearcherAgent("R1"))
        registry.register(ResearcherAgent("R2"))
        registry.register(CoderAgent("C1"))

        assert registry.get_agent_count() == 3
        assert registry.get_agent_count("researcher") == 2
        assert registry.get_agent_count("coder") == 1

    def test_get_health_status(self) -> None:
        """Test health status reporting."""
        registry = AgentRegistry()
        registry.register(ResearcherAgent("R1"))
        registry.register(CoderAgent("C1"))

        health = registry.get_health_status()
        assert health["total_agents"] == 2
        assert health["available"] == 2
        assert "state_distribution" in health

    def test_metrics(self) -> None:
        """Test registry metrics."""
        registry = AgentRegistry()
        agent = ResearcherAgent("R1")
        registry.register(agent)
        registry.deregister(agent.id)

        metrics = registry.metrics
        assert metrics["registrations"] == 1
        assert metrics["deregistrations"] == 1

    def test_shutdown_all(self) -> None:
        """Test shutting down all agents."""
        registry = AgentRegistry()
        registry.register(ResearcherAgent("R1"))
        registry.register(CoderAgent("C1"))

        registry.shutdown_all()
        assert len(registry) == 0

    def test_contains(self) -> None:
        """Test the 'in' operator."""
        registry = AgentRegistry()
        agent = ResearcherAgent("R1")
        registry.register(agent)

        assert agent.id in registry
        assert "nonexistent" not in registry
