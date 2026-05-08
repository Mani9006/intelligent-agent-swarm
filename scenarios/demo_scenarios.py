"""Demo scenarios showcasing the agent swarm capabilities."""

from __future__ import annotations

import json
import random
import time
from typing import Any, Dict, List

import structlog

from src.agents.coder import CoderAgent
from src.agents.planner import PlannerAgent
from src.agents.researcher import ResearcherAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.writer import WriterAgent
from src.orchestrator import SwarmOrchestrator
from src.tasks.task import TaskPriority

logger = structlog.get_logger(__name__)


class DemoScenarios:
    """Collection of demonstration scenarios for the agent swarm."""

    @staticmethod
    def scenario_basic_delegation() -> Dict[str, Any]:
        """Scenario 1: Basic task delegation across agent types.

        Demonstrates the fundamental task assignment flow where tasks
        of different types are automatically routed to the appropriate
        specialist agents.

        Returns:
            Scenario results.
        """
        print("\n" + "=" * 60)
        print("SCENARIO 1: Basic Task Delegation")
        print("=" * 60)

        orch = SwarmOrchestrator(max_workers=10, selection_strategy="best_match")

        # Register one agent of each type
        orch.register_agent(ResearcherAgent("Alice"))
        orch.register_agent(CoderAgent("Bob"))
        orch.register_agent(ReviewerAgent("Charlie"))
        orch.register_agent(WriterAgent("Diana"))
        orch.register_agent(PlannerAgent("Eve"))

        orch.start()

        # Submit tasks matching each agent type
        tasks = [
            ("Research AI adoption trends in healthcare", "research", TaskPriority.HIGH),
            ("Implement JWT authentication middleware", "code", TaskPriority.HIGH),
            ("Review codebase for security vulnerabilities", "review", TaskPriority.CRITICAL),
            ("Write API documentation for REST endpoints", "write", TaskPriority.MEDIUM),
            ("Create quarterly roadmap with milestones", "plan", TaskPriority.HIGH),
        ]

        for desc, task_type, priority in tasks:
            orch.submit_task_simple(desc, task_type, priority)
            print(f"  Submitted: [{task_type}] {desc[:50]}...")

        orch.wait_for_empty(timeout=15.0)
        orch.stop()

        metrics = orch.get_metrics()
        print(f"\n  Tasks completed: {metrics['swarm']['total_tasks_completed']}")
        print(f"  Success rate: {metrics['swarm']['avg_success_rate']:.1%}")

        return {"scenario": "basic_delegation", "metrics": metrics}

    @staticmethod
    def scenario_load_balancing() -> Dict[str, Any]:
        """Scenario 2: Load balancing with multiple agents per type.

        Shows how the orchestrator distributes tasks evenly across
        multiple agents of the same type.

        Returns:
            Scenario results.
        """
        print("\n" + "=" * 60)
        print("SCENARIO 2: Load Balancing")
        print("=" * 60)

        orch = SwarmOrchestrator(
            max_workers=20,
            selection_strategy="weighted",
            enable_load_balancing=True,
        )

        # Register multiple agents per type
        for i in range(3):
            orch.register_agent(ResearcherAgent(f"Researcher-{i+1}"))
            orch.register_agent(CoderAgent(f"Coder-{i+1}"))

        orch.start()

        # Submit many tasks to trigger load distribution
        task_types = ["research", "code"]
        for i in range(12):
            task_type = task_types[i % 2]
            orch.submit_task_simple(
                f"Bulk task {i+1}: {task_type} workload",
                task_type,
                TaskPriority.MEDIUM,
            )

        orch.wait_for_empty(timeout=15.0)
        orch.stop()

        metrics = orch.get_metrics()
        report = orch.tracker.generate_report()

        print(f"  Total tasks: {metrics['swarm']['total_tasks_submitted']}")
        print(f"  Load distribution:")
        for agent_type, load in report.get("load_distribution", {}).items():
            print(f"    {agent_type}: {load:.1%}")

        return {"scenario": "load_balancing", "metrics": metrics}

    @staticmethod
    def scenario_task_decomposition() -> Dict[str, Any]:
        """Scenario 3: Automatic task decomposition.

        Demonstrates how complex tasks are automatically broken down
        into subtasks for parallel execution.

        Returns:
            Scenario results.
        """
        print("\n" + "=" * 60)
        print("SCENARIO 3: Task Decomposition")
        print("=" * 60)

        orch = SwarmOrchestrator(
            max_workers=15,
            auto_decompose=True,
            selection_strategy="capability_then_load",
        )

        orch.register_agent(ResearcherAgent("Alice"))
        orch.register_agent(CoderAgent("Bob"))
        orch.register_agent(ReviewerAgent("Charlie"))
        orch.register_agent(WriterAgent("Diana"))
        orch.register_agent(PlannerAgent("Eve"))

        orch.start()

        # Submit complex tasks that should be decomposed
        complex_tasks = [
            "Build a complete user authentication system with login, signup, and password reset",
            "Research and analyze the competitive landscape for cloud computing platforms with detailed comparisons",
            "Create a comprehensive project plan for migrating a monolithic application to microservices architecture",
        ]

        for desc in complex_tasks:
            orch.submit_task_simple(desc, "code" if "authentication" in desc else "research", TaskPriority.HIGH)
            print(f"  Submitted complex task: {desc[:60]}...")

        orch.wait_for_empty(timeout=15.0)
        orch.stop()

        decomposer_stats = orch.decomposer.get_stats()
        print(f"\n  Decompositions performed: {decomposer_stats['total_decompositions']}")
        print(f"  Pattern hits: {decomposer_stats['pattern_hits']}")

        return {"scenario": "task_decomposition", "decomposer_stats": decomposer_stats}

    @staticmethod
    def scenario_consensus_mechanism() -> Dict[str, Any]:
        """Scenario 4: Consensus-driven decision making.

        Shows how multiple agents collaborate to reach consensus
        on critical decisions.

        Returns:
            Scenario results.
        """
        print("\n" + "=" * 60)
        print("SCENARIO 4: Consensus Mechanism")
        print("=" * 60)

        orch = SwarmOrchestrator(max_workers=10)

        orch.register_agent(ResearcherAgent("Alice"))
        orch.register_agent(CoderAgent("Bob"))
        orch.register_agent(ReviewerAgent("Charlie"))
        orch.register_agent(PlannerAgent("Diana"))

        orch.start()

        # Submit tasks requiring consensus
        from src.tasks.task import Task
        consensus_task = Task(
            description="Critical architecture decision: Should we adopt microservices?",
            task_type="plan",
            priority=TaskPriority.CRITICAL,
            consensus_required=True,
            min_consensus_votes=3,
            context={"decision_factors": ["scalability", "complexity", "team_size"]},
        )
        orch.submit_task(consensus_task)
        print(f"  Submitted consensus task: {consensus_task.description}")

        orch.wait_for_empty(timeout=15.0)
        orch.stop()

        consensus_metrics = orch.consensus.metrics
        print(f"\n  Consensus processes initiated: {consensus_metrics['initiated']}")
        print(f"  Consensus completed: {consensus_metrics['completed']}")

        return {"scenario": "consensus", "consensus_metrics": consensus_metrics}

    @staticmethod
    def scenario_retry_and_resilience() -> Dict[str, Any]:
        """Scenario 5: Retry logic and fault tolerance.

        Demonstrates how the system handles task failures with
        automatic retry and backoff.

        Returns:
            Scenario results.
        """
        print("\n" + "=" * 60)
        print("SCENARIO 5: Retry and Resilience")
        print("=" * 60)

        orch = SwarmOrchestrator(
            max_workers=10,
            retry_policy={"max_retries": 3, "backoff_factor": 2.0},
        )

        orch.register_agent(ResearcherAgent("Alice"))
        orch.register_agent(CoderAgent("Bob"))

        orch.start()

        # Submit a batch of tasks, some may fail and retry
        for i in range(5):
            orch.submit_task_simple(
                f"Resilient task {i+1}: Process data with validation",
                "research" if i % 2 == 0 else "code",
                TaskPriority.HIGH if i == 0 else TaskPriority.MEDIUM,
            )

        orch.wait_for_empty(timeout=15.0)
        orch.stop()

        metrics = orch.get_metrics()
        print(f"  Tasks completed: {metrics['swarm']['total_tasks_completed']}")
        print(f"  Tasks retried: {metrics['swarm']['total_tasks_retried']}")
        print(f"  Retry policy: {orch.retry_policy}")

        return {"scenario": "retry_resilience", "metrics": metrics}

    @staticmethod
    def scenario_full_swarm_simulation() -> Dict[str, Any]:
        """Scenario 6: Full swarm simulation with all features.

        A comprehensive simulation combining all capabilities:
        multi-agent types, decomposition, consensus, load balancing,
        and performance tracking.

        Returns:
            Scenario results.
        """
        print("\n" + "=" * 60)
        print("SCENARIO 6: Full Swarm Simulation")
        print("=" * 60)

        orch = SwarmOrchestrator(
            max_workers=25,
            auto_decompose=True,
            selection_strategy="weighted",
            enable_load_balancing=True,
            retry_policy={"max_retries": 3, "backoff_factor": 2.0},
        )

        # Register a diverse swarm
        agent_configs = [
            ("Alice", ResearcherAgent),
            ("Bob", ResearcherAgent),
            ("Carol", CoderAgent),
            ("David", CoderAgent),
            ("Eve", ReviewerAgent),
            ("Frank", ReviewerAgent),
            ("Grace", WriterAgent),
            ("Henry", WriterAgent),
            ("Ivy", PlannerAgent),
            ("Jack", PlannerAgent),
        ]

        for name, factory in agent_configs:
            orch.register_agent(factory(name))
            print(f"  Registered: {name} ({factory.__name__})")

        orch.start()

        # Submit a diverse workload
        workload = [
            ("Research emerging trends in quantum computing", "research", TaskPriority.HIGH),
            ("Implement OAuth2 authentication flow", "code", TaskPriority.HIGH),
            ("Security audit of payment processing module", "review", TaskPriority.CRITICAL),
            ("Write developer onboarding guide", "write", TaskPriority.MEDIUM),
            ("Design migration strategy from REST to GraphQL", "plan", TaskPriority.HIGH),
            ("Analyze user engagement metrics for Q3", "research", TaskPriority.MEDIUM),
            ("Refactor legacy database access layer", "code", TaskPriority.MEDIUM),
            ("Code review for authentication PR", "review", TaskPriority.HIGH),
            ("Create technical specification document", "write", TaskPriority.HIGH),
            ("Plan infrastructure scaling for holiday traffic", "plan", TaskPriority.CRITICAL),
            ("Research competitor API design patterns", "research", TaskPriority.LOW),
            ("Implement caching layer with Redis", "code", TaskPriority.MEDIUM),
        ]

        for desc, task_type, priority in workload:
            orch.submit_task_simple(desc, task_type, priority)

        print(f"\n  Submitted {len(workload)} tasks, processing...")
        orch.wait_for_empty(timeout=30.0)
        orch.stop()

        # Generate comprehensive report
        report = orch.tracker.generate_report()
        metrics = orch.get_metrics()

        print(f"\n  --- Results ---")
        print(f"  Tasks submitted: {metrics['swarm']['total_tasks_submitted']}")
        print(f"  Tasks completed: {metrics['swarm']['total_tasks_completed']}")
        print(f"  Success rate: {metrics['swarm']['avg_success_rate']:.1%}")
        print(f"  Avg latency: {metrics['swarm']['avg_task_latency_seconds']:.3f}s")

        print(f"\n  --- Top Performers ---")
        for i, perf in enumerate(report.get("top_performers", [])[:5], 1):
            print(
                f"  {i}. {perf['agent_id']} - "
                f"Success: {perf['success_rate']:.0%}, "
                f"Tasks: {perf['tasks_completed']}"
            )

        bottlenecks = report.get("bottlenecks", [])
        if bottlenecks:
            print(f"\n  --- Bottlenecks ---")
            for b in bottlenecks[:3]:
                print(f"  - {b['type']}: {b.get('recommendation', '')}")

        return {
            "scenario": "full_simulation",
            "metrics": metrics,
            "report": report,
        }

    @staticmethod
    def run_all() -> List[Dict[str, Any]]:
        """Run all demo scenarios and return results.

        Returns:
            List of scenario results.
        """
        print("\n" + "#" * 60)
        print("# AGENT SWARM DEMO - All Scenarios")
        print("#" * 60)

        results = []
        scenarios = [
            DemoScenarios.scenario_basic_delegation,
            DemoScenarios.scenario_load_balancing,
            DemoScenarios.scenario_task_decomposition,
            DemoScenarios.scenario_consensus_mechanism,
            DemoScenarios.scenario_retry_and_resilience,
            DemoScenarios.scenario_full_swarm_simulation,
        ]

        for scenario in scenarios:
            try:
                result = scenario()
                results.append(result)
            except Exception as exc:
                logger.error("scenario_failed", scenario=scenario.__name__, error=str(exc))
                results.append({
                    "scenario": scenario.__name__,
                    "error": str(exc),
                })

        print("\n" + "#" * 60)
        print("# ALL SCENARIOS COMPLETE")
        print("#" * 60)

        return results


if __name__ == "__main__":
    DemoScenarios.run_all()
