"""Planner agent specialized in strategy, scheduling, and resource management."""

from __future__ import annotations

import time
from typing import Any, Dict, List

import structlog

from src.agents.base_agent import AgentCapability, BaseAgent
from src.tasks.task import Task, TaskResult

logger = structlog.get_logger(__name__)


class PlannerAgent(BaseAgent):
    """Agent specialized in planning, strategy, and resource coordination.

    Capabilities include strategic planning, scheduling, resource management,
    dependency analysis, and workflow optimization.
    """

    def __init__(self, name: str = "Planner", config: Dict[str, Any] | None = None) -> None:
        capabilities = [
            AgentCapability("strategy", 0.95, "Develop strategic plans"),
            AgentCapability("scheduling", 0.90, "Create efficient schedules"),
            AgentCapability("resource_management", 0.85, "Allocate resources optimally"),
            AgentCapability("dependency_analysis", 0.80, "Map and resolve dependencies"),
            AgentCapability("workflow_optimization", 0.80, "Optimize process workflows"),
        ]
        super().__init__(
            name=name,
            agent_type="planner",
            capabilities=capabilities,
            max_concurrent_tasks=3,
            config=config,
        )
        self._plans_generated = 0
        self._log = logger.bind(agent_id=self.id, agent_type="planner")

    def _perform_task(self, task: Task) -> TaskResult:
        """Execute planning-oriented tasks.

        Args:
            task: A task requiring planning capabilities.

        Returns:
            Structured plan with milestones and resource allocation.
        """
        start = time.monotonic()
        self._log.info("planning_started", task_id=task.id)

        plan_type = task.context.get("plan_type", "project")
        constraints = task.context.get("constraints", {})
        resources = task.context.get("resources", [])
        timeline = task.context.get("timeline", "standard")
        dependencies = task.context.get("dependencies", [])

        plan = self._generate_plan(
            task.description, plan_type, constraints, resources, timeline, dependencies
        )
        self._plans_generated += 1

        duration = time.monotonic() - start
        milestones = plan.count("Milestone")
        self._log.info(
            "planning_completed",
            task_id=task.id,
            plan_type=plan_type,
            milestones=milestones,
        )

        return TaskResult(
            task_id=task.id,
            agent_id=self.id,
            success=True,
            output=plan,
            metadata={
                "plan_type": plan_type,
                "milestones": milestones,
                "resources_allocated": len(resources),
                "dependencies_mapped": len(dependencies),
                "plans_generated_total": self._plans_generated,
            },
            duration_seconds=duration,
        )

    def _generate_plan(
        self,
        description: str,
        plan_type: str,
        constraints: Dict[str, Any],
        resources: List[str],
        timeline: str,
        dependencies: List[str],
    ) -> str:
        """Simulate plan generation.

        Args:
            description: Plan description.
            plan_type: Type of plan.
            constraints: Budget/timeline constraints.
            resources: Available resources.
            timeline: Timeline preference.
            dependencies: Known dependencies.

        Returns:
            Formatted plan document.
        """
        phases = {
            "project": [
                ("Discovery", "Gather requirements and define scope", "1-2 weeks"),
                ("Design", "Create architecture and specifications", "2-3 weeks"),
                ("Implementation", "Build core components iteratively", "4-6 weeks"),
                ("Validation", "Test and quality assurance", "2-3 weeks"),
                ("Deployment", "Release and monitor", "1-2 weeks"),
            ],
            "sprint": [
                ("Sprint Planning", "Define sprint goals and tasks", "1 day"),
                ("Development", "Execute sprint backlog", "1-2 weeks"),
                ("Review", "Demo and stakeholder review", "1 day"),
                ("Retrospective", "Process improvement", "1 day"),
            ],
            "strategy": [
                ("Analysis", "Market and competitor analysis", "2-3 weeks"),
                ("Goal Setting", "Define OKRs and KPIs", "1 week"),
                ("Roadmap", "Create strategic roadmap", "2 weeks"),
                ("Execution Plan", "Define initiatives and owners", "1-2 weeks"),
            ],
        }

        selected_phases = phases.get(plan_type, phases["project"])

        constraint_section = "\n".join(
            f"- {k}: {v}" for k, v in constraints.items()
        ) if constraints else "- None specified"

        resource_section = "\n".join(f"- {r}" for r in resources) if resources else "- TBD"

        dep_section = "\n".join(f"- {d}" for d in dependencies) if dependencies else "- No known dependencies"

        phase_details = "\n\n".join(
            f"### Phase {i+1}: {name}\n"
            f"**Duration**: {duration}\n"
            f"**Objective**: {objective}\n"
            f"**Deliverables**: Phase {i+1} completion report\n"
            f"**Milestone**: {name} Complete"
            for i, (name, objective, duration) in enumerate(selected_phases)
        )

        return (
            f"# {plan_type.title()} Plan: {description}\n\n"
            f"**Timeline**: {timeline} | **Generated by**: PlannerAgent\n\n"
            f"---\n\n"
            f"## Constraints\n{constraint_section}\n\n"
            f"## Resources\n{resource_section}\n\n"
            f"## Dependencies\n{dep_section}\n\n"
            f"## Execution Phases\n\n"
            f"{phase_details}\n\n"
            f"---\n\n"
            f"## Risk Assessment\n"
            f"- Low: Resource availability\n"
            f"- Medium: Timeline pressure\n"
            f"- High: Scope creep\n\n"
            f"## Success Metrics\n"
            f"- All milestones delivered on schedule\n"
            f"- Resource utilization > 80%\n"
            f"- Quality score >= 8/10\n"
        )
