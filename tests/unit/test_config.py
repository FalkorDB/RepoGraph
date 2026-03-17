"""Unit tests for the configuration module."""

from __future__ import annotations

import os

from repograph.core.config import AnalysisConfig, AppConfig, FalkorDBConfig


class TestFalkorDBConfig:
    def test_defaults(self) -> None:
        config = FalkorDBConfig()
        assert config.host == "localhost"
        assert config.port == 6379
        assert config.graph_name == "repograph"
        assert config.password is None
        assert config.max_retries == 3

    def test_from_env(self, monkeypatch: object) -> None:
        import pytest

        mp = pytest.MonkeyPatch()
        mp.setenv("FALKORDB_HOST", "db.example.com")
        mp.setenv("FALKORDB_PORT", "6380")
        mp.setenv("REPOGRAPH_GRAPH_NAME", "testgraph")
        mp.setenv("FALKORDB_PASSWORD", "secret")

        config = FalkorDBConfig.from_env()
        assert config.host == "db.example.com"
        assert config.port == 6380
        assert config.graph_name == "testgraph"
        assert config.password == "secret"

        mp.undo()

    def test_immutable(self) -> None:
        config = FalkorDBConfig()
        try:
            config.host = "other"  # type: ignore[misc]
            assert False, "Should raise"
        except AttributeError:
            pass


class TestAnalysisConfig:
    def test_defaults(self) -> None:
        config = AnalysisConfig()
        assert config.max_commits == 5000
        assert config.knowledge_decay_days == 365
        assert config.module_depth == 2
        assert ".git" in config.excluded_paths

    def test_from_env(self) -> None:
        import pytest

        mp = pytest.MonkeyPatch()
        mp.setenv("REPOGRAPH_MAX_COMMITS", "1000")
        mp.setenv("REPOGRAPH_MODULE_DEPTH", "3")

        config = AnalysisConfig.from_env()
        assert config.max_commits == 1000
        assert config.module_depth == 3

        mp.undo()


class TestAppConfig:
    def test_from_env(self) -> None:
        config = AppConfig.from_env()
        assert isinstance(config.db, FalkorDBConfig)
        assert isinstance(config.analysis, AnalysisConfig)
