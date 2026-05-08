"""Tests for the task decomposer."""

from __future__ import annotations

import pytest

from src.task_decomposer import TaskDecomposer
from src.tasks.task import Task, TaskPriority, TaskStatus


class TestTaskDecomposer:
    """Test suite for the TaskDecomposer."""

    def test_create_decomposer(self) -> None:
        """Test creating a decomposer."""
        decomposer = TaskDecomposer()
        stats = decomposer.get_stats()
        assert stats["total_decompositions"] == 0

    def test_should_decompose_complex_task(self) -> None:
        """Test that complex tasks are flagged for decomposition."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Create a comprehensive plan with multiple phases and then execute it",
            task_type="plan",
            priority=TaskPriority.HIGH,
        )
        assert decomposer.should_decompose(task) is True

    def test_should_decompose_by_type(self) -> None:
        """Test decomposition by task type."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Write documentation",
            task_type="write",
            priority=TaskPriority.MEDIUM,
        )
        assert decomposer.should_decompose(task) is True

    def test_should_not_decompose_simple(self) -> None:
        """Test that simple tasks are not decomposed."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Simple task",
            task_type="general",
            priority=TaskPriority.LOW,
        )
        assert decomposer.should_decompose(task) is False

    def test_should_decompose_by_length(self) -> None:
        """Test that long descriptions trigger decomposition."""
        decomposer = TaskDecomposer()

        task = Task(
            description="This is a very long description that exceeds the "
                       "one hundred and fifty character threshold for automatic "
                       "decomposition into smaller subtasks for better management",
            task_type="general",
            priority=TaskPriority.MEDIUM,
        )
        assert decomposer.should_decompose(task) is True

    def test_should_decompose_forced(self) -> None:
        """Test forced decomposition via context."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Simple task",
            task_type="general",
            priority=TaskPriority.MEDIUM,
            context={"force_decompose": True},
        )
        assert decomposer.should_decompose(task) is True

    def test_decompose_task(self) -> None:
        """Test task decomposition."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Create project plan",
            task_type="plan",
            priority=TaskPriority.HIGH,
        )
        subtasks = decomposer.decompose(task)

        assert len(subtasks) >= 2
        assert all(st.parent_task_id == task.id for st in subtasks)
        assert len(task.subtask_ids) == len(subtasks)

    def test_decompose_code_task(self) -> None:
        """Test code task decomposition."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Build authentication system",
            task_type="code",
            priority=TaskPriority.HIGH,
        )
        subtasks = decomposer.decompose(task)

        assert len(subtasks) >= 3
        types = [st.task_type for st in subtasks]
        assert "design" in types or "implementation" in types

    def test_decompose_research_task(self) -> None:
        """Test research task decomposition."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Research market trends",
            task_type="research",
            priority=TaskPriority.MEDIUM,
        )
        subtasks = decomposer.decompose(task)

        assert len(subtasks) >= 3
        types = [st.task_type for st in subtasks]
        assert "analysis" in types

    def test_decompose_with_explicit_subtasks(self) -> None:
        """Test decomposition with explicit subtask definitions."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Parent task",
            task_type="code",
            priority=TaskPriority.HIGH,
            context={
                "subtasks": [
                    {
                        "description": "Subtask 1",
                        "task_type": "code",
                        "priority": "MEDIUM",
                    },
                    {
                        "description": "Subtask 2",
                        "task_type": "test",
                        "priority": "MEDIUM",
                    },
                ]
            },
        )
        subtasks = decomposer.decompose(task)

        assert len(subtasks) == 2
        assert subtasks[0].description == "Subtask 1"
        assert subtasks[1].description == "Subtask 2"

    def test_decompose_stats_updated(self) -> None:
        """Test that decomposition stats are updated."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Plan the sprint",
            task_type="plan",
            priority=TaskPriority.HIGH,
        )
        decomposer.decompose(task)

        stats = decomposer.get_stats()
        assert stats["total_decompositions"] == 1
        assert "plan" in stats["pattern_hits"]

    def test_add_custom_pattern(self) -> None:
        """Test adding custom decomposition patterns."""
        decomposer = TaskDecomposer()
        decomposer.add_decomposition_pattern(
            "custom_type",
            [
                ("phase_1", "First phase"),
                ("phase_2", "Second phase"),
            ],
        )

        task = Task(
            description="Custom task",
            task_type="custom_type",
            priority=TaskPriority.MEDIUM,
        )
        subtasks = decomposer.decompose(task)

        assert len(subtasks) == 2
        assert subtasks[0].task_type == "phase_1"
        assert subtasks[1].task_type == "phase_2"

    def test_subtask_capability_inference(self) -> None:
        """Test that subtasks get appropriate capabilities."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Code review",
            task_type="code",
            priority=TaskPriority.HIGH,
        )
        subtasks = decomposer.decompose(task)

        for st in subtasks:
            assert len(st.required_capabilities) > 0
            assert st.required_capabilities != ["general"]

    def test_fallback_pattern(self) -> None:
        """Test fallback for unknown task types."""
        decomposer = TaskDecomposer()

        task = Task(
            description="Unknown task type work",
            task_type="nonexistent_type",
            priority=TaskPriority.MEDIUM,
        )
        subtasks = decomposer.decompose(task)

        assert len(subtasks) == 3  # analysis, execution, validation
