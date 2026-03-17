"""Configuration management for RepoGraph."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FalkorDBConfig:
    """FalkorDB connection configuration."""

    host: str = "localhost"
    port: int = 6379
    graph_name: str = "repograph"
    password: str | None = None
    max_retries: int = 3
    retry_delay: float = 1.0
    socket_timeout: float = 30.0

    @classmethod
    def from_env(cls) -> FalkorDBConfig:
        """Create config from environment variables."""
        return cls(
            host=os.environ.get("FALKORDB_HOST", "localhost"),
            port=int(os.environ.get("FALKORDB_PORT", "6379")),
            graph_name=os.environ.get("REPOGRAPH_GRAPH_NAME", "repograph"),
            password=os.environ.get("FALKORDB_PASSWORD"),
            max_retries=int(os.environ.get("REPOGRAPH_MAX_RETRIES", "3")),
            retry_delay=float(os.environ.get("REPOGRAPH_RETRY_DELAY", "1.0")),
            socket_timeout=float(os.environ.get("REPOGRAPH_SOCKET_TIMEOUT", "30.0")),
        )


@dataclass(frozen=True)
class AnalysisConfig:
    """Configuration for repository analysis."""

    max_commits: int = 5000
    knowledge_decay_days: int = 365
    co_change_window: int = 1
    min_knowledge_score: float = 0.1
    module_depth: int = 2
    excluded_paths: list[str] = field(
        default_factory=lambda: [
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            ".tox",
            "dist",
            "build",
            ".egg-info",
        ]
    )

    @classmethod
    def from_env(cls) -> AnalysisConfig:
        """Create config from environment variables."""
        return cls(
            max_commits=int(os.environ.get("REPOGRAPH_MAX_COMMITS", "5000")),
            knowledge_decay_days=int(os.environ.get("REPOGRAPH_KNOWLEDGE_DECAY_DAYS", "365")),
            co_change_window=int(os.environ.get("REPOGRAPH_CO_CHANGE_WINDOW", "1")),
            min_knowledge_score=float(os.environ.get("REPOGRAPH_MIN_KNOWLEDGE_SCORE", "0.1")),
            module_depth=int(os.environ.get("REPOGRAPH_MODULE_DEPTH", "2")),
        )


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    db: FalkorDBConfig = field(default_factory=FalkorDBConfig.from_env)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig.from_env)

    @classmethod
    def from_env(cls) -> AppConfig:
        return cls(
            db=FalkorDBConfig.from_env(),
            analysis=AnalysisConfig.from_env(),
        )
