"""Integration tests — require a running FalkorDB instance.

Run with: pytest tests/integration/ -m integration
Requires FalkorDB on localhost:6379 (use docker-compose up -d falkordb).
"""

from __future__ import annotations

import pytest

from repograph.core.config import FalkorDBConfig
from repograph.core.database import DatabaseManager
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
from repograph.core.schema import setup_schema, verify_schema
from repograph.core.seed import generate_seed_data


@pytest.fixture(scope="module")
def db() -> DatabaseManager:
    """Create a database manager connected to a test graph."""
    config = FalkorDBConfig(
        host="localhost",
        port=6379,
        graph_name="repograph_integration_test",
        max_retries=2,
        retry_delay=0.5,
    )
    dm = DatabaseManager(config)
    try:
        dm.connect()
    except Exception:
        pytest.skip("FalkorDB not available at localhost:6379")
    return dm


@pytest.fixture(scope="module", autouse=True)
def seeded_graph(db: DatabaseManager) -> None:
    """Seed the test graph with demo data."""
    db.clear_graph()
    setup_schema(db)
    generate_seed_data(db, num_commits=200)


@pytest.mark.integration
class TestGraphIntegration:
    """Integration tests that exercise the full query pipeline against FalkorDB."""

    def test_graph_summary(self, db: DatabaseManager) -> None:
        summary = query_graph_summary(db)
        assert summary["developers"] == 8
        assert summary["files"] == 32
        assert summary["commits"] == 200
        assert summary["modules"] > 0

    def test_bus_factor(self, db: DatabaseManager) -> None:
        results = query_bus_factor(db, min_score=0.5)
        assert len(results) > 0
        for r in results:
            assert r.bus_factor >= 1
            assert r.file_count > 0
            assert len(r.experts) > 0

    def test_bus_factor_specific_module(self, db: DatabaseManager) -> None:
        results = query_bus_factor(db, module="src/core", min_score=0.5)
        assert len(results) == 1
        assert results[0].module == "src/core"

    def test_blast_radius(self, db: DatabaseManager) -> None:
        result = query_blast_radius(db, "src/core/engine.py", max_depth=2)
        assert result.source_file == "src/core/engine.py"
        # Should find some co-changed files
        assert len(result.affected_files) > 0
        # All distances should be <= max_depth
        for af in result.affected_files:
            assert af["distance"] <= 2

    def test_blast_radius_nonexistent_file(self, db: DatabaseManager) -> None:
        result = query_blast_radius(db, "nonexistent.py", max_depth=2)
        assert len(result.affected_files) == 0

    def test_reviewers(self, db: DatabaseManager) -> None:
        reviewers = query_reviewers(db, "src/api/routes.py", limit=3)
        assert len(reviewers) > 0
        assert len(reviewers) <= 3
        # Scores should be descending
        for i in range(1, len(reviewers)):
            assert reviewers[i - 1].score >= reviewers[i].score

    def test_reviewers_nonexistent_file(self, db: DatabaseManager) -> None:
        reviewers = query_reviewers(db, "nonexistent.py", limit=5)
        assert len(reviewers) == 0

    def test_knowledge_silos(self, db: DatabaseManager) -> None:
        # With a high min_score, some modules should become silos
        silos = query_knowledge_silos(db, max_experts=2, min_score=5.0)
        # We can't guarantee the exact number, but the query should work
        for s in silos:
            assert s.expert_count <= 2
            assert s.risk_level in ("critical", "warning")

    def test_module_coupling(self, db: DatabaseManager) -> None:
        couplings = query_module_coupling(db, min_strength=2)
        assert len(couplings) > 0
        for c in couplings:
            assert c.module_a != c.module_b
            assert c.coupling_strength >= 2

    def test_risk_hotspots(self, db: DatabaseManager) -> None:
        risks = query_risk_hotspots(db, min_score=0.5)
        assert len(risks) > 0
        for r in risks:
            assert r.bus_factor >= 1
            assert r.change_frequency >= 1
            assert r.risk_level in ("critical", "high", "medium", "low")

    def test_developer_overlap(self, db: DatabaseManager) -> None:
        overlaps = query_developer_overlap(db, min_shared=2)
        assert len(overlaps) > 0
        for o in overlaps:
            assert o.dev_a != o.dev_b
            assert o.shared_files >= 2

    def test_schema_verification(self, db: DatabaseManager) -> None:
        counts = verify_schema(db)
        assert counts["Developer"] == 8
        assert counts["File"] == 32
        assert counts["Commit"] == 200

    def test_end_to_end_pipeline(self, db: DatabaseManager) -> None:
        """Full pipeline: seed → query all insights → verify consistency."""
        query_graph_summary(db)

        # All query types should return data
        bf = query_bus_factor(db, min_score=0.3)
        assert len(bf) > 0

        br = query_blast_radius(db, "src/core/engine.py", max_depth=2)
        assert br.source_file == "src/core/engine.py"

        rev = query_reviewers(db, "src/api/routes.py", limit=5)
        assert len(rev) > 0

        risks = query_risk_hotspots(db, min_score=0.3)
        assert len(risks) > 0

        coupling = query_module_coupling(db, min_strength=1)
        assert len(coupling) > 0

        overlap = query_developer_overlap(db, min_shared=1)
        assert len(overlap) > 0
