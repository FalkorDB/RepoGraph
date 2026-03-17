"""Unit tests for team model and queries."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from repograph.core.teams import (
    TeamConfig,
    auto_detect_teams,
    build_team_graph,
    load_teams_from_yaml,
    query_team_bus_factor,
    query_team_silos,
)


class TestLoadTeamsFromYaml:
    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "teams.yml"
        config_file.write_text(
            "teams:\n"
            "  - name: Backend\n"
            "    members:\n"
            "      - alice@example.com\n"
            "      - bob@example.com\n"
            "  - name: Frontend\n"
            "    members:\n"
            "      - carol@example.com\n"
        )
        teams = load_teams_from_yaml(config_file)
        assert len(teams) == 2
        assert teams[0].name == "Backend"
        assert teams[0].members == ["alice@example.com", "bob@example.com"]
        assert teams[1].name == "Frontend"
        assert teams[1].members == ["carol@example.com"]

    def test_load_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_teams_from_yaml("/nonexistent/teams.yml")

    def test_load_invalid_yaml_no_teams_key(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bad.yml"
        config_file.write_text("something_else:\n  - name: Test\n")
        with pytest.raises(ValueError, match="expected 'teams' key"):
            load_teams_from_yaml(config_file)

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "empty.yml"
        config_file.write_text("")
        with pytest.raises(ValueError, match="expected 'teams' key"):
            load_teams_from_yaml(config_file)

    def test_skip_invalid_entries(self, tmp_path: Path) -> None:
        config_file = tmp_path / "partial.yml"
        config_file.write_text(
            "teams:\n  - name: Valid\n    members: [a@b.com]\n  - invalid_entry: true\n"
        )
        teams = load_teams_from_yaml(config_file)
        assert len(teams) == 1
        assert teams[0].name == "Valid"


class TestBuildTeamGraph:
    def test_build_team_graph(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(result_set=[["Alice"]])

        teams = [TeamConfig(name="Backend", members=["alice@example.com"])]
        stats = build_team_graph(mock_db, teams)

        assert stats["teams"] == 1
        assert stats["memberships"] == 1
        assert mock_db.query.call_count == 2  # MERGE team + MERGE membership

    def test_build_team_missing_developer(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(result_set=[])

        teams = [TeamConfig(name="Backend", members=["unknown@example.com"])]
        stats = build_team_graph(mock_db, teams)

        assert stats["teams"] == 1
        assert stats["memberships"] == 0


class TestAutoDetectTeams:
    def test_auto_detect_multiple_domains(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(
            result_set=[
                ["a@backend.company.com", "Alice"],
                ["b@backend.company.com", "Bob"],
                ["c@frontend.company.com", "Carol"],
            ]
        )

        teams = auto_detect_teams(mock_db)
        assert len(teams) == 2
        names = {t.name for t in teams}
        assert "Backend" in names
        assert "Frontend" in names

    def test_auto_detect_single_domain(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(
            result_set=[
                ["a@company.com", "Alice"],
                ["b@company.com", "Bob"],
            ]
        )

        teams = auto_detect_teams(mock_db)
        assert len(teams) == 1
        assert teams[0].name == "All"

    def test_auto_detect_empty_graph(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(result_set=[])

        teams = auto_detect_teams(mock_db)
        assert teams == []


class TestTeamQueries:
    def test_query_team_bus_factor_empty(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(result_set=[])

        results = query_team_bus_factor(mock_db)
        assert results == []

    def test_query_team_bus_factor_with_data(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(
            result_set=[
                ["Backend", 3, 5, ["src/api", "src/core", "src/models", "src/db", "src/utils"]],
                ["Frontend", 2, 3, ["src/ui", "src/components", "src/styles"]],
            ]
        )

        results = query_team_bus_factor(mock_db)
        assert len(results) == 2
        # Backend has exclusive: api, core, models, db, utils (not shared with Frontend)
        # Frontend has exclusive: ui, components, styles (not shared with Backend)
        backend = next(r for r in results if r.team == "Backend")
        frontend = next(r for r in results if r.team == "Frontend")
        assert backend.member_count == 3
        assert frontend.member_count == 2

    def test_query_team_silos_empty(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(result_set=[])

        results = query_team_silos(mock_db)
        assert results == []

    def test_query_team_silos_with_data(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(
            result_set=[
                ["src/api", "Backend", 2, 5],
                ["src/ui", "Frontend", 1, 3],
            ]
        )

        results = query_team_silos(mock_db)
        assert len(results) == 2
        assert results[0].module == "src/api"
        assert results[0].owning_team == "Backend"
        assert results[1].module == "src/ui"
        assert results[1].owning_team == "Frontend"

    def test_query_team_silos_null_team(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(
            result_set=[
                ["src/orphan", None, 1, 2],
            ]
        )

        results = query_team_silos(mock_db)
        assert len(results) == 1
        assert results[0].owning_team == "Unassigned"
