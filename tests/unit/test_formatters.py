"""Unit tests for output formatters."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from rich.console import Console

from repograph.core.queries import (
    BlastRadiusResult,
    BusFactorResult,
    CouplingResult,
    DeveloperOverlap,
    KnowledgeSiloResult,
    ReviewerResult,
    RiskResult,
)
from repograph.utils.formatters import (
    format_blast_radius,
    format_bus_factor,
    format_coupling,
    format_developer_overlap,
    format_reviewers,
    format_risks,
    format_silos,
    format_summary,
    format_team_bus_factor,
    format_team_silos,
)


def _capture_output(func, *args):
    """Capture Rich console output."""
    buf = StringIO()
    test_console = Console(file=buf, force_terminal=True, width=120)
    with patch("repograph.utils.formatters.console", test_console):
        func(*args)
    return buf.getvalue()


class TestFormatBusFactor:
    def test_empty_results(self) -> None:
        output = _capture_output(format_bus_factor, [])
        assert "No bus factor data" in output

    def test_with_results(self) -> None:
        results = [
            BusFactorResult(
                module="src/core",
                bus_factor=1,
                experts=[{"name": "Alice", "email": "a@x.com", "score": 5.0}],
                file_count=10,
            ),
            BusFactorResult(
                module="src/api",
                bus_factor=3,
                experts=[
                    {"name": "Bob", "score": 4.0},
                    {"name": "Carol", "score": 3.0},
                    {"name": "Dave", "score": 2.0},
                ],
                file_count=5,
            ),
        ]
        output = _capture_output(format_bus_factor, results)
        assert "Bus Factor" in output
        assert "src/core" in output
        assert "Alice" in output


class TestFormatBlastRadius:
    def test_empty_radius(self) -> None:
        result = BlastRadiusResult(source_file="test.py", affected_files=[], affected_modules=[])
        output = _capture_output(format_blast_radius, result)
        assert "No co-change" in output

    def test_with_affected_files(self) -> None:
        result = BlastRadiusResult(
            source_file="src/main.py",
            affected_files=[
                {"path": "src/utils.py", "distance": 1},
                {"path": "src/api.py", "distance": 2},
                {"path": "src/deep.py", "distance": 3},
            ],
            affected_modules=["src"],
        )
        output = _capture_output(format_blast_radius, result)
        assert "src/main.py" in output
        assert "src/utils.py" in output
        assert "Direct" in output
        assert "Indirect" in output
        assert "Transitive" in output


class TestFormatReviewers:
    def test_empty(self) -> None:
        output = _capture_output(format_reviewers, "test.py", [])
        assert "No reviewers" in output

    def test_with_reviewers(self) -> None:
        reviewers = [
            ReviewerResult(name="Alice", email="a@x.com", score=8.5, commit_count=42),
            ReviewerResult(name="Bob", email="b@x.com", score=5.0, commit_count=20),
        ]
        output = _capture_output(format_reviewers, "test.py", reviewers)
        assert "Alice" in output
        assert "Bob" in output


class TestFormatSilos:
    def test_no_silos(self) -> None:
        output = _capture_output(format_silos, [])
        assert "No knowledge silos" in output

    def test_with_silos(self) -> None:
        silos = [
            KnowledgeSiloResult(
                module="src/billing",
                expert_count=1,
                experts=["Alice"],
                file_count=6,
                risk_level="critical",
            ),
        ]
        output = _capture_output(format_silos, silos)
        assert "src/billing" in output
        assert "CRITICAL" in output


class TestFormatCoupling:
    def test_no_coupling(self) -> None:
        output = _capture_output(format_coupling, [])
        assert "No significant" in output

    def test_with_coupling(self) -> None:
        couplings = [
            CouplingResult(
                module_a="src/api", module_b="src/core", coupling_strength=15, shared_files=8
            ),
        ]
        output = _capture_output(format_coupling, couplings)
        assert "src/api" in output


class TestFormatRisks:
    def test_no_risks(self) -> None:
        output = _capture_output(format_risks, [])
        assert "No high-risk" in output

    def test_with_risks(self) -> None:
        risks = [
            RiskResult(
                module="src/core",
                bus_factor=1,
                change_frequency=50,
                risk_score=50.0,
                risk_level="critical",
            ),
            RiskResult(
                module="src/api",
                bus_factor=3,
                change_frequency=20,
                risk_score=6.7,
                risk_level="high",
            ),
            RiskResult(
                module="src/utils",
                bus_factor=5,
                change_frequency=10,
                risk_score=2.0,
                risk_level="medium",
            ),
            RiskResult(
                module="src/docs",
                bus_factor=8,
                change_frequency=5,
                risk_score=0.6,
                risk_level="low",
            ),
        ]
        output = _capture_output(format_risks, risks)
        assert "CRITICAL" in output
        assert "HIGH" in output


class TestFormatDeveloperOverlap:
    def test_empty(self) -> None:
        output = _capture_output(format_developer_overlap, [])
        assert "No significant" in output

    def test_with_overlap(self) -> None:
        overlaps = [
            DeveloperOverlap(dev_a="Alice", dev_b="Bob", shared_files=12, overlap_score=0.85)
        ]
        output = _capture_output(format_developer_overlap, overlaps)
        assert "Alice" in output
        assert "Bob" in output


class TestFormatSummary:
    def test_summary(self) -> None:
        output = _capture_output(
            format_summary, {"developers": 8, "files": 32, "modules": 9, "commits": 300}
        )
        assert "Developers" in output
        assert "8" in output


class TestFormatTeamBusFactor:
    def test_empty(self) -> None:
        output = _capture_output(format_team_bus_factor, [])
        assert "No team data" in output

    def test_with_results(self) -> None:
        from repograph.core.teams import TeamBusFactor

        results = [
            TeamBusFactor(
                team="Backend",
                member_count=3,
                modules_covered=5,
                exclusive_modules=["src/api", "src/core"],
            ),
            TeamBusFactor(
                team="Frontend",
                member_count=2,
                modules_covered=3,
                exclusive_modules=[],
            ),
        ]
        output = _capture_output(format_team_bus_factor, results)
        assert "Backend" in output
        assert "Frontend" in output
        assert "src/api" in output


class TestFormatTeamSilos:
    def test_empty(self) -> None:
        output = _capture_output(format_team_silos, [])
        assert "No team-level silos" in output

    def test_with_results(self) -> None:
        from repograph.core.teams import TeamSilo

        results = [
            TeamSilo(module="src/billing", owning_team="Backend", experts_in_team=2, file_count=5),
        ]
        output = _capture_output(format_team_silos, results)
        assert "src/billing" in output
        assert "Backend" in output
