"""Graph builder — populates FalkorDB from git analysis results."""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import UTC, datetime

from repograph.core.config import AnalysisConfig
from repograph.core.database import DatabaseManager
from repograph.core.git_analyzer import AnalysisResult

logger = logging.getLogger(__name__)


def _infer_language(extension: str) -> str:
    """Map file extension to language name."""
    mapping = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".jsx": "JavaScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".c": "C",
        ".h": "C",
        ".cpp": "C++",
        ".rb": "Ruby",
        ".php": "PHP",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".cs": "C#",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".json": "JSON",
        ".toml": "TOML",
        ".md": "Markdown",
        ".sh": "Shell",
        ".sql": "SQL",
        ".html": "HTML",
        ".css": "CSS",
        ".scss": "SCSS",
    }
    return mapping.get(extension, "Other")


def _extract_module(filepath: str, depth: int) -> list[tuple[str, str, int]]:
    """Extract module hierarchy from a file path.

    Returns list of (module_name, module_path, depth) tuples.
    E.g., for 'src/core/utils.py' with depth=2:
      [('src', 'src', 0), ('src/core', 'src/core', 1)]
    """
    parts = filepath.split("/")
    modules: list[tuple[str, str, int]] = []
    for i in range(min(depth, len(parts) - 1)):
        module_path = "/".join(parts[: i + 1])
        modules.append((parts[i], module_path, i))
    return modules


def build_graph(
    db: DatabaseManager,
    analysis: AnalysisResult,
    config: AnalysisConfig | None = None,
) -> dict[str, int]:
    """Build the complete graph from analysis results.

    Returns a dict of counts: nodes created, relationships created, etc.
    """
    config = config or AnalysisConfig()
    stats: dict[str, int] = defaultdict(int)
    now = datetime.now(tz=UTC)

    logger.info("Building graph from %d commits...", len(analysis.commits))

    # Phase 1: Create Developer nodes
    for email, name in analysis.developers.items():
        db.query(
            "MERGE (d:Developer {email: $email}) "
            "ON CREATE SET d.name = $name "
            "ON MATCH SET d.name = $name",
            params={"email": email, "name": name},
        )
        stats["developers"] += 1

    logger.info("Created %d developer nodes", stats["developers"])

    # Phase 2: Create File nodes and Module nodes
    seen_modules: set[str] = set()
    for filepath in analysis.files:
        ext = ""
        if "." in filepath.split("/")[-1]:
            ext = "." + filepath.split("/")[-1].rsplit(".", 1)[-1]
        language = _infer_language(ext)

        db.query(
            "MERGE (f:File {path: $path}) ON CREATE SET f.extension = $ext, f.language = $language",
            params={"path": filepath, "ext": ext, "language": language},
        )
        stats["files"] += 1

        # Create module hierarchy
        modules = _extract_module(filepath, config.module_depth)
        for mod_name, mod_path, depth in modules:
            if mod_path not in seen_modules:
                db.query(
                    "MERGE (m:Module {path: $path}) ON CREATE SET m.name = $name, m.depth = $depth",
                    params={"path": mod_path, "name": mod_name, "depth": depth},
                )
                seen_modules.add(mod_path)
                stats["modules"] += 1

        # Link file to its immediate parent module
        if modules:
            _, parent_path, _ = modules[-1]
            db.query(
                "MATCH (f:File {path: $fpath}), (m:Module {path: $mpath}) "
                "MERGE (f)-[:PART_OF]->(m)",
                params={"fpath": filepath, "mpath": parent_path},
            )

    # Create CHILD_OF relationships between modules
    for mod_path in seen_modules:
        parts = mod_path.split("/")
        if len(parts) > 1:
            parent_path = "/".join(parts[:-1])
            if parent_path in seen_modules:
                db.query(
                    "MATCH (child:Module {path: $cpath}), (parent:Module {path: $ppath}) "
                    "MERGE (child)-[:CHILD_OF]->(parent)",
                    params={"cpath": mod_path, "ppath": parent_path},
                )

    logger.info("Created %d file nodes, %d module nodes", stats["files"], stats["modules"])

    # Phase 3: Create Commit nodes and relationships
    for commit in analysis.commits:
        ts_epoch = int(commit.timestamp.timestamp())
        db.query(
            "MERGE (c:Commit {hash: $hash}) "
            "ON CREATE SET c.message = $msg, c.timestamp = $ts, "
            "c.additions = $adds, c.deletions = $dels",
            params={
                "hash": commit.hash,
                "msg": commit.message[:200],
                "ts": ts_epoch,
                "adds": sum(f.additions for f in commit.files),
                "dels": sum(f.deletions for f in commit.files),
            },
        )

        # AUTHORED relationship
        db.query(
            "MATCH (d:Developer {email: $email}), (c:Commit {hash: $hash}) "
            "MERGE (d)-[:AUTHORED {timestamp: $ts}]->(c)",
            params={"email": commit.author_email, "hash": commit.hash, "ts": ts_epoch},
        )

        # MODIFIED relationships
        for fc in commit.files:
            if fc.change_type == "D":
                continue
            db.query(
                "MATCH (c:Commit {hash: $hash}), (f:File {path: $path}) "
                "MERGE (c)-[:MODIFIED {additions: $adds, deletions: $dels}]->(f)",
                params={
                    "hash": commit.hash,
                    "path": fc.path,
                    "adds": fc.additions,
                    "dels": fc.deletions,
                },
            )

        stats["commits"] += 1
        if stats["commits"] % 200 == 0:
            logger.info("Processed %d/%d commits...", stats["commits"], len(analysis.commits))

    logger.info("Created %d commit nodes", stats["commits"])

    # Phase 4: Compute KNOWS relationships (developer expertise per file)
    logger.info("Computing developer knowledge scores...")
    _compute_knowledge_scores(db, config, now)

    # Phase 5: Compute CO_CHANGED_WITH relationships
    logger.info("Computing co-change relationships...")
    co_change_count = _compute_co_changes(db, analysis)
    stats["co_changes"] = co_change_count

    logger.info("Graph build complete: %s", dict(stats))
    return dict(stats)


def _compute_knowledge_scores(
    db: DatabaseManager,
    config: AnalysisConfig,
    now: datetime,
) -> None:
    """Compute KNOWS relationships between developers and files.

    Knowledge score factors:
    - Number of commits touching the file
    - Recency of changes (exponential decay)
    - Volume of changes (additions + deletions)
    """
    now_epoch = int(now.timestamp())
    decay_seconds = config.knowledge_decay_days * 86400

    # For each developer-file pair, aggregate commit data
    result = db.query(
        "MATCH (d:Developer)-[:AUTHORED]->(c:Commit)-[:MODIFIED]->(f:File) "
        "RETURN d.email, f.path, count(c) AS commit_count, "
        "max(c.timestamp) AS last_touched, "
        "sum(c.additions) + sum(c.deletions) AS total_changes"
    )

    if not result.result_set:
        return

    for row in result.result_set:
        email, path, commit_count, last_touched, total_changes = row

        # Recency factor: exponential decay
        age_seconds = max(0, now_epoch - (last_touched or 0))
        recency = math.exp(-age_seconds / decay_seconds) if decay_seconds > 0 else 1.0

        # Volume factor: logarithmic to avoid overweighting large changes
        volume = math.log1p(total_changes or 0)

        # Combined score
        score = round((commit_count * 0.5 + volume * 0.3) * recency + 0.2, 3)

        if score >= config.min_knowledge_score:
            db.query(
                "MATCH (d:Developer {email: $email}), (f:File {path: $path}) "
                "MERGE (d)-[k:KNOWS]->(f) "
                "SET k.score = $score, k.last_touched = $last_touched, "
                "k.commit_count = $commit_count",
                params={
                    "email": email,
                    "path": path,
                    "score": score,
                    "last_touched": last_touched,
                    "commit_count": commit_count,
                },
            )


def _compute_co_changes(db: DatabaseManager, analysis: AnalysisResult) -> int:
    """Compute CO_CHANGED_WITH relationships between files.

    Two files are co-changed if they appear in the same commit.
    Frequency counts how often this happens.
    """
    co_change_counts: dict[tuple[str, str], int] = defaultdict(int)
    co_change_last: dict[tuple[str, str], int] = {}

    for commit in analysis.commits:
        paths = [f.path for f in commit.files if f.change_type != "D"]
        # Only consider commits with reasonable number of files (skip mega-commits)
        if len(paths) < 2 or len(paths) > 50:
            continue

        ts = int(commit.timestamp.timestamp())
        for i, p1 in enumerate(paths):
            for p2 in paths[i + 1 :]:
                key = (min(p1, p2), max(p1, p2))
                co_change_counts[key] += 1
                co_change_last[key] = max(co_change_last.get(key, 0), ts)

    # Only persist co-changes with frequency >= 2
    count = 0
    for (p1, p2), freq in co_change_counts.items():
        if freq < 2:
            continue
        last_ts = co_change_last[(p1, p2)]
        db.query(
            "MATCH (f1:File {path: $p1}), (f2:File {path: $p2}) "
            "MERGE (f1)-[r:CO_CHANGED_WITH]->(f2) "
            "SET r.frequency = $freq, r.last_co_change = $ts",
            params={"p1": p1, "p2": p2, "freq": freq, "ts": last_ts},
        )
        count += 1

    logger.info("Created %d co-change relationships", count)
    return count
