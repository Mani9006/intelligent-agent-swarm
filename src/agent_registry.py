"""Agent registry for discovering, tracking, and managing swarm agents."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Type

import structlog

from src.agents.base_agent import BaseAgent

logger = structlog.get_logger(__name__)


class AgentRegistry:
    """Central registry for agent discovery and lifecycle management.

    Maintains a catalog of all active agents, indexes them by type and
    capability, and provides query interfaces for agent selection.
    """

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}
        self._type_index: Dict[str, List[str]] = {}
        self._capability_index: Dict[str, List[str]] = {}
        self._lock = threading.RLock()
        self._metrics: Dict[str, int] = {
            "registrations": 0,
            "deregistrations": 0,
            "queries": 0,
        }

    def register(self, agent: BaseAgent) -> None:
        """Register an agent in the swarm.

        Args:
            agent: The agent to register.

        Raises:
            ValueError: If an agent with the same ID exists.
        """
        with self._lock:
            if agent.id in self._agents:
                raise ValueError(f"Agent {agent.id} already registered")

            self._agents[agent.id] = agent
            self._type_index.setdefault(agent.agent_type, []).append(agent.id)

            for cap_name in agent.capability_names:
                self._capability_index.setdefault(cap_name, []).append(agent.id)

            self._metrics["registrations"] += 1
            logger.info(
                "agent_registered",
                agent_id=agent.id,
                agent_type=agent.agent_type,
                capabilities=agent.capability_names,
                total_agents=len(self._agents),
            )

    def deregister(self, agent_id: str) -> bool:
        """Remove an agent from the registry.

        Args:
            agent_id: The agent to remove.

        Returns:
            True if the agent was removed.
        """
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False

            del self._agents[agent_id]

            # Remove from type index
            type_list = self._type_index.get(agent.agent_type, [])
            if agent_id in type_list:
                type_list.remove(agent_id)
                if not type_list:
                    del self._type_index[agent.agent_type]

            # Remove from capability index
            for cap_name in agent.capability_names:
                cap_list = self._capability_index.get(cap_name, [])
                if agent_id in cap_list:
                    cap_list.remove(agent_id)
                    if not cap_list:
                        del self._capability_index[cap_name]

            self._metrics["deregistrations"] += 1
            logger.info(
                "agent_deregistered",
                agent_id=agent_id,
                remaining_agents=len(self._agents),
            )
            return True

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Retrieve an agent by ID.

        Args:
            agent_id: The agent identifier.

        Returns:
            The agent if found, else None.
        """
        with self._lock:
            return self._agents.get(agent_id)

    def get_by_type(self, agent_type: str) -> List[BaseAgent]:
        """Find all agents of a specific type.

        Args:
            agent_type: The agent type to search for.

        Returns:
            List of matching agents.
        """
        with self._lock:
            return [
                self._agents[aid]
                for aid in self._type_index.get(agent_type, [])
                if aid in self._agents
            ]

    def get_by_capability(self, capability: str) -> List[BaseAgent]:
        """Find all agents with a specific capability.

        Args:
            capability: The capability name.

        Returns:
            List of agents possessing the capability.
        """
        with self._lock:
            return [
                self._agents[aid]
                for aid in self._capability_index.get(capability, [])
                if aid in self._agents
            ]

    def find_agents(
        self,
        agent_type: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        available_only: bool = True,
    ) -> List[BaseAgent]:
        """Find agents matching multiple criteria.

        Args:
            agent_type: Filter by agent type.
            capabilities: Filter by required capabilities.
            available_only: Only return available agents.

        Returns:
            List of matching agents.
        """
        with self._lock:
            self._metrics["queries"] += 1
            candidates: List[BaseAgent] = list(self._agents.values())

            if agent_type:
                candidates = [a for a in candidates if a.agent_type == agent_type]

            if capabilities:
                candidates = [
                    a for a in candidates
                    if all(a.capability_score(c) > 0 for c in capabilities)
                ]

            if available_only:
                candidates = [a for a in candidates if a.is_available]

            return candidates

    def get_all_agents(self) -> List[BaseAgent]:
        """Return all registered agents.

        Returns:
            List of all agents.
        """
        with self._lock:
            return list(self._agents.values())

    def get_agent_types(self) -> List[str]:
        """Return all registered agent types.

        Returns:
            List of unique agent type names.
        """
        with self._lock:
            return list(self._type_index.keys())

    def get_all_capabilities(self) -> List[str]:
        """Return all known capability names.

        Returns:
            List of unique capability names.
        """
        with self._lock:
            return list(self._capability_index.keys())

    def get_agent_count(self, agent_type: Optional[str] = None) -> int:
        """Count agents, optionally filtered by type.

        Args:
            agent_type: Optional type filter.

        Returns:
            Agent count.
        """
        with self._lock:
            if agent_type:
                return len(self._type_index.get(agent_type, []))
            return len(self._agents)

    def get_health_status(self) -> Dict[str, Any]:
        """Return aggregate health information for all agents.

        Returns:
            Health status dictionary.
        """
        with self._lock:
            agents_data = []
            for agent in self._agents.values():
                agents_data.append({
                    "id": agent.id,
                    "type": agent.agent_type,
                    "name": agent.name,
                    "state": agent.state.value,
                    "available": agent.is_available,
                    "load_factor": agent.load_factor,
                })

            states: Dict[str, int] = {}
            for a in self._agents.values():
                states[a.state.value] = states.get(a.state.value, 0) + 1

            return {
                "total_agents": len(self._agents),
                "available": sum(1 for a in self._agents.values() if a.is_available),
                "busy": sum(1 for a in self._agents.values() if not a.is_available),
                "state_distribution": states,
                "agents": agents_data,
            }

    def shutdown_all(self) -> None:
        """Gracefully shut down all registered agents."""
        with self._lock:
            for agent in list(self._agents.values()):
                try:
                    agent.shutdown()
                except Exception as exc:
                    logger.error(
                        "agent_shutdown_error", agent_id=agent.id, error=str(exc)
                    )
            self._agents.clear()
            self._type_index.clear()
            self._capability_index.clear()
            logger.info("all_agents_shutdown")

    @property
    def metrics(self) -> Dict[str, int]:
        """Return registry operation metrics."""
        with self._lock:
            return self._metrics.copy()

    def __len__(self) -> int:
        """Return the number of registered agents."""
        with self._lock:
            return len(self._agents)

    def __contains__(self, agent_id: str) -> bool:
        """Check if an agent is registered."""
        with self._lock:
            return agent_id in self._agents
