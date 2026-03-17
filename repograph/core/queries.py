"""Core Cypher queries — the graph intelligence engine for RepoGraph.

Each function executes one or more Cypher queries against FalkorDB and returns
structured results. All queries use parameterized inputs to prevent injection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from repograph.core.database import DatabaseManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------


@dataclass
class BusFactorResult:
    """Bus factor report for a module."""

    module: str
    bus_factor: int
    experts: list[dict[str, float]]  # [{name, email, score}]
    file_count: int


@dataclass
class BlastRadiusResult:
    """Blast radius of changing a file."""

    source_file: str
    affected_files: list[dict[str, int | str]]  # [{path, distance, frequency}]
    affected_modules: list[str]


@dataclass
class ReviewerResult:
    """Recommended reviewer for a file."""

    name: str
    email: str
    score: float
    commit_count: int


@dataclass
class KnowledgeSiloResult:
    """A module that is a knowledge silo."""

    module: str
    expert_count: int
    experts: list[str]
    file_count: int
    risk_level: str  # "critical", "warning", "ok"


@dataclass
class CouplingResult:
    """Coupling between two modules."""

    module_a: str
    module_b: str
    coupling_strength: int
    shared_files: int


@dataclass
class RiskResult:
    """Risk assessment for a module."""

    module: str
    bus_factor: int
    change_frequency: int
    risk_score: float
    risk_level: str


@dataclass
class DeveloperOverlap:
    """Knowledge overlap between two developers."""

    dev_a: str
    dev_b: str
    shared_files: int
    overlap_score: float


# ---------------------------------------------------------------------------
# Query implementations
# ---------------------------------------------------------------------------


def query_bus_factor(
    db: DatabaseManager,
    module: str | None = None,
    min_score: float = 0.5,
) -> list[BusFactorResult]:
    """Compute bus factor per module.

    Bus factor = number of developers with meaningful knowledge of a module.
    Uses variable-length path: Developer -[:KNOWS]-> File -[:PART_OF]-> Module

    This query aggregates developer expertise scores across all files in a module,
    which in SQL would require recursive CTEs to handle the module hierarchy.
    """
    if module:
        result = db.query(
            "MATCH (d:Developer)-[k:KNOWS]->(f:File)-[:PART_OF]->(m:Module {path: $module}) "
            "WHERE k.score >= $min_score "
            "WITH m, d, sum(k.score) AS total_score, count(f) AS files_known "
            "ORDER BY total_score DESC "
            "WITH m, collect({name: d.name, email: d.email, score: total_score, "
            "files: files_known}) AS experts "
            "MATCH (f2:File)-[:PART_OF]->(m) "
            "WITH m, experts, count(DISTINCT f2) AS file_count "
            "RETURN m.path, size(experts), experts, file_count",
            params={"module": module, "min_score": min_score},
        )
    else:
        result = db.query(
            "MATCH (d:Developer)-[k:KNOWS]->(f:File)-[:PART_OF]->(m:Module) "
            "WHERE k.score >= $min_score "
            "WITH m, d, sum(k.score) AS total_score, count(f) AS files_known "
            "ORDER BY total_score DESC "
            "WITH m, collect({name: d.name, email: d.email, score: total_score, "
            "files: files_known}) AS experts "
            "MATCH (f2:File)-[:PART_OF]->(m) "
            "WITH m, experts, count(DISTINCT f2) AS file_count "
            "RETURN m.path, size(experts), experts, file_count "
            "ORDER BY size(experts) ASC",
            params={"min_score": min_score},
        )

    results: list[BusFactorResult] = []
    if result.result_set:
        for row in result.result_set:
            mod_path, bf, experts, fc = row
            results.append(
                BusFactorResult(
                    module=mod_path,
                    bus_factor=bf,
                    experts=experts if isinstance(experts, list) else [],
                    file_count=fc,
                )
            )

    return results


def query_blast_radius(
    db: DatabaseManager,
    file_path: str,
    max_depth: int = 3,
) -> BlastRadiusResult:
    """Compute the blast radius of changing a file.

    Uses variable-length path traversal: File -[:CO_CHANGED_WITH*1..N]-> File
    This is the quintessential graph query — finding all transitively co-changed
    files within N hops. In SQL, this would require N self-joins or recursive CTEs.
    """
    # Note: FalkorDB doesn't support parameterized variable-length bounds,
    # so we inline the depth (validated integer) directly into the query.
    result = db.query(
        f"MATCH path = (source:File {{path: $path}})"
        f"-[:CO_CHANGED_WITH*1..{int(max_depth)}]-(target:File) "
        "WHERE source <> target "
        "WITH target, min(length(path)) AS distance "
        "RETURN target.path, distance "
        "ORDER BY distance, target.path",
        params={"path": file_path},
    )

    affected: list[dict[str, int | str]] = []
    if result.result_set:
        for row in result.result_set:
            affected.append({"path": row[0], "distance": row[1]})

    # Find affected modules
    module_result = db.query(
        f"MATCH path = (source:File {{path: $path}})"
        f"-[:CO_CHANGED_WITH*1..{int(max_depth)}]-(target:File)"
        "-[:PART_OF]->(m:Module) "
        "WHERE source <> target "
        "RETURN DISTINCT m.path "
        "ORDER BY m.path",
        params={"path": file_path},
    )

    modules: list[str] = []
    if module_result.result_set:
        modules = [row[0] for row in module_result.result_set]

    return BlastRadiusResult(
        source_file=file_path,
        affected_files=affected,
        affected_modules=modules,
    )


def query_reviewers(
    db: DatabaseManager,
    file_path: str,
    limit: int = 5,
) -> list[ReviewerResult]:
    """Find the best reviewers for a file based on knowledge graph.

    Ranks developers by their KNOWS score for the given file.
    """
    result = db.query(
        "MATCH (d:Developer)-[k:KNOWS]->(f:File {path: $path}) "
        "RETURN d.name, d.email, k.score, k.commit_count "
        "ORDER BY k.score DESC "
        "LIMIT $limit",
        params={"path": file_path, "limit": limit},
    )

    reviewers: list[ReviewerResult] = []
    if result.result_set:
        for row in result.result_set:
            reviewers.append(
                ReviewerResult(
                    name=row[0],
                    email=row[1],
                    score=row[2],
                    commit_count=row[3],
                )
            )

    return reviewers


def query_knowledge_silos(
    db: DatabaseManager,
    max_experts: int = 2,
    min_score: float = 0.5,
) -> list[KnowledgeSiloResult]:
    """Find modules that are knowledge silos (known by very few developers).

    This is an aggregation over subgraphs — for each module, traverse all files,
    find all knowledgeable developers, and flag modules below the threshold.
    """
    result = db.query(
        "MATCH (m:Module)<-[:PART_OF]-(f:File) "
        "OPTIONAL MATCH (d:Developer)-[k:KNOWS]->(f) "
        "WHERE k.score >= $min_score "
        "WITH m, collect(DISTINCT f.path) AS files, collect(DISTINCT d.name) AS experts "
        "WHERE size(experts) <= $max_experts "
        "RETURN m.path, size(experts), experts, size(files) "
        "ORDER BY size(experts) ASC, size(files) DESC",
        params={"max_experts": max_experts, "min_score": min_score},
    )

    silos: list[KnowledgeSiloResult] = []
    if result.result_set:
        for row in result.result_set:
            expert_count = row[1]
            risk = "critical" if expert_count <= 1 else "warning"
            silos.append(
                KnowledgeSiloResult(
                    module=row[0],
                    expert_count=expert_count,
                    experts=row[2] if isinstance(row[2], list) else [],
                    file_count=row[3],
                    risk_level=risk,
                )
            )

    return silos


def query_module_coupling(
    db: DatabaseManager,
    min_strength: int = 3,
) -> list[CouplingResult]:
    """Find implicitly coupled modules based on co-change patterns.

    This query crosses module boundaries — files in different modules that are
    frequently changed together indicate implicit coupling. Requires aggregating
    co-change relationships across module boundaries (cross-subgraph aggregation).
    """
    result = db.query(
        "MATCH (f1:File)-[r:CO_CHANGED_WITH]->(f2:File), "
        "(f1)-[:PART_OF]->(m1:Module), (f2)-[:PART_OF]->(m2:Module) "
        "WHERE m1 <> m2 "
        "WITH m1, m2, sum(r.frequency) AS coupling, count(DISTINCT f1) + count(DISTINCT f2) AS files "
        "WHERE coupling >= $min_strength "
        "RETURN m1.path, m2.path, coupling, files "
        "ORDER BY coupling DESC",
        params={"min_strength": min_strength},
    )

    couplings: list[CouplingResult] = []
    seen: set[tuple[str, str]] = set()
    if result.result_set:
        for row in result.result_set:
            pair = (min(row[0], row[1]), max(row[0], row[1]))
            if pair not in seen:
                seen.add(pair)
                couplings.append(
                    CouplingResult(
                        module_a=pair[0],
                        module_b=pair[1],
                        coupling_strength=row[2],
                        shared_files=row[3],
                    )
                )

    return couplings


def query_risk_hotspots(
    db: DatabaseManager,
    min_score: float = 0.5,
) -> list[RiskResult]:
    """Identify high-risk modules by combining bus factor with change frequency.

    Risk = (1 / bus_factor) × change_frequency
    This is the most complex query: it combines subgraph aggregation (bus factor)
    with temporal aggregation (change frequency) across the entire graph.
    """
    result = db.query(
        "MATCH (m:Module)<-[:PART_OF]-(f:File)<-[:MODIFIED]-(c:Commit) "
        "WITH m, count(DISTINCT c) AS change_freq "
        "MATCH (d:Developer)-[k:KNOWS]->(f2:File)-[:PART_OF]->(m) "
        "WHERE k.score >= $min_score "
        "WITH m, change_freq, count(DISTINCT d) AS bus_factor "
        "WITH m, bus_factor, change_freq, "
        "toFloat(change_freq) / CASE WHEN bus_factor = 0 THEN 1 ELSE bus_factor END AS risk "
        "RETURN m.path, bus_factor, change_freq, risk "
        "ORDER BY risk DESC",
        params={"min_score": min_score},
    )

    risks: list[RiskResult] = []
    if result.result_set:
        for row in result.result_set:
            risk_val = row[3]
            if risk_val >= 10:
                level = "critical"
            elif risk_val >= 5:
                level = "high"
            elif risk_val >= 2:
                level = "medium"
            else:
                level = "low"

            risks.append(
                RiskResult(
                    module=row[0],
                    bus_factor=row[1],
                    change_frequency=row[2],
                    risk_score=round(risk_val, 2),
                    risk_level=level,
                )
            )

    return risks


def query_developer_overlap(
    db: DatabaseManager,
    min_shared: int = 3,
) -> list[DeveloperOverlap]:
    """Find knowledge overlap between pairs of developers.

    Bipartite pattern matching: Dev1 -[:KNOWS]-> File <-[:KNOWS]- Dev2
    This reveals which developers could cover for each other.
    """
    result = db.query(
        "MATCH (d1:Developer)-[:KNOWS]->(f:File)<-[:KNOWS]-(d2:Developer) "
        "WHERE d1.email < d2.email "
        "WITH d1, d2, count(f) AS shared, "
        "sum(1.0) AS raw_overlap "
        "WHERE shared >= $min_shared "
        "RETURN d1.name, d2.name, shared, raw_overlap "
        "ORDER BY shared DESC",
        params={"min_shared": min_shared},
    )

    overlaps: list[DeveloperOverlap] = []
    if result.result_set:
        for row in result.result_set:
            overlaps.append(
                DeveloperOverlap(
                    dev_a=row[0],
                    dev_b=row[1],
                    shared_files=row[2],
                    overlap_score=round(row[3], 2),
                )
            )

    return overlaps


def query_graph_summary(db: DatabaseManager) -> dict:
    """Get a summary of the current graph state."""
    result = db.query(
        "MATCH (d:Developer) WITH count(d) AS devs "
        "MATCH (f:File) WITH devs, count(f) AS files "
        "MATCH (m:Module) WITH devs, files, count(m) AS mods "
        "MATCH (c:Commit) WITH devs, files, mods, count(c) AS commits "
        "RETURN devs, files, mods, commits"
    )

    if result.result_set and result.result_set[0]:
        row = result.result_set[0]
        return {
            "developers": row[0],
            "files": row[1],
            "modules": row[2],
            "commits": row[3],
        }
    return {"developers": 0, "files": 0, "modules": 0, "commits": 0}
