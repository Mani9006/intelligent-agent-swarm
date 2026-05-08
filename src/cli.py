"""Command-line interface for the Agent Swarm system."""

from __future__ import annotations

import json
import sys
import time
from typing import Optional

import click
import structlog
from rich.console import Console
from rich.json import JSON
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.agents.coder import CoderAgent
from src.agents.planner import PlannerAgent
from src.agents.researcher import ResearcherAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.writer import WriterAgent
from src.orchestrator import SwarmOrchestrator
from src.tasks.task import TaskPriority

console = Console()
logger = structlog.get_logger(__name__)


def _create_default_orchestrator() -> SwarmOrchestrator:
    """Create an orchestrator with a full agent complement."""
    orch = SwarmOrchestrator()

    # Register agents of each type
    orch.register_agent(ResearcherAgent("Alice"))
    orch.register_agent(ResearcherAgent("Bob"))
    orch.register_agent(CoderAgent("Carol"))
    orch.register_agent(CoderAgent("David"))
    orch.register_agent(ReviewerAgent("Eve"))
    orch.register_agent(ReviewerAgent("Frank"))
    orch.register_agent(WriterAgent("Grace"))
    orch.register_agent(WriterAgent("Henry"))
    orch.register_agent(PlannerAgent("Ivy"))
    orch.register_agent(PlannerAgent("Jack"))

    return orch


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Agent Swarm Task Delegation System."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    if verbose:
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(10),
        )


@cli.command()
@click.option("--agents", default=2, help="Number of agents per type")
@click.option("--tasks", default=10, help="Number of tasks to generate")
@click.option("--strategy", default="weighted", help="Agent selection strategy")
@click.option("--duration", default=5.0, help="Simulation duration in seconds")
@click.option("--report", is_flag=True, help="Show final performance report")
@click.pass_context
def simulate(
    ctx: click.Context,
    agents: int,
    tasks: int,
    strategy: str,
    duration: float,
    report: bool,
) -> None:
    """Run a swarm simulation with generated tasks."""
    console.print(
        Panel(
            Text("Agent Swarm Simulation", style="bold cyan"),
            subtitle=f"{agents} agents/type, {tasks} tasks, {strategy} strategy",
        )
    )

    orch = SwarmOrchestrator(
        max_workers=20,
        selection_strategy=strategy,
    )

    # Register agents
    agent_factories = [
        ("Researcher", ResearcherAgent),
        ("Coder", CoderAgent),
        ("Reviewer", ReviewerAgent),
        ("Writer", WriterAgent),
        ("Planner", PlannerAgent),
    ]

    for name_prefix, factory in agent_factories:
        for i in range(agents):
            orch.register_agent(factory(f"{name_prefix}-{i+1}"))

    console.print(f"[green]Registered {len(agent_factories) * agents} agents[/green]")

    # Submit tasks
    task_templates = [
        ("Research market trends in AI adoption", "research", TaskPriority.HIGH),
        ("Implement user authentication module", "code", TaskPriority.HIGH),
        ("Review pull request #42 for security issues", "review", TaskPriority.MEDIUM),
        ("Write API documentation for v2 endpoints", "write", TaskPriority.MEDIUM),
        ("Create sprint plan for Q4 deliverables", "plan", TaskPriority.HIGH),
        ("Analyze performance bottleneck in data pipeline", "analysis", TaskPriority.CRITICAL),
        ("Debug memory leak in production service", "code", TaskPriority.CRITICAL),
        ("Write technical blog post on microservices", "write", TaskPriority.LOW),
        ("Review architecture proposal for new service", "review", TaskPriority.HIGH),
        ("Research competitor pricing strategies", "research", TaskPriority.MEDIUM),
    ]

    for i in range(tasks):
        template = task_templates[i % len(task_templates)]
        orch.submit_task_simple(
            description=f"{template[0]} (task-{i+1})",
            task_type=template[1],
            priority=template[2],
        )

    console.print(f"[green]Submitted {tasks} tasks[/green]")

    # Start and run
    orch.start()
    console.print("[yellow]Running simulation...[/yellow]")

    start = time.monotonic()
    with Live(console=console, refresh_per_second=2) as live:
        while time.monotonic() - start < duration:
            metrics = orch.get_metrics()

            # Build status table
            table = Table(title="Swarm Status")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            swarm = metrics.get("swarm", {})
            table.add_row("Tasks Completed", str(swarm.get("total_tasks_completed", 0)))
            table.add_row("Tasks Failed", str(swarm.get("total_tasks_failed", 0)))
            table.add_row("Success Rate", f"{swarm.get('avg_success_rate', 0):.1%}")
            table.add_row("Queue Size", str(metrics.get("queue", {}).get("size", 0)))
            table.add_row(
                "Active Agents",
                str(metrics.get("registry", {}).get("health", {}).get("available", 0)),
            )
            table.add_row(
                "Avg Load",
                f"{swarm.get('avg_system_load', 0):.1%}",
            )

            live.update(table)
            time.sleep(0.5)

    # Wait for queue to drain
    orch.wait_for_empty(timeout=10.0)
    orch.stop()

    console.print("[bold green]Simulation complete![/bold green]")

    # Final report
    if report:
        metrics = orch.get_metrics()
        console.print("\n[bold]Final Metrics:[/bold]")
        console.print(JSON(json.dumps(metrics, indent=2, default=str)))

    # Performance report
    report_data = orch.tracker.generate_report()
    console.print("\n[bold]Top Performers:[/bold]")
    for i, perf in enumerate(report_data.get("top_performers", []), 1):
        console.print(
            f"  {i}. {perf['agent_id']} ({perf['agent_type']}) - "
            f"Success: {perf['success_rate']:.1%}, "
            f"Throughput: {perf['throughput_per_minute']:.1f}/min"
        )

    bottlenecks = report_data.get("bottlenecks", [])
    if bottlenecks:
        console.print("\n[bold red]Bottlenecks:[/bold red]")
        for b in bottlenecks:
            console.print(f"  - {b['type']}: {b.get('recommendation', '')}")


@cli.command()
@click.option("--port", default=8080, help="API port (placeholder)")
def serve(port: int) -> None:
    """Start the swarm API server (placeholder)."""
    console.print(f"[yellow]API server mode is a placeholder (port {port})[/yellow]")
    console.print("Use 'simulate' command to run the swarm interactively.")


@cli.command()
def status() -> None:
    """Show current swarm status (placeholder)."""
    console.print("[yellow]No active swarm. Use 'simulate' to start one.[/yellow]")


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
