"""GitHub integration — pull PR review data and use as knowledge signal."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass

from repograph.core.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class PRReview:
    """A pull request review from GitHub."""

    pr_number: int
    reviewer_email: str
    reviewer_name: str
    files_reviewed: list[str]
    state: str  # "APPROVED", "CHANGES_REQUESTED", "COMMENTED"
    submitted_at: str


def fetch_pr_reviews(
    repo: str,
    limit: int = 50,
) -> list[PRReview]:
    """Fetch recent PR reviews using the GitHub CLI (gh).

    Requires `gh` to be installed and authenticated.

    Args:
        repo: GitHub repo in owner/repo format (e.g., "FalkorDB/nova2").
        limit: Maximum number of PRs to fetch reviews from.

    Returns:
        List of PRReview objects.
    """
    reviews: list[PRReview] = []

    try:
        # List recent merged PRs
        pr_result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "merged",
                "--limit",
                str(limit),
                "--json",
                "number,files",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if pr_result.returncode != 0:
            logger.warning("Failed to fetch PRs: %s", pr_result.stderr)
            return reviews

        prs = json.loads(pr_result.stdout)

        for pr in prs:
            pr_number = pr["number"]
            pr_files = [f["path"] for f in pr.get("files", [])]

            # Fetch reviews for this PR
            review_result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr_number),
                    "--repo",
                    repo,
                    "--json",
                    "reviews",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if review_result.returncode != 0:
                continue

            review_data = json.loads(review_result.stdout)
            for review in review_data.get("reviews", []):
                author = review.get("author", {})
                reviews.append(
                    PRReview(
                        pr_number=pr_number,
                        reviewer_email=author.get("login", "") + "@github",
                        reviewer_name=author.get("login", "unknown"),
                        files_reviewed=pr_files,
                        state=review.get("state", "COMMENTED"),
                        submitted_at=review.get("submittedAt", ""),
                    )
                )

    except FileNotFoundError:
        logger.error("GitHub CLI (gh) not found. Install it: https://cli.github.com/")
    except subprocess.TimeoutExpired:
        logger.error("Timed out fetching PR reviews from GitHub")
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Error parsing GitHub response: %s", e)

    logger.info("Fetched %d PR reviews", len(reviews))
    return reviews


def integrate_reviews(db: DatabaseManager, reviews: list[PRReview]) -> dict[str, int]:
    """Integrate PR review data into the knowledge graph.

    Reviews boost a developer's KNOWS score for files they reviewed.
    Review-based knowledge is a strong signal — if someone reviewed code,
    they understand it.
    """
    stats = {"reviews_processed": 0, "knowledge_boosted": 0}
    review_weight = 0.3  # Weight of a review vs a commit

    for review in reviews:
        if review.state not in ("APPROVED", "CHANGES_REQUESTED"):
            continue

        for filepath in review.files_reviewed:
            # Check if the reviewer exists as a developer
            # Try matching by name since GitHub login != git email
            result = db.query(
                "MATCH (d:Developer) "
                "WHERE d.name = $name OR d.email CONTAINS $login "
                "MATCH (f:File {path: $path}) "
                "MERGE (d)-[k:KNOWS]->(f) "
                "ON CREATE SET k.score = $weight, k.commit_count = 0, k.last_touched = 0 "
                "ON MATCH SET k.score = k.score + $weight "
                "RETURN d.name",
                params={
                    "name": review.reviewer_name,
                    "login": review.reviewer_name,
                    "path": filepath,
                    "weight": review_weight,
                },
            )
            if result.result_set:
                stats["knowledge_boosted"] += 1

        stats["reviews_processed"] += 1

    logger.info("Integrated PR reviews: %s", stats)
    return stats
