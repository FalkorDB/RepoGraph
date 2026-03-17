"""RepoGraph CLI — command-line interface for repository graph analysis."""

from __future__ import annotations

import logging
import sys

import click
from rich.console import Console

from repograph.core.config import AppConfig, FalkorDBConfig
from repograph.core.database import ConnectionError, DatabaseManager
from repograph.core.queries import (
    query_blast_radius,
    query_bus_factor,
    query_developer_overlap,
    query_graph_summary,
    query_knowledge_silos,
    query_module_coupling,
    query_reviewers,
    query_risk_hotspots,
)
from repograph.core.schema import setup_schema
from repograph.utils.formatters import (
    format_blast_radius,
    format_bus_factor,
    format_coupling,
    format_developer_overlap,
    format_reviewers,
    format_risks,
    format_silos,
    format_summary,
)

console = Console()
logger = logging.getLogger("repograph")


def _setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _get_db(host: str, port: int, graph: str) -> DatabaseManager:
    """Create and connect to the database."""
    config = FalkorDBConfig(host=host, port=port, graph_name=graph)
    db = DatabaseManager(config)
    try:
        db.connect()
    except ConnectionError as e:
        console.print(f"[bold red]Error:[/] {e}")
        console.print("[dim]Is FalkorDB running? Try: docker-compose up -d falkordb[/]")
        sys.exit(1)
    return db


@click.group()
@click.option("--host", default="localhost", envvar="FALKORDB_HOST", help="FalkorDB host")
@click.option("--port", default=6379, envvar="FALKORDB_PORT", type=int, help="FalkorDB port")
@click.option("--graph", default="repograph", envvar="REPOGRAPH_GRAPH_NAME", help="Graph name")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.version_option(version="0.1.0", prog_name="repograph")
@click.pass_context
def cli(ctx: click.Context, host: str, port: int, graph: str, verbose: bool) -> None:
    """RepoGraph — Git repository intelligence powered by graph analysis.

    Analyze your git repository to discover knowledge silos, bus factors,
    implicit module coupling, and code review recommendations.
    """
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["host"] = host
    ctx.obj["port"] = port
    ctx.obj["graph"] = graph


@cli.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--max-commits", default=5000, type=int, help="Maximum commits to analyze")
@click.option("--clear", is_flag=True, help="Clear existing graph before analyzing")
@click.pass_context
def analyze(ctx: click.Context, repo_path: str, max_commits: int, clear: bool) -> None:
    """Analyze a git repository and build the knowledge graph.

    REPO_PATH is the path to the git repository to analyze.
    """
    from repograph.core.config import AnalysisConfig
    from repograph.core.git_analyzer import analyze_repository
    from repograph.core.graph_builder import build_graph

    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])

    try:
        if clear:
            console.print("[yellow]Clearing existing graph...[/]")
            db.clear_graph()

        setup_schema(db)

        console.print(f"[bold]Analyzing repository:[/] {repo_path}")
        with console.status("[bold green]Parsing git history..."):
            analysis_config = AnalysisConfig(max_commits=max_commits)
            result = analyze_repository(repo_path, analysis_config)

        console.print(
            f"  Found [bold]{result.total_commits_scanned}[/] commits, "
            f"[bold]{len(result.developers)}[/] developers, "
            f"[bold]{len(result.files)}[/] files"
        )

        with console.status("[bold green]Building knowledge graph..."):
            stats = build_graph(db, result, analysis_config)

        console.print("[bold green]✅ Graph built successfully![/]")
        format_summary(query_graph_summary(db))

    except ValueError as e:
        console.print(f"[bold red]Error:[/] {e}")
        sys.exit(1)
    finally:
        db.close()


@cli.command()
@click.option("--commits", default=300, type=int, help="Number of seed commits")
@click.option("--clear", is_flag=True, default=True, help="Clear graph before seeding")
@click.pass_context
def seed(ctx: click.Context, commits: int, clear: bool) -> None:
    """Load demo data for testing and exploration."""
    from repograph.core.seed import generate_seed_data

    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])

    try:
        if clear:
            console.print("[yellow]Clearing existing graph...[/]")
            db.clear_graph()

        setup_schema(db)

        with console.status("[bold green]Generating seed data..."):
            stats = generate_seed_data(db, num_commits=commits)

        console.print("[bold green]✅ Seed data loaded![/]")
        format_summary(query_graph_summary(db))

    finally:
        db.close()


@cli.command("bus-factor")
@click.option("--module", "-m", default=None, help="Filter by module path")
@click.option("--min-score", default=0.5, type=float, help="Minimum knowledge score threshold")
@click.pass_context
def bus_factor(ctx: click.Context, module: str | None, min_score: float) -> None:
    """Show bus factor analysis per module.

    Bus factor = number of developers with meaningful expertise in a module.
    A bus factor of 1 means if that person leaves, the module has no expert.
    """
    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])
    try:
        results = query_bus_factor(db, module=module, min_score=min_score)
        format_bus_factor(results)
    finally:
        db.close()


@cli.command("blast-radius")
@click.argument("file_path")
@click.option("--depth", "-d", default=3, type=int, help="Maximum traversal depth (1-5)")
@click.pass_context
def blast_radius(ctx: click.Context, file_path: str, depth: int) -> None:
    """Show the blast radius of changing a file.

    Traces co-change relationships to find all files that are typically
    modified together, up to N hops away.

    FILE_PATH is the path of the file to analyze.
    """
    if depth < 1 or depth > 5:
        console.print("[bold red]Error:[/] Depth must be between 1 and 5")
        sys.exit(1)

    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])
    try:
        result = query_blast_radius(db, file_path=file_path, max_depth=depth)
        format_blast_radius(result)
    finally:
        db.close()


@cli.command()
@click.argument("file_path")
@click.option("--limit", "-n", default=5, type=int, help="Number of reviewers to suggest")
@click.pass_context
def reviewers(ctx: click.Context, file_path: str, limit: int) -> None:
    """Suggest the best reviewers for a file.

    Ranks developers by their knowledge score (based on commit history)
    for the specified file.

    FILE_PATH is the path of the file to find reviewers for.
    """
    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])
    try:
        results = query_reviewers(db, file_path=file_path, limit=limit)
        format_reviewers(file_path, results)
    finally:
        db.close()


@cli.command()
@click.option("--max-experts", default=2, type=int, help="Maximum experts to flag as silo")
@click.option("--min-score", default=0.5, type=float, help="Minimum knowledge score threshold")
@click.pass_context
def silos(ctx: click.Context, max_experts: int, min_score: float) -> None:
    """Find knowledge silos — modules known by very few developers.

    Identifies modules where only 1-2 developers have meaningful expertise,
    creating a risk if those developers leave.
    """
    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])
    try:
        results = query_knowledge_silos(db, max_experts=max_experts, min_score=min_score)
        format_silos(results)
    finally:
        db.close()


@cli.command()
@click.option("--min-strength", default=3, type=int, help="Minimum coupling strength")
@click.pass_context
def coupling(ctx: click.Context, min_strength: int) -> None:
    """Show implicit module coupling based on co-change patterns.

    Identifies modules that are frequently changed together, even though
    they may not have explicit dependencies — a sign of hidden coupling.
    """
    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])
    try:
        results = query_module_coupling(db, min_strength=min_strength)
        format_coupling(results)
    finally:
        db.close()


@cli.command()
@click.option("--min-score", default=0.5, type=float, help="Minimum knowledge score threshold")
@click.pass_context
def risks(ctx: click.Context, min_score: float) -> None:
    """Identify high-risk modules (low bus factor + high change frequency).

    Risk score = change_frequency / bus_factor. Higher scores indicate
    modules that change frequently but are understood by few people.
    """
    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])
    try:
        results = query_risk_hotspots(db, min_score=min_score)
        format_risks(results)
    finally:
        db.close()


@cli.command()
@click.option("--min-shared", default=3, type=int, help="Minimum shared files")
@click.pass_context
def overlap(ctx: click.Context, min_shared: int) -> None:
    """Show developer knowledge overlap.

    Finds pairs of developers who share knowledge of many files,
    indicating they could substitute for each other.
    """
    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])
    try:
        results = query_developer_overlap(db, min_shared=min_shared)
        format_developer_overlap(results)
    finally:
        db.close()


@cli.command()
@click.pass_context
def summary(ctx: click.Context) -> None:
    """Show a summary of the current graph state."""
    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])
    try:
        result = query_graph_summary(db)
        format_summary(result)
    finally:
        db.close()


@cli.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def clear(ctx: click.Context, confirm: bool) -> None:
    """Clear all data from the graph."""
    if not confirm:
        if not click.confirm("This will delete all data in the graph. Continue?"):
            return

    db = _get_db(ctx.obj["host"], ctx.obj["port"], ctx.obj["graph"])
    try:
        db.clear_graph()
        console.print("[bold green]✅ Graph cleared.[/]")
    finally:
        db.close()


if __name__ == "__main__":
    cli()
