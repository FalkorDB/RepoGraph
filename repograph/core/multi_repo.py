"""Multi-repo support — analyze multiple repositories into one graph.

Adds a Repository node and links all files, commits, and developers
to their source repository. Enables cross-repo queries like finding
shared developers and cross-repo experts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from repograph.core.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class RepoInfo:
    """Summary of a repository in the graph."""

    name: str
    path: str
    url: str
    developer_count: int
    file_count: int
    commit_count: int


@dataclass
class CrossRepoExpert:
    """A developer with expertise across multiple repositories."""

    name: str
    email: str
    repo_count: int
    repos: list[str]
    total_score: float


def register_repository(
    db: DatabaseManager,
    name: str,
    path: str = "",
    url: str = "",
) -> None:
    """Create or update a Repository node in the graph."""
    db.query(
        "MERGE (r:Repository {name: $name}) "
        "SET r.path = $path, r.url = $url",
        params={"name": name, "path": path, "url": url},
    )
    logger.info("Registered repository: %s", name)


def tag_graph_with_repo(db: DatabaseManager, repo_name: str) -> dict[str, int]:
    """Tag all untagged File and Commit nodes with a repository.

    This is called after build_graph() to associate nodes with a repo.
    Only tags nodes that don't already have a repo property.
    """
    stats = {"files": 0, "commits": 0}

    # Tag untagged files
    result = db.query(
        "MATCH (f:File) WHERE f.repository IS NULL "
        "SET f.repository = $repo "
        "RETURN count(f)",
        params={"repo": repo_name},
    )
    if result.result_set:
        stats["files"] = result.result_set[0][0]

    # Tag untagged commits
    result = db.query(
        "MATCH (c:Commit) WHERE c.repository IS NULL "
        "SET c.repository = $repo "
        "RETURN count(c)",
        params={"repo": repo_name},
    )
    if result.result_set:
        stats["commits"] = result.result_set[0][0]

    # Create BELONGS_TO relationships
    db.query(
        "MATCH (f:File {repository: $repo}), (r:Repository {name: $repo}) "
        "MERGE (f)-[:BELONGS_TO]->(r)",
        params={"repo": repo_name},
    )

    db.query(
        "MATCH (c:Commit {repository: $repo}), (r:Repository {name: $repo}) "
        "MERGE (c)-[:IN_REPO]->(r)",
        params={"repo": repo_name},
    )

    logger.info("Tagged %d files and %d commits with repo '%s'", stats["files"], stats["commits"], repo_name)
    return stats


def list_repositories(db: DatabaseManager) -> list[RepoInfo]:
    """List all repositories in the graph with stats."""
    result = db.query(
        "MATCH (r:Repository) "
        "OPTIONAL MATCH (f:File)-[:BELONGS_TO]->(r) "
        "OPTIONAL MATCH (c:Commit)-[:IN_REPO]->(r) "
        "OPTIONAL MATCH (d:Developer)-[:AUTHORED]->(c2:Commit)-[:IN_REPO]->(r) "
        "RETURN r.name, r.path, r.url, "
        "count(DISTINCT d) AS devs, count(DISTINCT f) AS files, count(DISTINCT c) AS commits "
        "ORDER BY r.name"
    )

    repos: list[RepoInfo] = []
    if result.result_set:
        for row in result.result_set:
            repos.append(
                RepoInfo(
                    name=row[0],
                    path=row[1] or "",
                    url=row[2] or "",
                    developer_count=row[3],
                    file_count=row[4],
                    commit_count=row[5],
                )
            )

    return repos


def query_cross_repo_experts(
    db: DatabaseManager,
    min_repos: int = 2,
    min_score: float = 0.5,
) -> list[CrossRepoExpert]:
    """Find developers with expertise across multiple repositories.

    This is a powerful cross-repo graph query: Developer → KNOWS → File → BELONGS_TO → Repository.
    It identifies people who bridge knowledge across repos — critical for organizations
    with microservices or multi-repo architectures.
    """
    result = db.query(
        "MATCH (d:Developer)-[k:KNOWS]->(f:File)-[:BELONGS_TO]->(r:Repository) "
        "WHERE k.score >= $min_score "
        "WITH d, r, sum(k.score) AS repo_score "
        "WITH d, collect(r.name) AS repos, sum(repo_score) AS total "
        "WHERE size(repos) >= $min_repos "
        "RETURN d.name, d.email, size(repos), repos, total "
        "ORDER BY size(repos) DESC, total DESC",
        params={"min_repos": min_repos, "min_score": min_score},
    )

    experts: list[CrossRepoExpert] = []
    if result.result_set:
        for row in result.result_set:
            experts.append(
                CrossRepoExpert(
                    name=row[0],
                    email=row[1],
                    repo_count=row[2],
                    repos=row[3] if isinstance(row[3], list) else [],
                    total_score=round(row[4], 2),
                )
            )

    return experts


def query_repo_summary(db: DatabaseManager, repo_name: str) -> dict:
    """Get summary for a specific repository."""
    result = db.query(
        "MATCH (f:File {repository: $repo})-[:PART_OF]->(m:Module) "
        "WITH count(DISTINCT f) AS files, count(DISTINCT m) AS modules "
        "OPTIONAL MATCH (c:Commit {repository: $repo}) "
        "WITH files, modules, count(DISTINCT c) AS commits "
        "OPTIONAL MATCH (d:Developer)-[:AUTHORED]->(c2:Commit {repository: $repo}) "
        "RETURN count(DISTINCT d) AS devs, files, modules, commits",
        params={"repo": repo_name},
    )

    if result.result_set and result.result_set[0]:
        row = result.result_set[0]
        return {
            "repository": repo_name,
            "developers": row[0],
            "files": row[1],
            "modules": row[2],
            "commits": row[3],
        }
    return {"repository": repo_name, "developers": 0, "files": 0, "modules": 0, "commits": 0}
