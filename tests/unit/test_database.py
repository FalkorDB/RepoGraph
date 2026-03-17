"""Unit tests for the database module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from repograph.core.config import FalkorDBConfig
from repograph.core.database import ConnectionError, DatabaseManager


class TestDatabaseManager:
    def test_config_defaults(self) -> None:
        dm = DatabaseManager()
        assert dm.config.host == "localhost"
        assert dm.config.port == 6379

    def test_config_custom(self) -> None:
        config = FalkorDBConfig(host="db.test", port=6380)
        dm = DatabaseManager(config)
        assert dm.config.host == "db.test"
        assert dm.config.port == 6380

    @patch("repograph.core.database.FalkorDB")
    def test_connect_success(self, mock_falkordb_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_graph = MagicMock()
        mock_falkordb_cls.return_value = mock_db
        mock_db.select_graph.return_value = mock_graph

        config = FalkorDBConfig(host="localhost", port=6379)
        dm = DatabaseManager(config)
        result = dm.connect()

        assert result == mock_graph
        mock_falkordb_cls.assert_called_once()
        mock_graph.query.assert_called_once_with("RETURN 1")

    @patch("repograph.core.database.FalkorDB")
    def test_connect_failure_retries(self, mock_falkordb_cls: MagicMock) -> None:
        mock_falkordb_cls.side_effect = Exception("Connection refused")

        config = FalkorDBConfig(max_retries=2, retry_delay=0.01)
        dm = DatabaseManager(config)

        with pytest.raises(ConnectionError, match="Failed to connect"):
            dm.connect()

        assert mock_falkordb_cls.call_count == 2

    @patch("repograph.core.database.FalkorDB")
    def test_health_check_success(self, mock_falkordb_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_graph = MagicMock()
        mock_falkordb_cls.return_value = mock_db
        mock_db.select_graph.return_value = mock_graph

        dm = DatabaseManager(FalkorDBConfig())
        dm.connect()
        assert dm.health_check() is True

    @patch("repograph.core.database.FalkorDB")
    def test_health_check_failure(self, mock_falkordb_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_graph = MagicMock()
        mock_falkordb_cls.return_value = mock_db
        mock_db.select_graph.return_value = mock_graph
        # First call succeeds (connect), second fails (health_check)
        mock_graph.query.side_effect = [None, Exception("timeout")]

        dm = DatabaseManager(FalkorDBConfig())
        dm.connect()
        assert dm.health_check() is False

    def test_close(self) -> None:
        dm = DatabaseManager(FalkorDBConfig())
        dm.close()
        # Accessing graph after close should reconnect
        assert dm._graph is None


class TestGetDb:
    @patch("repograph.core.database.FalkorDB")
    def test_context_manager(self, mock_falkordb_cls: MagicMock) -> None:
        from repograph.core.database import get_db

        mock_db = MagicMock()
        mock_graph = MagicMock()
        mock_falkordb_cls.return_value = mock_db
        mock_db.select_graph.return_value = mock_graph

        with get_db() as db:
            assert db is not None
            assert db.health_check() is True
