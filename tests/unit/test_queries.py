"""Unit tests for query result data classes and query parameter validation."""

from __future__ import annotations

from repograph.core.queries import (
    BlastRadiusResult,
    BusFactorResult,
    CouplingResult,
    DeveloperOverlap,
    KnowledgeSiloResult,
    ReviewerResult,
    RiskResult,
)


class TestBusFactorResult:
    def test_creation(self) -> None:
        r = BusFactorResult(
            module="src/core",
            bus_factor=3,
            experts=[{"name": "Alice", "email": "a@x.com", "score": 5.0}],
            file_count=10,
        )
        assert r.module == "src/core"
        assert r.bus_factor == 3
        assert len(r.experts) == 1

    def test_empty_experts(self) -> None:
        r = BusFactorResult(module="src", bus_factor=0, experts=[], file_count=5)
        assert r.bus_factor == 0
        assert r.experts == []


class TestBlastRadiusResult:
    def test_creation(self) -> None:
        r = BlastRadiusResult(
            source_file="src/main.py",
            affected_files=[{"path": "src/utils.py", "distance": 1}],
            affected_modules=["src"],
        )
        assert r.source_file == "src/main.py"
        assert len(r.affected_files) == 1

    def test_empty_radius(self) -> None:
        r = BlastRadiusResult(source_file="lonely.py", affected_files=[], affected_modules=[])
        assert len(r.affected_files) == 0


class TestReviewerResult:
    def test_creation(self) -> None:
        r = ReviewerResult(name="Alice", email="a@x.com", score=8.5, commit_count=42)
        assert r.score == 8.5
        assert r.commit_count == 42


class TestKnowledgeSiloResult:
    def test_critical_silo(self) -> None:
        r = KnowledgeSiloResult(
            module="src/billing",
            expert_count=1,
            experts=["Alice"],
            file_count=15,
            risk_level="critical",
        )
        assert r.risk_level == "critical"

    def test_warning_silo(self) -> None:
        r = KnowledgeSiloResult(
            module="src/auth",
            expert_count=2,
            experts=["Alice", "Bob"],
            file_count=8,
            risk_level="warning",
        )
        assert r.risk_level == "warning"


class TestCouplingResult:
    def test_creation(self) -> None:
        r = CouplingResult(
            module_a="src/api",
            module_b="src/core",
            coupling_strength=15,
            shared_files=8,
        )
        assert r.coupling_strength == 15


class TestRiskResult:
    def test_creation(self) -> None:
        r = RiskResult(
            module="src/core",
            bus_factor=1,
            change_frequency=50,
            risk_score=50.0,
            risk_level="critical",
        )
        assert r.risk_score == 50.0
        assert r.risk_level == "critical"


class TestDeveloperOverlap:
    def test_creation(self) -> None:
        r = DeveloperOverlap(
            dev_a="Alice",
            dev_b="Bob",
            shared_files=12,
            overlap_score=0.85,
        )
        assert r.shared_files == 12
