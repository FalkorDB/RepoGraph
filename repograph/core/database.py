"""FalkorDB connection management with retry and health checking."""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from falkordb import FalkorDB, Graph

from repograph.core.config import FalkorDBConfig

logger = logging.getLogger(__name__)


class ConnectionError(Exception):
    """Raised when FalkorDB connection fails after retries."""


class DatabaseManager:
    """Manages FalkorDB connections with retry logic and health checking."""

    def __init__(self, config: FalkorDBConfig | None = None) -> None:
        self._config = config or FalkorDBConfig.from_env()
        self._db: FalkorDB | None = None
        self._graph: Graph | None = None

    @property
    def config(self) -> FalkorDBConfig:
        return self._config

    def connect(self) -> Graph:
        """Connect to FalkorDB with retry logic. Returns the graph handle."""
        last_error: Exception | None = None

        for attempt in range(1, self._config.max_retries + 1):
            try:
                logger.info(
                    "Connecting to FalkorDB at %s:%d (attempt %d/%d)",
                    self._config.host,
                    self._config.port,
                    attempt,
                    self._config.max_retries,
                )
                self._db = FalkorDB(
                    host=self._config.host,
                    port=self._config.port,
                    password=self._config.password,
                )
                self._graph = self._db.select_graph(self._config.graph_name)
                # Verify connectivity with a simple query
                self._graph.query("RETURN 1")
                logger.info("Connected to FalkorDB successfully")
                return self._graph
            except Exception as e:
                last_error = e
                logger.warning(
                    "Connection attempt %d failed: %s",
                    attempt,
                    str(e),
                )
                if attempt < self._config.max_retries:
                    time.sleep(self._config.retry_delay * attempt)

        raise ConnectionError(
            f"Failed to connect to FalkorDB at {self._config.host}:{self._config.port} "
            f"after {self._config.max_retries} attempts: {last_error}"
        )

    @property
    def graph(self) -> Graph:
        """Get the current graph handle, connecting if necessary."""
        if self._graph is None:
            return self.connect()
        return self._graph

    def health_check(self) -> bool:
        """Check if the database connection is healthy."""
        try:
            self.graph.query("RETURN 1")
            return True
        except Exception as e:
            logger.warning("Health check failed: %s", str(e))
            return False

    def clear_graph(self) -> None:
        """Delete all nodes and relationships in the graph."""
        try:
            self.graph.query("MATCH (n) DETACH DELETE n")
            logger.info("Graph cleared")
        except Exception as e:
            logger.error("Failed to clear graph: %s", str(e))
            raise

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a Cypher query with optional parameters."""
        logger.debug("Executing query: %s (params: %s)", cypher, params)
        return self.graph.query(cypher, params=params)

    def close(self) -> None:
        """Close the database connection."""
        self._graph = None
        self._db = None
        logger.info("Database connection closed")


@contextmanager
def get_db(config: FalkorDBConfig | None = None) -> Generator[DatabaseManager, None, None]:
    """Context manager for database access."""
    db = DatabaseManager(config)
    try:
        db.connect()
        yield db
    finally:
        db.close()
