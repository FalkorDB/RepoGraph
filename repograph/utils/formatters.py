"""Rich-based terminal output formatters for RepoGraph."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from repograph.core.queries import (
    BlastRadiusResult,
    BusFactorResult,
    CouplingResult,
    DeveloperOverlap,
    KnowledgeSiloResult,
    ReviewerResult,
    RiskResult,
)

console = Console()


def format_bus_factor(results: list[BusFactorResult]) -> None:
    """Display bus factor results as a Rich table."""
    if not results:
        console.print("[yellow]No bus factor data found. Run 'repograph seed' or 'repograph analyze' first.[/]")
        return

    table = Table(title="🚌 Bus Factor Report", show_lines=True)
    table.add_column("Module", style="cyan", min_width=20)
    table.add_column("Bus Factor", justify="center", min_width=12)
    table.add_column("Files", justify="center")
    table.add_column("Top Experts", style="green", min_width=30)

    for r in results:
        # Color the bus factor based on risk
        if r.bus_factor <= 1:
            bf_style = "bold red"
            bf_icon = "🔴"
        elif r.bus_factor <= 2:
            bf_style = "bold yellow"
            bf_icon = "🟡"
        else:
            bf_style = "bold green"
            bf_icon = "🟢"

        bf_text = Text(f"{bf_icon} {r.bus_factor}", style=bf_style)
        experts_str = ", ".join(
            f"{e['name']} ({e.get('score', 0):.1f})" for e in r.experts[:3]
        ) if r.experts else "None"

        table.add_row(r.module, bf_text, str(r.file_count), experts_str)

    console.print(table)


def format_blast_radius(result: BlastRadiusResult) -> None:
    """Display blast radius results."""
    console.print(
        Panel(
            f"[bold]Blast radius for:[/] [cyan]{result.source_file}[/]",
            title="💥 Blast Radius Analysis",
        )
    )

    if not result.affected_files:
        console.print("[yellow]No co-change relationships found for this file.[/]")
        return

    table = Table(show_lines=False)
    table.add_column("File", style="cyan", min_width=30)
    table.add_column("Distance", justify="center")
    table.add_column("Risk", justify="center")

    for af in result.affected_files:
        dist = af["distance"]
        if dist == 1:
            risk = "[red]Direct[/]"
        elif dist == 2:
            risk = "[yellow]Indirect[/]"
        else:
            risk = "[dim]Transitive[/]"
        table.add_row(str(af["path"]), str(dist), risk)

    console.print(table)
    console.print(f"\n[bold]Affected modules:[/] {', '.join(result.affected_modules) or 'None'}")
    console.print(f"[bold]Total affected files:[/] {len(result.affected_files)}")


def format_reviewers(file_path: str, reviewers: list[ReviewerResult]) -> None:
    """Display recommended reviewers."""
    console.print(
        Panel(
            f"[bold]Recommended reviewers for:[/] [cyan]{file_path}[/]",
            title="👀 Reviewer Suggestions",
        )
    )

    if not reviewers:
        console.print("[yellow]No reviewers found for this file.[/]")
        return

    table = Table(show_lines=False)
    table.add_column("#", justify="center", width=3)
    table.add_column("Developer", style="green", min_width=20)
    table.add_column("Email", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Commits", justify="center")

    for i, r in enumerate(reviewers, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, " ")
        table.add_row(medal, r.name, r.email, f"{r.score:.2f}", str(r.commit_count))

    console.print(table)


def format_silos(results: list[KnowledgeSiloResult]) -> None:
    """Display knowledge silo results."""
    if not results:
        console.print("[green]✅ No knowledge silos detected. Your team has good coverage![/]")
        return

    table = Table(title="🏝️  Knowledge Silos", show_lines=True)
    table.add_column("Module", style="cyan", min_width=20)
    table.add_column("Risk", justify="center")
    table.add_column("Experts", justify="center")
    table.add_column("Files", justify="center")
    table.add_column("Known By", style="green")

    for r in results:
        if r.risk_level == "critical":
            risk_text = Text("🔴 CRITICAL", style="bold red")
        else:
            risk_text = Text("🟡 WARNING", style="bold yellow")

        table.add_row(
            r.module,
            risk_text,
            str(r.expert_count),
            str(r.file_count),
            ", ".join(r.experts) if r.experts else "Nobody!",
        )

    console.print(table)


def format_coupling(results: list[CouplingResult]) -> None:
    """Display module coupling results."""
    if not results:
        console.print("[green]✅ No significant cross-module coupling detected.[/]")
        return

    table = Table(title="🔗 Module Coupling", show_lines=True)
    table.add_column("Module A", style="cyan")
    table.add_column("Module B", style="cyan")
    table.add_column("Coupling Strength", justify="center")
    table.add_column("Shared Files", justify="center")

    for r in results:
        strength_style = "bold red" if r.coupling_strength >= 10 else "yellow"
        table.add_row(
            r.module_a,
            r.module_b,
            Text(str(r.coupling_strength), style=strength_style),
            str(r.shared_files),
        )

    console.print(table)


def format_risks(results: list[RiskResult]) -> None:
    """Display risk hotspot results."""
    if not results:
        console.print("[green]✅ No high-risk hotspots detected.[/]")
        return

    table = Table(title="⚠️  Risk Hotspots", show_lines=True)
    table.add_column("Module", style="cyan", min_width=20)
    table.add_column("Bus Factor", justify="center")
    table.add_column("Changes", justify="center")
    table.add_column("Risk Score", justify="center")
    table.add_column("Level", justify="center")

    for r in results:
        level_map = {
            "critical": Text("🔴 CRITICAL", style="bold red"),
            "high": Text("🟠 HIGH", style="bold yellow"),
            "medium": Text("🟡 MEDIUM", style="yellow"),
            "low": Text("🟢 LOW", style="green"),
        }
        table.add_row(
            r.module,
            str(r.bus_factor),
            str(r.change_frequency),
            f"{r.risk_score:.1f}",
            level_map.get(r.risk_level, Text(r.risk_level)),
        )

    console.print(table)


def format_developer_overlap(results: list[DeveloperOverlap]) -> None:
    """Display developer knowledge overlap."""
    if not results:
        console.print("[yellow]No significant developer overlap found.[/]")
        return

    table = Table(title="👥 Developer Knowledge Overlap", show_lines=False)
    table.add_column("Developer A", style="green")
    table.add_column("Developer B", style="green")
    table.add_column("Shared Files", justify="center")

    for r in results:
        table.add_row(r.dev_a, r.dev_b, str(r.shared_files))

    console.print(table)


def format_summary(summary: dict) -> None:
    """Display graph summary."""
    console.print(
        Panel(
            f"[bold]Developers:[/] {summary.get('developers', 0)}\n"
            f"[bold]Files:[/] {summary.get('files', 0)}\n"
            f"[bold]Modules:[/] {summary.get('modules', 0)}\n"
            f"[bold]Commits:[/] {summary.get('commits', 0)}",
            title="📊 Graph Summary",
            border_style="blue",
        )
    )
