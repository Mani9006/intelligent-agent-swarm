"""Coder agent specialized in software development and programming tasks."""

from __future__ import annotations

import time
from typing import Any, Dict, List

import structlog

from src.agents.base_agent import AgentCapability, BaseAgent
from src.tasks.task import Task, TaskResult

logger = structlog.get_logger(__name__)


class CoderAgent(BaseAgent):
    """Agent specialized in coding, debugging, and software architecture.

    Capabilities include programming in multiple languages, code review,
    debugging, test generation, and system design.
    """

    def __init__(self, name: str = "Coder", config: Dict[str, Any] | None = None) -> None:
        capabilities = [
            AgentCapability("programming", 0.95, "Write and edit code in multiple languages"),
            AgentCapability("debugging", 0.90, "Identify and fix software defects"),
            AgentCapability("testing", 0.85, "Create and run test suites"),
            AgentCapability("architecture", 0.80, "Design software systems and patterns"),
            AgentCapability("refactoring", 0.80, "Restructure code without changing behavior"),
        ]
        super().__init__(
            name=name,
            agent_type="coder",
            capabilities=capabilities,
            max_concurrent_tasks=2,
            config=config,
        )
        self._language = config.get("language", "python") if config else "python"
        self._code_cache: Dict[str, str] = {}
        self._log = logger.bind(agent_id=self.id, agent_type="coder")

    def _perform_task(self, task: Task) -> TaskResult:
        """Execute coding-oriented tasks.

        Args:
            task: A task requiring coding capabilities.

        Returns:
            Code output or development artifacts.
        """
        start = time.monotonic()
        self._log.info("coding_started", task_id=task.id)

        language = task.context.get("language", self._language)
        code_type = task.context.get("code_type", "implementation")
        requirements = task.context.get("requirements", [])

        if code_type == "debug":
            output = self._debug_code(task.description, language)
        elif code_type == "test":
            output = self._generate_tests(task.description, language, requirements)
        elif code_type == "review":
            output = self._review_code(task.description, language)
        else:
            output = self._implement_feature(
                task.description, language, requirements
            )

        duration = time.monotonic() - start
        self._log.info("coding_completed", task_id=task.id, language=language)

        return TaskResult(
            task_id=task.id,
            agent_id=self.id,
            success=True,
            output=output,
            metadata={
                "language": language,
                "code_type": code_type,
                "requirements_count": len(requirements),
                "lines_of_code": len(output.splitlines()),
            },
            duration_seconds=duration,
        )

    def _implement_feature(
        self, description: str, language: str, requirements: List[str]
    ) -> str:
        """Simulate feature implementation.

        Args:
            description: Feature description.
            language: Target programming language.
            requirements: Functional requirements.

        Returns:
            Simulated code output.
        """
        req_lines = "\n".join(f"# - {r}" for r in requirements) if requirements else "# - No specific requirements"
        return (
            f"# Feature: {description}\n"
            f"# Language: {language}\n"
            f"# Requirements:\n{req_lines}\n\n"
            f"def implement_feature():\n"
            f'    \"\"\"Implementation of: {description}\"\"\"\n'
            f"    # TODO: Implement core logic\n"
            f"    result = process_data()\n"
            f"    return validate_output(result)\n"
            f"\n"
            f"def process_data():\n"
            f"    # Processing pipeline\n"
            f"    data = load_input()\n"
            f"    return transform(data)\n"
            f"\n"
            f"def validate_output(result):\n"
            f"    assert result is not None\n"
            f"    return result\n"
        )

    def _debug_code(self, code_snippet: str, language: str) -> str:
        """Simulate debugging session.

        Args:
            code_snippet: Code to debug.
            language: Programming language.

        Returns:
            Debug report with fixes.
        """
        return (
            f"=== Debug Report ({language}) ===\n"
            f"Analyzing: {code_snippet[:50]}...\n\n"
            f"Issues Found:\n"
            f"1. Fixed: Potential null reference\n"
            f"2. Fixed: Resource leak in cleanup\n"
            f"3. Fixed: Off-by-one in loop boundary\n"
            f"\nApplied 3 fixes. All tests passing.\n"
        )

    def _generate_tests(
        self, description: str, language: str, requirements: List[str]
    ) -> str:
        """Simulate test generation.

        Args:
            description: Feature under test.
            language: Target language.
            requirements: Requirements to cover.

        Returns:
            Generated test code.
        """
        test_cases = "\n".join(
            f"def test_req_{i}():\n    assert True  # Covers: {req}\n"
            for i, req in enumerate(requirements)
        ) if requirements else f"def test_feature():\n    assert True  # Basic smoke test\n"
        return (
            f"# Test Suite: {description}\n"
            f"# Language: {language}\n\n"
            f"import pytest\n\n"
            f"{test_cases}\n"
        )

    def _review_code(self, code_snippet: str, language: str) -> str:
        """Simulate code review.

        Args:
            code_snippet: Code to review.
            language: Programming language.

        Returns:
            Review feedback.
        """
        return (
            f"=== Code Review ({language}) ===\n"
            f"Lines reviewed: {len(code_snippet.splitlines())}\n\n"
            f"Score: 8.5/10\n"
            f"Suggestions:\n"
            f"- Add type hints for better readability\n"
            f"- Extract magic numbers to constants\n"
            f"- Consider early returns to reduce nesting\n"
            f"- Add docstrings for public methods\n"
        )
