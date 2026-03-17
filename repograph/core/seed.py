"""Seed data generator — creates a realistic demo graph for testing and demos."""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from repograph.core.database import DatabaseManager

logger = logging.getLogger(__name__)

# Realistic developer names and emails
DEVELOPERS = [
    ("Alice Chen", "alice@example.com"),
    ("Bob Martinez", "bob@example.com"),
    ("Carol Singh", "carol@example.com"),
    ("David Kim", "david@example.com"),
    ("Eve Johnson", "eve@example.com"),
    ("Frank Weber", "frank@example.com"),
    ("Grace Liu", "grace@example.com"),
    ("Henry Brown", "henry@example.com"),
]

# Realistic project file structure
FILES = {
    "src/api": [
        "src/api/routes.py",
        "src/api/middleware.py",
        "src/api/auth.py",
        "src/api/validators.py",
        "src/api/serializers.py",
    ],
    "src/core": [
        "src/core/engine.py",
        "src/core/processor.py",
        "src/core/pipeline.py",
        "src/core/scheduler.py",
        "src/core/cache.py",
    ],
    "src/models": [
        "src/models/user.py",
        "src/models/project.py",
        "src/models/task.py",
        "src/models/base.py",
    ],
    "src/services": [
        "src/services/email.py",
        "src/services/notifications.py",
        "src/services/billing.py",
        "src/services/analytics.py",
    ],
    "src/utils": [
        "src/utils/helpers.py",
        "src/utils/logging.py",
        "src/utils/config.py",
        "src/utils/crypto.py",
    ],
    "tests": [
        "tests/test_api.py",
        "tests/test_core.py",
        "tests/test_models.py",
        "tests/test_services.py",
    ],
    "docs": [
        "docs/api.md",
        "docs/architecture.md",
        "docs/deployment.md",
    ],
    "infra": [
        "infra/docker-compose.yml",
        "infra/Dockerfile",
        "infra/nginx.conf",
    ],
}

# Expertise mapping: developer -> primary modules they work on
EXPERTISE_MAP: dict[str, list[str]] = {
    "alice@example.com": ["src/api", "src/models"],
    "bob@example.com": ["src/core", "src/utils"],
    "carol@example.com": ["src/core", "src/services"],
    "david@example.com": ["src/api", "src/services", "infra"],
    "eve@example.com": ["src/models", "tests"],
    "frank@example.com": ["infra", "docs"],
    "grace@example.com": ["src/core", "src/api", "src/models"],
    "henry@example.com": ["tests", "docs"],
}


def generate_seed_data(db: DatabaseManager, num_commits: int = 300) -> dict[str, int]:
    """Generate realistic seed data in the graph.

    Creates a simulated project with realistic patterns:
    - Developers have specializations (knowledge silos)
    - Some modules have low bus factor (risky)
    - Files that are commonly changed together (co-changes)
    - Varying levels of activity across the codebase
    """
    logger.info("Generating seed data with %d commits...", num_commits)
    random.seed(42)  # Reproducible results

    stats: dict[str, int] = {"developers": 0, "files": 0, "modules": 0, "commits": 0}

    # Create developer nodes
    for name, email in DEVELOPERS:
        db.query(
            "MERGE (d:Developer {email: $email}) SET d.name = $name",
            params={"email": email, "name": name},
        )
        stats["developers"] += 1

    # Create module and file nodes
    all_files: list[str] = []
    for module_path, files in FILES.items():
        # Create module node
        parts = module_path.split("/")
        for i in range(len(parts)):
            mpath = "/".join(parts[: i + 1])
            mname = parts[i]
            db.query(
                "MERGE (m:Module {path: $path}) SET m.name = $name, m.depth = $depth",
                params={"path": mpath, "name": mname, "depth": i},
            )
            stats["modules"] += 1

        # Create CHILD_OF relationships
        for i in range(1, len(parts)):
            child_path = "/".join(parts[: i + 1])
            parent_path = "/".join(parts[:i])
            db.query(
                "MATCH (c:Module {path: $cpath}), (p:Module {path: $ppath}) "
                "MERGE (c)-[:CHILD_OF]->(p)",
                params={"cpath": child_path, "ppath": parent_path},
            )

        for filepath in files:
            ext = "." + filepath.rsplit(".", 1)[-1] if "." in filepath else ""
            lang_map = {
                ".py": "Python",
                ".md": "Markdown",
                ".yml": "YAML",
                ".conf": "Config",
            }
            lang = lang_map.get(ext, "Other")
            db.query(
                "MERGE (f:File {path: $path}) "
                "SET f.extension = $ext, f.language = $lang",
                params={"path": filepath, "ext": ext, "lang": lang},
            )
            # Link file to module
            db.query(
                "MATCH (f:File {path: $fpath}), (m:Module {path: $mpath}) "
                "MERGE (f)-[:PART_OF]->(m)",
                params={"fpath": filepath, "mpath": module_path},
            )
            all_files.append(filepath)
            stats["files"] += 1

    # Generate commits with realistic patterns
    base_ts = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    dev_emails = [email for _, email in DEVELOPERS]

    for i in range(num_commits):
        # Pick a developer (weighted towards active ones)
        dev_email = random.choice(dev_emails)
        dev_modules = EXPERTISE_MAP.get(dev_email, ["src/utils"])

        # Pick files from developer's expertise area (80% chance) or random (20%)
        num_files = random.randint(1, 5)
        commit_files: list[str] = []
        for _ in range(num_files):
            if random.random() < 0.8:
                # From expertise area
                mod = random.choice(dev_modules)
                mod_files = FILES.get(mod, [])
                if mod_files:
                    commit_files.append(random.choice(mod_files))
            else:
                commit_files.append(random.choice(all_files))

        commit_files = list(set(commit_files))  # Deduplicate
        if not commit_files:
            continue

        commit_hash = f"seed_{i:06d}"
        ts = base_ts + i * 3600  # One commit per hour
        additions = random.randint(5, 200)
        deletions = random.randint(0, 100)

        messages = [
            "Fix bug in request handling",
            "Add new feature for user analytics",
            "Refactor core processing pipeline",
            "Update configuration management",
            "Improve error handling",
            "Add unit tests",
            "Update documentation",
            "Fix performance issue in scheduler",
            "Add billing integration",
            "Refactor middleware stack",
        ]

        db.query(
            "MERGE (c:Commit {hash: $hash}) "
            "SET c.message = $msg, c.timestamp = $ts, "
            "c.additions = $adds, c.deletions = $dels",
            params={
                "hash": commit_hash,
                "msg": random.choice(messages),
                "ts": ts,
                "adds": additions,
                "dels": deletions,
            },
        )

        # AUTHORED relationship
        db.query(
            "MATCH (d:Developer {email: $email}), (c:Commit {hash: $hash}) "
            "MERGE (d)-[:AUTHORED {timestamp: $ts}]->(c)",
            params={"email": dev_email, "hash": commit_hash, "ts": ts},
        )

        # MODIFIED relationships
        for filepath in commit_files:
            db.query(
                "MATCH (c:Commit {hash: $hash}), (f:File {path: $path}) "
                "MERGE (c)-[:MODIFIED {additions: $adds, deletions: $dels}]->(f)",
                params={
                    "hash": commit_hash,
                    "path": filepath,
                    "adds": random.randint(1, 50),
                    "dels": random.randint(0, 30),
                },
            )

        stats["commits"] += 1

    # Compute KNOWS relationships
    logger.info("Computing knowledge scores for seed data...")
    _compute_seed_knowledge(db)

    # Compute CO_CHANGED_WITH relationships
    logger.info("Computing co-change relationships for seed data...")
    _compute_seed_co_changes(db)

    logger.info("Seed data generation complete: %s", stats)
    return stats


def _compute_seed_knowledge(db: DatabaseManager) -> None:
    """Compute KNOWS relationships from seed commit data."""
    result = db.query(
        "MATCH (d:Developer)-[:AUTHORED]->(c:Commit)-[:MODIFIED]->(f:File) "
        "RETURN d.email, f.path, count(c) AS commits, max(c.timestamp) AS last_ts"
    )

    if not result.result_set:
        return

    for row in result.result_set:
        email, path, commits, last_ts = row
        # Simple scoring: commit count weighted by a base factor
        score = round(min(commits * 0.4 + 0.2, 10.0), 3)
        db.query(
            "MATCH (d:Developer {email: $email}), (f:File {path: $path}) "
            "MERGE (d)-[k:KNOWS]->(f) "
            "SET k.score = $score, k.last_touched = $last_ts, k.commit_count = $commits",
            params={"email": email, "path": path, "score": score, "commits": commits, "last_ts": last_ts},
        )


def _compute_seed_co_changes(db: DatabaseManager) -> None:
    """Compute CO_CHANGED_WITH from seed commits."""
    result = db.query(
        "MATCH (c:Commit)-[:MODIFIED]->(f1:File), (c)-[:MODIFIED]->(f2:File) "
        "WHERE f1.path < f2.path "
        "WITH f1, f2, count(c) AS freq, max(c.timestamp) AS last_ts "
        "WHERE freq >= 2 "
        "RETURN f1.path, f2.path, freq, last_ts"
    )

    if not result.result_set:
        return

    for row in result.result_set:
        db.query(
            "MATCH (f1:File {path: $p1}), (f2:File {path: $p2}) "
            "MERGE (f1)-[r:CO_CHANGED_WITH]->(f2) "
            "SET r.frequency = $freq, r.last_co_change = $ts",
            params={"p1": row[0], "p2": row[1], "freq": row[2], "ts": row[3]},
        )
