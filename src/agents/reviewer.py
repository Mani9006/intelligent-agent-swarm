"""Reviewer agent specialized in quality assurance and critical analysis."""

from __future__ import annotations

import time
from typing import Any, Dict

import structlog

from src.agents.base_agent import AgentCapability, BaseAgent
from src.tasks.task import Task, TaskResult

logger = structlog.get_logger(__name__)


class ReviewerAgent(BaseAgent):
    """Agent specialized in quality assurance, review, and critical analysis.

    Capabilities include code review, document review, quality checks,
    compliance verification, and critical assessment of deliverables.
    """

    def __init__(self, name: str = "Reviewer", config: Dict[str, Any] | None = None) -> None:
        capabilities = [
            AgentCapability("quality_assurance", 0.95, "Verify quality standards"),
            AgentCapability("analysis", 0.90, "Critical analysis of deliverables"),
            AgentCapability("documentation", 0.85, "Review documentation quality"),
            AgentCapability("compliance", 0.80, "Check compliance with standards"),
            AgentCapability("fact_checking", 0.80, "Verify factual accuracy"),
        ]
        super().__init__(
            name=name,
            agent_type="reviewer",
            capabilities=capabilities,
            max_concurrent_tasks=3,
            config=config,
        )
        self._review_history: list[Dict[str, Any]] = []
        self._log = logger.bind(agent_id=self.id, agent_type="reviewer")

    def _perform_task(self, task: Task) -> TaskResult:
        """Execute review-oriented tasks.

        Args:
            task: A task requiring review capabilities.

        Returns:
            Review report with findings and recommendations.
        """
        start = time.monotonic()
        self._log.info("review_started", task_id=task.id)

        review_type = task.context.get("review_type", "general")
        target = task.context.get("target", task.description)
        criteria = task.context.get("criteria", [])
        severity_threshold = task.context.get("severity_threshold", "medium")

        review_report = self._conduct_review(
            target, review_type, criteria, severity_threshold
        )

        self._review_history.append({
            "task_id": task.id,
            "review_type": review_type,
            "timestamp": time.time(),
        })

        duration = time.monotonic() - start
        issues_found = review_report.count("- Issue:")
        self._log.info(
            "review_completed",
            task_id=task.id,
            issues_found=issues_found,
            review_type=review_type,
        )

        return TaskResult(
            task_id=task.id,
            agent_id=self.id,
            success=True,
            output=review_report,
            metadata={
                "review_type": review_type,
                "issues_found": issues_found,
                "severity_threshold": severity_threshold,
                "criteria_checked": len(criteria),
                "total_reviews": len(self._review_history),
            },
            duration_seconds=duration,
        )

    def _conduct_review(
        self,
        target: str,
        review_type: str,
        criteria: list[str],
        severity_threshold: str,
    ) -> str:
        """Simulate a quality review process.

        Args:
            target: The item under review.
            review_type: Category of review.
            criteria: Checklist criteria.
            severity_threshold: Minimum severity to report.

        Returns:
            Formatted review report.
        """
        severity_levels = {"critical": 1, "high": 2, "medium": 3, "low": 4}
        threshold_level = severity_levels.get(severity_threshold, 3)

        criteria_section = "\n".join(
            f"  [{i+1}] {c}: PASS" for i, c in enumerate(criteria)
        ) if criteria else "  No specific criteria provided.\n  General review applied."

        issues = [
            "- Issue: Inconsistent naming convention (Severity: medium)",
            "- Issue: Missing edge case handling (Severity: medium)",
            "- Issue: Documentation could be more detailed (Severity: low)",
            "- Issue: Consider adding input validation (Severity: high)",
        ]
        filtered_issues = [
            issue for issue in issues
            if severity_levels.get(
                issue.split("Severity: ")[-1].rstrip(")"), 4
            ) <= threshold_level
        ]
        issues_section = "\n".join(filtered_issues) if filtered_issues else "No issues found."

        score = max(0, 10 - len(filtered_issues) * 0.5)

        return (
            f"=== {review_type.upper()} Review Report ===\n"
            f"Target: {target}\n"
            f"Severity Threshold: {severity_threshold}\n"
            f"Overall Score: {score:.1f}/10\n\n"
            f"Criteria Checklist:\n{criteria_section}\n\n"
            f"Findings:\n{issues_section}\n\n"
            f"Recommendations:\n"
            f"1. Address all high-severity findings before merge\n"
            f"2. Add automated checks to prevent regressions\n"
            f"3. Consider peer review for complex changes\n\n"
            f"Status: {'APPROVED' if score >= 8 else 'CHANGES_REQUESTED'}\n"
        )
