"""Unit tests for CLI commands using Click's test runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from repograph.cli.main import cli


class TestCLI:
    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_help(self) -> None:
        result = self.runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "RepoGraph" in result.output
        assert "analyze" in result.output

    def test_version(self) -> None:
        result = self.runner.invoke(cli, ["--version"])
        assert result.exit_code == 0

    @patch("repograph.cli.main._get_db")
    def test_summary(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.query.return_value = MagicMock(result_set=[[8, 32, 9, 300]])

        result = self.runner.invoke(cli, ["summary"])
        assert result.exit_code == 0
        mock_db.close.assert_called_once()

    @patch("repograph.cli.main._get_db")
    def test_bus_factor(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.query.return_value = MagicMock(result_set=[])

        result = self.runner.invoke(cli, ["bus-factor"])
        assert result.exit_code == 0
        mock_db.close.assert_called_once()

    @patch("repograph.cli.main._get_db")
    def test_blast_radius(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.query.return_value = MagicMock(result_set=[])

        result = self.runner.invoke(cli, ["blast-radius", "src/main.py"])
        assert result.exit_code == 0
        mock_db.close.assert_called_once()

    def test_blast_radius_invalid_depth(self) -> None:
        result = self.runner.invoke(cli, ["blast-radius", "src/main.py", "--depth", "10"])
        assert result.exit_code != 0

    @patch("repograph.cli.main._get_db")
    def test_reviewers(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.query.return_value = MagicMock(result_set=[])

        result = self.runner.invoke(cli, ["reviewers", "src/main.py"])
        assert result.exit_code == 0

    @patch("repograph.cli.main._get_db")
    def test_silos(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.query.return_value = MagicMock(result_set=[])

        result = self.runner.invoke(cli, ["silos"])
        assert result.exit_code == 0

    @patch("repograph.cli.main._get_db")
    def test_coupling(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.query.return_value = MagicMock(result_set=[])

        result = self.runner.invoke(cli, ["coupling"])
        assert result.exit_code == 0

    @patch("repograph.cli.main._get_db")
    def test_risks(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.query.return_value = MagicMock(result_set=[])

        result = self.runner.invoke(cli, ["risks"])
        assert result.exit_code == 0

    @patch("repograph.cli.main._get_db")
    def test_overlap(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.query.return_value = MagicMock(result_set=[])

        result = self.runner.invoke(cli, ["overlap"])
        assert result.exit_code == 0

    @patch("repograph.cli.main._get_db")
    def test_clear_with_confirm(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        result = self.runner.invoke(cli, ["clear", "--confirm"])
        assert result.exit_code == 0
        mock_db.clear_graph.assert_called_once()

    @patch("repograph.cli.main._get_db")
    def test_clear_without_confirm_decline(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        self.runner.invoke(cli, ["clear"], input="n\n")
        mock_db.clear_graph.assert_not_called()

    @patch("repograph.cli.main._get_db")
    def test_seed(self, mock_get_db: MagicMock) -> None:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        # Mock the seed data generation
        mock_db.query.return_value = MagicMock(result_set=[[8, 32, 9, 300]])

        with patch("repograph.core.seed.generate_seed_data", return_value={"commits": 100}):
            result = self.runner.invoke(cli, ["seed", "--commits", "100"])
        assert result.exit_code == 0
