"""Graph schema setup — indices and constraints for the RepoGraph model."""

from __future__ import annotations

import logging

from repograph.core.database import DatabaseManager

logger = logging.getLogger(__name__)

# Index definitions: (label, property, is_unique)
INDICES: list[tuple[str, str]] = [
    ("Developer", "email"),
    ("File", "path"),
    ("Module", "path"),
    ("Commit", "hash"),
    ("Snapshot", "snapshot_id"),
    ("ModuleSnapshot", "snapshot_id"),
    ("Repository", "name"),
]


def setup_schema(db: DatabaseManager) -> None:
    """Create indices for graph node labels."""
    for label, prop in INDICES:
        try:
            query = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
            db.query(query)
            logger.info("Created index on %s.%s", label, prop)
        except Exception as e:
            # Index may already exist — that's fine
            if "already indexed" in str(e).lower() or "already exists" in str(e).lower():
                logger.debug("Index on %s.%s already exists", label, prop)
            else:
                logger.warning("Could not create index on %s.%s: %s", label, prop, e)


def verify_schema(db: DatabaseManager) -> dict[str, int]:
    """Return counts of each node type to verify graph health."""
    counts: dict[str, int] = {}
    for label in ["Developer", "File", "Module", "Commit", "Snapshot", "Repository"]:
        result = db.query(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        counts[label] = result.result_set[0][0] if result.result_set else 0
    return counts
