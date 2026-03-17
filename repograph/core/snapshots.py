"""Temporal trend analysis — track how metrics evolve over time.

Takes point-in-time snapshots of key graph metrics (bus factor, silo count,
risk scores) and stores them as Snapshot nodes in the graph. Trend queries
compare snapshots to show whether code health is improving or degrading.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from repograph.core.database import DatabaseManager
from repograph.core.queries import (
    query_bus_factor,
    query_graph_summary,
    query_knowledge_silos,
    query_risk_hotspots,
)

logger = logging.getLogger(__name__)


@dataclass
class SnapshotSummary:
    """Point-in-time capture of graph health metrics."""

    snapshot_id: str
    timestamp: float
    developer_count: int
    module_count: int
    file_count: int
    commit_count: int
    avg_bus_factor: float
    silo_count: int
    high_risk_count: int


@dataclass
class ModuleSnapshotData:
    """Point-in-time metrics for a single module."""

    module: str
    bus_factor: int
    risk_score: float
    risk_level: str


@dataclass
class TrendPoint:
    """A single point in a metric trend over time."""

    timestamp: float
    value: float


@dataclass
class TrendResult:
    """Trend data for a metric over time."""

    metric: str
    points: list[TrendPoint] = field(default_factory=list)
    direction: str = "stable"  # "improving", "degrading", "stable"
    change_pct: float = 0.0


def take_snapshot(db: DatabaseManager, min_score: float = 0.5) -> SnapshotSummary:
    """Capture current graph metrics as a Snapshot node.

    Creates a Snapshot node with overall metrics, plus ModuleSnapshot nodes
    for per-module tracking over time.
    """
    snapshot_id = str(uuid.uuid4())[:8]
    ts = time.time()

    summary = query_graph_summary(db)
    bus_factors = query_bus_factor(db, min_score=min_score)
    silos = query_knowledge_silos(db, min_score=min_score)
    risks = query_risk_hotspots(db, min_score=min_score)

    avg_bf = (
        sum(r.bus_factor for r in bus_factors) / len(bus_factors) if bus_factors else 0.0
    )
    silo_count = len(silos)
    high_risk_count = sum(1 for r in risks if r.risk_level in ("critical", "high"))

    # Store the snapshot node
    db.query(
        "CREATE (s:Snapshot {"
        "  snapshot_id: $id, timestamp: $ts,"
        "  developer_count: $devs, module_count: $mods,"
        "  file_count: $files, commit_count: $commits,"
        "  avg_bus_factor: $avg_bf, silo_count: $silos,"
        "  high_risk_count: $high_risk"
        "})",
        params={
            "id": snapshot_id,
            "ts": ts,
            "devs": summary.get("developers", 0),
            "mods": summary.get("modules", 0),
            "files": summary.get("files", 0),
            "commits": summary.get("commits", 0),
            "avg_bf": round(avg_bf, 2),
            "silos": silo_count,
            "high_risk": high_risk_count,
        },
    )

    # Store per-module snapshots for detailed trends
    for r in risks:
        db.query(
            "CREATE (ms:ModuleSnapshot {"
            "  snapshot_id: $id, timestamp: $ts,"
            "  module: $mod, bus_factor: $bf,"
            "  risk_score: $risk, risk_level: $level"
            "})",
            params={
                "id": snapshot_id,
                "ts": ts,
                "mod": r.module,
                "bf": r.bus_factor,
                "risk": r.risk_score,
                "level": r.risk_level,
            },
        )

    logger.info(
        "Snapshot %s: avg_bf=%.1f, silos=%d, high_risk=%d",
        snapshot_id, avg_bf, silo_count, high_risk_count,
    )

    return SnapshotSummary(
        snapshot_id=snapshot_id,
        timestamp=ts,
        developer_count=summary.get("developers", 0),
        module_count=summary.get("modules", 0),
        file_count=summary.get("files", 0),
        commit_count=summary.get("commits", 0),
        avg_bus_factor=round(avg_bf, 2),
        silo_count=silo_count,
        high_risk_count=high_risk_count,
    )


def query_snapshot_history(
    db: DatabaseManager,
    limit: int = 30,
) -> list[SnapshotSummary]:
    """Retrieve snapshot history, most recent first."""
    result = db.query(
        "MATCH (s:Snapshot) "
        "RETURN s.snapshot_id, s.timestamp, s.developer_count, s.module_count, "
        "s.file_count, s.commit_count, s.avg_bus_factor, s.silo_count, "
        "s.high_risk_count "
        "ORDER BY s.timestamp DESC "
        "LIMIT $limit",
        params={"limit": limit},
    )

    snapshots: list[SnapshotSummary] = []
    if result.result_set:
        for row in result.result_set:
            snapshots.append(
                SnapshotSummary(
                    snapshot_id=row[0],
                    timestamp=row[1],
                    developer_count=row[2],
                    module_count=row[3],
                    file_count=row[4],
                    commit_count=row[5],
                    avg_bus_factor=row[6],
                    silo_count=row[7],
                    high_risk_count=row[8],
                )
            )

    return snapshots


def query_trends(
    db: DatabaseManager,
    limit: int = 30,
) -> dict[str, TrendResult]:
    """Compute trends for key metrics from snapshot history.

    Returns trends for: avg_bus_factor, silo_count, high_risk_count.
    Each trend includes direction (improving/degrading/stable) and change %.
    """
    snapshots = query_snapshot_history(db, limit=limit)

    if not snapshots:
        return {}

    # Snapshots are newest-first; reverse for chronological order
    snapshots = list(reversed(snapshots))

    metrics = {
        "avg_bus_factor": TrendResult(metric="avg_bus_factor"),
        "silo_count": TrendResult(metric="silo_count"),
        "high_risk_count": TrendResult(metric="high_risk_count"),
    }

    for snap in snapshots:
        metrics["avg_bus_factor"].points.append(
            TrendPoint(timestamp=snap.timestamp, value=snap.avg_bus_factor)
        )
        metrics["silo_count"].points.append(
            TrendPoint(timestamp=snap.timestamp, value=snap.silo_count)
        )
        metrics["high_risk_count"].points.append(
            TrendPoint(timestamp=snap.timestamp, value=snap.high_risk_count)
        )

    # Compute direction for each metric
    for name, trend in metrics.items():
        if len(trend.points) >= 2:
            first_val = trend.points[0].value
            last_val = trend.points[-1].value
            if first_val == 0:
                trend.change_pct = 100.0 if last_val > 0 else 0.0
            else:
                trend.change_pct = round(((last_val - first_val) / abs(first_val)) * 100, 1)

            # For bus factor: higher is better (improving)
            # For silos and risks: lower is better (improving)
            if name == "avg_bus_factor":
                if trend.change_pct > 5:
                    trend.direction = "improving"
                elif trend.change_pct < -5:
                    trend.direction = "degrading"
            else:
                if trend.change_pct < -5:
                    trend.direction = "improving"
                elif trend.change_pct > 5:
                    trend.direction = "degrading"

    return metrics


def query_module_trend(
    db: DatabaseManager,
    module: str,
    limit: int = 30,
) -> list[ModuleSnapshotData]:
    """Get historical trend for a specific module."""
    result = db.query(
        "MATCH (ms:ModuleSnapshot {module: $module}) "
        "RETURN ms.module, ms.bus_factor, ms.risk_score, ms.risk_level "
        "ORDER BY ms.timestamp ASC "
        "LIMIT $limit",
        params={"module": module, "limit": limit},
    )

    history: list[ModuleSnapshotData] = []
    if result.result_set:
        for row in result.result_set:
            history.append(
                ModuleSnapshotData(
                    module=row[0],
                    bus_factor=row[1],
                    risk_score=row[2],
                    risk_level=row[3],
                )
            )

    return history
