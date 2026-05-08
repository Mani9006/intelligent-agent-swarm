"""Researcher agent specialized in information gathering and analysis tasks."""

from __future__ import annotations

import time
from typing import Any, Dict, List

import structlog

from src.agents.base_agent import AgentCapability, BaseAgent
from src.tasks.task import Task, TaskResult

logger = structlog.get_logger(__name__)


class ResearcherAgent(BaseAgent):
    """Agent specialized in research, information retrieval, and analysis.

    Capabilities include web search, data analysis, literature review,
    and competitive intelligence gathering.
    """

    def __init__(self, name: str = "Researcher", config: Dict[str, Any] | None = None) -> None:
        capabilities = [
            AgentCapability("information_retrieval", 0.95, "Search and retrieve information"),
            AgentCapability("analysis", 0.90, "Analyze data and draw conclusions"),
            AgentCapability("web_search", 0.85, "Execute web searches effectively"),
            AgentCapability("data_analysis", 0.80, "Perform statistical data analysis"),
            AgentCapability("literature_review", 0.75, "Review and synthesize literature"),
        ]
        super().__init__(
            name=name,
            agent_type="researcher",
            capabilities=capabilities,
            max_concurrent_tasks=2,
            config=config,
        )
        self._research_cache: Dict[str, str] = {}
        self._log = logger.bind(agent_id=self.id, agent_type="researcher")

    def _perform_task(self, task: Task) -> TaskResult:
        """Execute research-oriented tasks.

        Args:
            task: A task requiring research capabilities.

        Returns:
            Structured research findings.
        """
        start = time.monotonic()
        self._log.info("research_started", task_id=task.id, description=task.description)

        # Check cache for similar queries
        cache_key = task.description.lower().strip()
        if cache_key in self._research_cache:
            return TaskResult(
                task_id=task.id,
                agent_id=self.id,
                success=True,
                output=self._research_cache[cache_key],
                metadata={"cached": True, "source": "research_cache"},
                duration_seconds=time.monotonic() - start,
            )

        # Simulate research work based on task context
        topic = task.context.get("topic", task.description)
        depth = task.context.get("depth", "standard")
        sources = task.context.get("sources", ["web", "academic", "industry"])

        # Generate simulated research output
        findings = self._conduct_research(topic, depth, sources)
        self._research_cache[cache_key] = findings

        duration = time.monotonic() - start
        self._log.info("research_completed", task_id=task.id, duration=duration)

        return TaskResult(
            task_id=task.id,
            agent_id=self.id,
            success=True,
            output=findings,
            metadata={
                "topic": topic,
                "depth": depth,
                "sources_consulted": sources,
                "cache_size": len(self._research_cache),
            },
            duration_seconds=duration,
        )

    def _conduct_research(
        self, topic: str, depth: str, sources: List[str]
    ) -> str:
        """Simulate a research workflow.

        Args:
            topic: The research subject.
            depth: Research depth (brief, standard, deep).
            sources: Data sources to consult.

        Returns:
            Formatted research findings.
        """
        depth_multiplier = {"brief": 1, "standard": 2, "deep": 3}.get(depth, 2)
        source_count = len(sources) * depth_multiplier

        findings = (
            f"=== Research Report: {topic} ===\n"
            f"Depth: {depth} | Sources: {', '.join(sources)}\n"
            f"Sources Consulted: {source_count}\n"
            f"\nKey Findings:\n"
            f"1. Overview: {topic} spans multiple domains with significant impact.\n"
            f"2. Trends: Identified {source_count * 2} emerging trends.\n"
            f"3. Data Points: Gathered from {source_count * 5} data sources.\n"
            f"4. Analysis: Cross-referenced findings show consistent patterns.\n"
            f"\nConclusion: Research objectives achieved with "
            f"{95 - depth_multiplier * 5}% confidence.\n"
        )
        return findings

    def receive_message(self, sender_id: str, message: Dict[str, Any]) -> None:
        """Handle messages from other agents.

        Args:
            sender_id: The sending agent's ID.
            message: The message payload.
        """
        super().receive_message(sender_id, message)
        content = message.get("content", {})
        if content.get("type") == "research_request":
            self._log.info("received_research_request", from_agent=sender_id)
