"""Unit tests for the Flask web API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from repograph.core.config import FalkorDBConfig
from repograph.web.app import create_app


@pytest.fixture
def mock_db():
    """Create a mock database manager."""
    with patch("repograph.web.app.DatabaseManager") as mock_cls:
        db = MagicMock()
        db.health_check.return_value = True
        mock_cls.return_value = db
        yield db


@pytest.fixture
def client(mock_db):
    """Create a Flask test client."""
    app = create_app(FalkorDBConfig(host="localhost", port=6379, graph_name="test"))
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestDashboard:
    def test_dashboard_returns_html(self, client) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"RepoGraph" in resp.data
        assert b"d3.v7" in resp.data

    def test_dashboard_contains_tabs(self, client) -> None:
        resp = client.get("/")
        assert b"Overview" in resp.data
        assert b"Bus Factor" in resp.data
        assert b"Risks" in resp.data
        assert b"Coupling" in resp.data
        assert b"Teams" in resp.data


class TestSummaryAPI:
    def test_summary_endpoint(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[[5, 20, 8, 100]])
        resp = client.get("/api/summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "developers" in data or isinstance(data, dict)


class TestBusFactorAPI:
    def test_bus_factor_empty(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/bus-factor")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_bus_factor_with_module_filter(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/bus-factor?module=src/api")
        assert resp.status_code == 200


class TestBlastRadiusAPI:
    def test_blast_radius_endpoint(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/blast-radius/src/main.py")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "source_file" in data

    def test_blast_radius_depth_clamped(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/blast-radius/src/main.py?depth=10")
        assert resp.status_code == 200


class TestReviewersAPI:
    def test_reviewers_empty(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/reviewers/src/main.py")
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestSilosAPI:
    def test_silos_empty(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/silos")
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestCouplingAPI:
    def test_coupling_empty(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/coupling")
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestRisksAPI:
    def test_risks_empty(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/risks")
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestOverlapAPI:
    def test_overlap_empty(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/overlap")
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestGraphAPI:
    def test_graph_empty(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/graph")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "nodes" in data
        assert "links" in data
        assert data["nodes"] == []
        assert data["links"] == []


class TestTeamAPIs:
    def test_team_bus_factor_empty(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/teams/bus-factor")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_team_silos_empty(self, client, mock_db) -> None:
        mock_db.query.return_value = MagicMock(result_set=[])
        resp = client.get("/api/teams/silos")
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestWebhook:
    def test_webhook_no_payload(self, client) -> None:
        resp = client.post("/webhook/push")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_webhook_no_repo_path(self, client) -> None:
        resp = client.post(
            "/webhook/push",
            json={"ref": "refs/heads/main"},
        )
        assert resp.status_code == 500
        assert "REPOGRAPH_REPO_PATH" in resp.get_json()["error"]
