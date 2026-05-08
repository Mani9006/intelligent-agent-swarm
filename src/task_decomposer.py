"""Task decomposition engine for breaking complex tasks into subtasks."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import structlog

from src.tasks.task import Task, TaskPriority, TaskStatus

logger = structlog.get_logger(__name__)


class TaskDecomposer:
    """Decomposes complex tasks into manageable subtasks.

    Analyzes task descriptions and context to identify natural break points,
    dependency relationships, and optimal division strategies.
    """

    DECOMPOSITION_PATTERNS = {
        "research": [
            ("literature_review", "Review existing literature and prior work"),
            ("data_collection", "Gather relevant data and sources"),
            ("analysis", "Analyze collected information"),
            ("synthesis", "Synthesize findings into conclusions"),
        ],
        "code": [
            ("design", "Design solution architecture"),
            ("implementation", "Implement core functionality"),
            ("testing", "Write and run tests"),
            ("documentation", "Document the implementation"),
        ],
        "review": [
            ("preliminary_scan", "Perform initial quality scan"),
            ("detailed_review", "Conduct detailed line-by-line review"),
            ("compliance_check", "Verify compliance with standards"),
            ("feedback", "Compile review feedback"),
        ],
        "write": [
            ("outline", "Create content outline and structure"),
            ("draft", "Write initial draft"),
            ("review_draft", "Review and refine the draft"),
            ("finalize", "Finalize and polish content"),
        ],
        "plan": [
            ("goal_analysis", "Analyze goals and constraints"),
            ("strategy", "Develop strategy and approach"),
            ("scheduling", "Create timeline and milestones"),
            ("resource_allocation", "Allocate resources and assign owners"),
        ],
        "analysis": [
            ("data_exploration", "Explore and understand the data"),
            ("modeling", "Apply analytical models"),
            ("validation", "Validate results and assumptions"),
            ("reporting", "Create analysis report"),
        ],
    }

    COMPOUND_INDICATORS = [
        "and then", "followed by", "after that", "subsequently",
        "first.*then", "phase", "stage", "step by step", "multi-step",
        "comprehensive", "end-to-end", "full", "complete",
    ]

    def __init__(self) -> None:
        self._decomposition_count = 0
        self._pattern_hits: Dict[str, int] = {}
        self._log = logger

    def should_decompose(self, task: Task) -> bool:
        """Determine if a task should be decomposed.

        Uses heuristics based on description length, complexity indicators,
        and task type patterns.

        Args:
            task: The task to evaluate.

        Returns:
            True if decomposition is recommended.
        """
        desc_lower = task.description.lower()

        # Check compound indicators
        for indicator in self.COMPOUND_INDICATORS:
            if re.search(indicator, desc_lower):
                return True

        # Decompose based on task type and context
        if task.context.get("force_decompose", False):
            return True

        if task.task_type.lower() in self.DECOMPOSITION_PATTERNS:
            return True

        # Long descriptions likely need splitting
        if len(task.description) > 150:
            return True

        # Multiple explicit sub-tasks in context
        if task.context.get("subtasks"):
            return True

        return False

    def decompose(self, task: Task) -> List[Task]:
        """Break a task into subtasks.

        Args:
            task: The parent task to decompose.

        Returns:
            List of subtask objects.
        """
        self._log.info("decomposing_task", task_id=task.id, task_type=task.task_type)

        # Check for explicit subtasks in context
        if task.context.get("subtasks"):
            subtasks = self._create_from_explicit(task)
        else:
            subtasks = self._create_from_pattern(task)

        # Link subtasks to parent
        for sub in subtasks:
            sub.parent_task_id = task.id
            task.add_subtask(sub.id)

        task.status = TaskStatus.DECOMPOSING
        self._decomposition_count += 1
        self._pattern_hits[task.task_type] = (
            self._pattern_hits.get(task.task_type, 0) + 1
        )

        self._log.info(
            "decomposition_complete",
            task_id=task.id,
            subtask_count=len(subtasks),
        )
        return subtasks

    def _create_from_explicit(self, task: Task) -> List[Task]:
        """Create subtasks from explicitly defined subtask list.

        Args:
            task: Parent task with subtasks in context.

        Returns:
            List of subtask objects.
        """
        subtasks_data = task.context.get("subtasks", [])
        results = []

        for i, sub_data in enumerate(subtasks_data):
            priority_name = sub_data.get("priority", task.priority.name)
            subtask = Task(
                description=sub_data.get("description", f"Subtask {i+1}"),
                task_type=sub_data.get("task_type", task.task_type),
                priority=TaskPriority[priority_name]
                if isinstance(priority_name, str)
                else priority_name,
                required_capabilities=sub_data.get(
                    "required_capabilities",
                    task.required_capabilities,
                ),
                context=sub_data.get("context", {}),
                consensus_required=sub_data.get(
                    "consensus_required", task.consensus_required
                ),
                max_retries=task.max_retries,
            )
            results.append(subtask)

        return results

    def _create_from_pattern(self, task: Task) -> List[Task]:
        """Create subtasks using decomposition patterns.

        Args:
            task: Parent task to decompose.

        Returns:
            List of subtask objects.
        """
        task_type = task.task_type.lower()
        patterns = self.DECOMPOSITION_PATTERNS.get(task_type, [])

        if not patterns:
            # Generic fallback: split into analysis, execution, validation
            patterns = [
                ("analysis", f"Analyze requirements for: {task.description}"),
                ("execution", f"Execute: {task.description}"),
                ("validation", f"Validate results for: {task.description}"),
            ]

        # Adjust priority: parent task priority propagates with slight variation
        priority_order = list(TaskPriority)
        parent_idx = priority_order.index(task.priority)

        subtasks = []
        for i, (sub_type, sub_desc) in enumerate(patterns):
            # First subtask gets parent priority, others may be lower
            sub_priority = (
                task.priority
                if i == 0
                else priority_order[min(parent_idx + 1, len(priority_order) - 1)]
            )

            subtask = Task(
                description=sub_desc,
                task_type=sub_type,
                priority=sub_priority,
                parent_task_id=task.id,
                required_capabilities=self._infer_subtask_capabilities(sub_type),
                context={
                    **task.context,
                    "phase": i + 1,
                    "total_phases": len(patterns),
                },
                consensus_required=task.consensus_required,
                max_retries=task.max_retries,
            )
            subtasks.append(subtask)

        return subtasks

    def _infer_subtask_capabilities(self, subtask_type: str) -> List[str]:
        """Infer required capabilities for a subtask type.

        Args:
            subtask_type: The subtask category.

        Returns:
            List of capability names.
        """
        capability_map = {
            "literature_review": ["information_retrieval", "analysis"],
            "data_collection": ["information_retrieval", "data_analysis"],
            "analysis": ["analysis", "data_analysis"],
            "synthesis": ["analysis", "communication"],
            "design": ["architecture", "programming"],
            "implementation": ["programming", "debugging"],
            "testing": ["testing", "qa"],
            "documentation": ["documentation", "communication"],
            "preliminary_scan": ["quality_assurance", "analysis"],
            "detailed_review": ["quality_assurance", "analysis"],
            "compliance_check": ["compliance", "quality_assurance"],
            "feedback": ["communication", "documentation"],
            "outline": ["content_creation", "strategy"],
            "draft": ["content_creation", "writing"],
            "review_draft": ["editing", "quality_assurance"],
            "finalize": ["editing", "content_creation"],
            "goal_analysis": ["analysis", "strategy"],
            "strategy": ["strategy", "planning"],
            "scheduling": ["scheduling", "resource_management"],
            "resource_allocation": ["resource_management", "scheduling"],
            "data_exploration": ["data_analysis", "analysis"],
            "modeling": ["data_analysis", "programming"],
            "validation": ["quality_assurance", "testing"],
            "reporting": ["documentation", "content_creation"],
        }
        return capability_map.get(subtask_type, ["general"])

    def get_stats(self) -> Dict[str, Any]:
        """Return decomposition statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "total_decompositions": self._decomposition_count,
            "pattern_hits": self._pattern_hits.copy(),
            "available_patterns": list(self.DECOMPOSITION_PATTERNS.keys()),
        }

    def add_decomposition_pattern(
        self, task_type: str, phases: List[tuple[str, str]]
    ) -> None:
        """Register a custom decomposition pattern.

        Args:
            task_type: The task type to match.
            phases: List of (subtask_type, description) tuples.
        """
        self.DECOMPOSITION_PATTERNS[task_type.lower()] = phases
        self._log.info("pattern_added", task_type=task_type, phases=len(phases))
