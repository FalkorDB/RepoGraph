"""Tests for temporal trend analysis (snapshots module)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from repograph.core.snapshots import (
    ModuleSnapshotData,
    SnapshotSummary,
    TrendPoint,
    TrendResult,
    query_module_trend,
    query_snapshot_history,
    query_trends,
    take_snapshot,
)


class MockQueryResult:
    """Mock FalkorDB query result."""

    def __init__(self, result_set=None):
        self.result_set = result_set


@pytest.fixture()
def mock_db():
    """Create a mock DatabaseManager."""
    return MagicMock()


class TestTakeSnapshot:
    """Tests for take_snapshot()."""

    def test_take_snapshot_basic(self, mock_db):
        """Test basic snapshot creation."""
        # Mock query_graph_summary
        with (
            patch("repograph.core.snapshots.query_graph_summary") as mock_summary,
            patch("repograph.core.snapshots.query_bus_factor") as mock_bf,
            patch("repograph.core.snapshots.query_knowledge_silos") as mock_silos,
            patch("repograph.core.snapshots.query_risk_hotspots") as mock_risks,
        ):
            mock_summary.return_value = {
                "developers": 5,
                "modules": 3,
                "files": 20,
                "commits": 100,
            }
            # Bus factor results
            bf1 = MagicMock()
            bf1.bus_factor = 3
            bf2 = MagicMock()
            bf2.bus_factor = 1
            mock_bf.return_value = [bf1, bf2]

            mock_silos.return_value = [MagicMock(), MagicMock()]

            risk1 = MagicMock()
            risk1.module = "mod/a"
            risk1.bus_factor = 1
            risk1.risk_score = 12.0
            risk1.risk_level = "critical"
            risk2 = MagicMock()
            risk2.module = "mod/b"
            risk2.bus_factor = 3
            risk2.risk_score = 2.0
            risk2.risk_level = "low"
            mock_risks.return_value = [risk1, risk2]

            mock_db.query.return_value = MockQueryResult([])

            result = take_snapshot(mock_db)

            assert isinstance(result, SnapshotSummary)
            assert result.developer_count == 5
            assert result.module_count == 3
            assert result.file_count == 20
            assert result.commit_count == 100
            assert result.avg_bus_factor == 2.0
            assert result.silo_count == 2
            assert result.high_risk_count == 1  # only "critical" counts

    def test_take_snapshot_empty_graph(self, mock_db):
        """Test snapshot with no data."""
        with (
            patch("repograph.core.snapshots.query_graph_summary") as mock_summary,
            patch("repograph.core.snapshots.query_bus_factor") as mock_bf,
            patch("repograph.core.snapshots.query_knowledge_silos") as mock_silos,
            patch("repograph.core.snapshots.query_risk_hotspots") as mock_risks,
        ):
            mock_summary.return_value = {
                "developers": 0,
                "modules": 0,
                "files": 0,
                "commits": 0,
            }
            mock_bf.return_value = []
            mock_silos.return_value = []
            mock_risks.return_value = []
            mock_db.query.return_value = MockQueryResult([])

            result = take_snapshot(mock_db)

            assert result.avg_bus_factor == 0.0
            assert result.silo_count == 0
            assert result.high_risk_count == 0


class TestQuerySnapshotHistory:
    """Tests for query_snapshot_history()."""

    def test_returns_snapshots(self, mock_db):
        """Test retrieving snapshot history."""
        mock_db.query.return_value = MockQueryResult(
            [
                ["abc123", 1000000.0, 5, 3, 20, 100, 2.5, 1, 0],
                ["def456", 999000.0, 4, 3, 18, 90, 2.0, 2, 1],
            ]
        )

        result = query_snapshot_history(mock_db, limit=10)

        assert len(result) == 2
        assert result[0].snapshot_id == "abc123"
        assert result[0].avg_bus_factor == 2.5
        assert result[1].snapshot_id == "def456"

    def test_empty_history(self, mock_db):
        """Test empty snapshot history."""
        mock_db.query.return_value = MockQueryResult([])

        result = query_snapshot_history(mock_db)
        assert result == []

    def test_none_result_set(self, mock_db):
        """Test None result set."""
        mock_db.query.return_value = MockQueryResult(None)

        result = query_snapshot_history(mock_db)
        assert result == []


class TestQueryTrends:
    """Tests for query_trends()."""

    def test_improving_bus_factor(self, mock_db):
        """Test that increasing bus factor is detected as improving."""
        mock_db.query.return_value = MockQueryResult(
            [
                ["snap2", 2000.0, 5, 3, 20, 100, 3.0, 1, 0],  # newest
                ["snap1", 1000.0, 5, 3, 20, 100, 1.5, 3, 2],  # oldest
            ]
        )

        result = query_trends(mock_db)

        assert "avg_bus_factor" in result
        bf_trend = result["avg_bus_factor"]
        assert bf_trend.direction == "improving"
        assert bf_trend.change_pct > 0

    def test_degrading_silos(self, mock_db):
        """Test that increasing silo count is detected as degrading."""
        mock_db.query.return_value = MockQueryResult(
            [
                ["snap2", 2000.0, 5, 3, 20, 100, 2.0, 5, 2],  # newest (5 silos)
                ["snap1", 1000.0, 5, 3, 20, 100, 2.0, 1, 0],  # oldest (1 silo)
            ]
        )

        result = query_trends(mock_db)

        silo_trend = result["silo_count"]
        assert silo_trend.direction == "degrading"

    def test_stable_metrics(self, mock_db):
        """Test that unchanged metrics are stable."""
        mock_db.query.return_value = MockQueryResult(
            [
                ["snap2", 2000.0, 5, 3, 20, 100, 2.0, 2, 1],
                ["snap1", 1000.0, 5, 3, 20, 100, 2.0, 2, 1],
            ]
        )

        result = query_trends(mock_db)

        assert result["avg_bus_factor"].direction == "stable"
        assert result["silo_count"].direction == "stable"

    def test_no_snapshots(self, mock_db):
        """Test with no snapshot data."""
        mock_db.query.return_value = MockQueryResult([])

        result = query_trends(mock_db)
        assert result == {}


class TestQueryModuleTrend:
    """Tests for query_module_trend()."""

    def test_module_history(self, mock_db):
        """Test retrieving trend for a module."""
        mock_db.query.return_value = MockQueryResult(
            [
                ["mod/a", 2, 5.0, "high"],
                ["mod/a", 3, 3.0, "medium"],
            ]
        )

        result = query_module_trend(mock_db, module="mod/a")

        assert len(result) == 2
        assert isinstance(result[0], ModuleSnapshotData)
        assert result[0].bus_factor == 2
        assert result[1].bus_factor == 3

    def test_empty_module_history(self, mock_db):
        """Test empty module trend."""
        mock_db.query.return_value = MockQueryResult([])

        result = query_module_trend(mock_db, module="nonexistent")
        assert result == []


class TestTrendResult:
    """Tests for TrendResult dataclass defaults."""

    def test_defaults(self):
        trend = TrendResult(metric="test")
        assert trend.points == []
        assert trend.direction == "stable"
        assert trend.change_pct == 0.0

    def test_trend_point(self):
        point = TrendPoint(timestamp=1000.0, value=3.5)
        assert point.timestamp == 1000.0
        assert point.value == 3.5
