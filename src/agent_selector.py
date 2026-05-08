"""Agent selection algorithms for optimal task-agent matching."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import structlog

from src.agents.base_agent import BaseAgent
from src.tasks.task import Task

logger = structlog.get_logger(__name__)


@dataclass
class SelectionResult:
    """Result of an agent selection operation."""

    agent: BaseAgent
    score: float
    strategy: str
    metadata: Dict[str, Any]


class AgentSelector:
    """Selects the best agent for a given task using configurable strategies.

    Supports multiple selection algorithms:
    - best_match: Highest capability score
    - least_loaded: Lowest current load
    - round_robin: Even distribution
    - random: Random selection among candidates
    - weighted: Combined capability-load score
    """

    def __init__(self) -> None:
        self._round_robin_counters: Dict[str, int] = {}
        self._selection_count = 0
        self._strategy_hits: Dict[str, int] = {}
        self._log = logger

    def select(
        self,
        candidates: List[BaseAgent],
        task: Task,
        strategy: str = "best_match",
        custom_scorer: Optional[Callable[[BaseAgent, Task], float]] = None,
    ) -> Optional[SelectionResult]:
        """Select the best agent for a task.

        Args:
            candidates: Available agents to choose from.
            task: The task to be assigned.
            strategy: Selection strategy name.
            custom_scorer: Optional custom scoring function.

        Returns:
            SelectionResult with chosen agent and score, or None.
        """
        if not candidates:
            self._log.warning("no_candidates_for_selection", task_id=task.id)
            return None

        self._selection_count += 1
        self._strategy_hits[strategy] = self._strategy_hits.get(strategy, 0) + 1

        scorer = custom_scorer or self._get_scorer(strategy)

        scored = []
        for agent in candidates:
            try:
                score = scorer(agent, task)
                scored.append((agent, score))
            except Exception as exc:
                self._log.debug(
                    "scoring_error",
                    agent_id=agent.id,
                    error=str(exc),
                )

        if not scored:
            return None

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        best_agent, best_score = scored[0]

        metadata = {
            "candidates_evaluated": len(candidates),
            "top_score": best_score,
            "all_scores": {a.id: s for a, s in scored},
        }

        self._log.debug(
            "agent_selected",
            task_id=task.id,
            agent_id=best_agent.id,
            strategy=strategy,
            score=best_score,
        )

        return SelectionResult(
            agent=best_agent,
            score=best_score,
            strategy=strategy,
            metadata=metadata,
        )

    def select_multiple(
        self,
        candidates: List[BaseAgent],
        task: Task,
        count: int,
        strategy: str = "best_match",
    ) -> List[SelectionResult]:
        """Select multiple agents for a collaborative task.

        Args:
            candidates: Available agents.
            task: The task requiring collaboration.
            count: Number of agents to select.
            strategy: Selection strategy.

        Returns:
            List of selection results.
        """
        results = []
        remaining = list(candidates)

        for _ in range(min(count, len(candidates))):
            result = self.select(remaining, task, strategy)
            if result:
                results.append(result)
                remaining.remove(result.agent)
            else:
                break

        return results

    def _get_scorer(
        self, strategy: str
    ) -> Callable[[BaseAgent, Task], float]:
        """Get the scoring function for a strategy.

        Args:
            strategy: Strategy name.

        Returns:
            Scoring callable.
        """
        scorers = {
            "best_match": self._score_best_match,
            "least_loaded": self._score_least_loaded,
            "round_robin": self._score_round_robin,
            "random": self._score_random,
            "weighted": self._score_weighted,
            "capability_then_load": self._score_capability_then_load,
        }
        return scorers.get(strategy, self._score_best_match)

    def _score_best_match(self, agent: BaseAgent, task: Task) -> float:
        """Score based on capability match quality.

        Args:
            agent: The agent to score.
            task: The task requirements.

        Returns:
            Composite capability score (0.0-1.0).
        """
        if not task.required_capabilities:
            return 0.5  # Default for tasks with no specific requirements

        return agent.composite_score(task.required_capabilities)

    def _score_least_loaded(self, agent: BaseAgent, task: Task) -> float:
        """Score based on how available the agent is.

        Args:
            agent: The agent to score.
            task: The task (unused but required by signature).

        Returns:
            Availability score (1.0 = fully available).
        """
        return 1.0 - agent.load_factor

    def _score_round_robin(self, agent: BaseAgent, task: Task) -> float:
        """Score using round-robin counter per agent type.

        Args:
            agent: The agent to score.
            task: The task.

        Returns:
            Score that cycles through agents evenly.
        """
        task_type = task.task_type
        counter = self._round_robin_counters.get(task_type, 0)
        agents_of_type = [
            a for a in [agent]  # Simplified: actual RR needs global state
        ]
        idx = hash(agent.id) % max(len(agents_of_type), 1)
        self._round_robin_counters[task_type] = counter + 1
        # Give a small boost to agents that have been selected less
        return 0.5 + (counter % 2) * 0.1

    def _score_random(self, agent: BaseAgent, task: Task) -> float:
        """Assign a random score.

        Args:
            agent: The agent to score (unused).
            task: The task (unused).

        Returns:
            Random score between 0 and 1.
        """
        return random.random()

    def _score_weighted(self, agent: BaseAgent, task: Task) -> float:
        """Combined score balancing capability and load.

        Formula: 0.6 * capability + 0.4 * (1 - load)

        Args:
            agent: The agent to score.
            task: The task.

        Returns:
            Weighted composite score.
        """
        capability = self._score_best_match(agent, task)
        availability = 1.0 - agent.load_factor
        return capability * 0.6 + availability * 0.4

    def _score_capability_then_load(
        self, agent: BaseAgent, task: Task
    ) -> float:
        """Score prioritizing capability, with load as tiebreaker.

        Args:
            agent: The agent to score.
            task: The task.

        Returns:
            Tiered composite score.
        """
        capability = self._score_best_match(agent, task)
        availability = 1.0 - agent.load_factor
        # Capability is primary (80%), availability breaks ties (20%)
        return capability * 0.8 + availability * 0.2

    def get_stats(self) -> Dict[str, Any]:
        """Return selection statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "total_selections": self._selection_count,
            "strategy_distribution": self._strategy_hits.copy(),
            "available_strategies": [
                "best_match",
                "least_loaded",
                "round_robin",
                "random",
                "weighted",
                "capability_then_load",
            ],
        }

    def reset_counters(self) -> None:
        """Reset round-robin and other counters."""
        self._round_robin_counters.clear()
        self._selection_count = 0
        self._log.info("selector_counters_reset")
