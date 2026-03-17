"""Git history parser — extracts commits, authors, and file changes from a repository."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import git as gitpython

from repograph.core.config import AnalysisConfig

logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    """A single file modification within a commit."""

    path: str
    additions: int
    deletions: int
    change_type: str  # 'A', 'M', 'D', 'R'


@dataclass
class CommitInfo:
    """Parsed information about a single git commit."""

    hash: str
    message: str
    author_name: str
    author_email: str
    timestamp: datetime
    files: list[FileChange] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Complete result of git history analysis."""

    repo_path: str
    commits: list[CommitInfo]
    developers: dict[str, str]  # email -> name
    files: set[str]
    total_commits_scanned: int


def _is_excluded(path: str, excluded: list[str]) -> bool:
    """Check if a file path matches any exclusion pattern."""
    parts = path.split("/")
    return any(exc in parts for exc in excluded)


def _parse_diff_stats(commit: gitpython.Commit) -> list[FileChange]:
    """Extract file changes from a commit's diff."""
    changes: list[FileChange] = []
    try:
        if not commit.parents:
            # Initial commit — diff against empty tree
            diffs = commit.diff(gitpython.NULL_TREE, create_patch=False)
        else:
            diffs = commit.parents[0].diff(commit, create_patch=False)

        for diff in diffs:
            path = diff.b_path or diff.a_path
            if not path:
                continue

            change_type = "M"
            if diff.new_file:
                change_type = "A"
            elif diff.deleted_file:
                change_type = "D"
            elif diff.renamed_file:
                change_type = "R"

            changes.append(
                FileChange(
                    path=path,
                    additions=0,
                    deletions=0,
                    change_type=change_type,
                )
            )
    except Exception as e:
        logger.debug("Could not parse diff for %s: %s", commit.hexsha[:8], e)

    return changes


def _extract_numstat(commit: gitpython.Commit) -> dict[str, tuple[int, int]]:
    """Extract line addition/deletion counts per file."""
    stats: dict[str, tuple[int, int]] = {}
    try:
        if commit.stats and commit.stats.files:
            for filepath, stat in commit.stats.files.items():
                stats[filepath] = (stat.get("insertions", 0), stat.get("deletions", 0))
    except Exception as e:
        logger.debug("Could not extract stats for %s: %s", commit.hexsha[:8], e)
    return stats


def analyze_repository(
    repo_path: str | Path,
    config: AnalysisConfig | None = None,
) -> AnalysisResult:
    """Analyze a git repository and extract commit history.

    Args:
        repo_path: Path to the git repository root.
        config: Analysis configuration. Uses defaults if not provided.

    Returns:
        AnalysisResult with parsed commits, developers, and files.

    Raises:
        ValueError: If the path is not a valid git repository.
    """
    config = config or AnalysisConfig()
    repo_path = Path(repo_path).resolve()

    if not (repo_path / ".git").exists():
        raise ValueError(f"Not a git repository: {repo_path}")

    logger.info("Analyzing repository at %s", repo_path)
    repo = gitpython.Repo(str(repo_path))

    commits: list[CommitInfo] = []
    developers: dict[str, str] = {}
    files: set[str] = set()
    total_scanned = 0

    try:
        commit_iter = repo.iter_commits("HEAD", max_count=config.max_commits)
    except gitpython.GitCommandError as e:
        raise ValueError(f"Cannot iterate commits in {repo_path}: {e}") from e

    for raw_commit in commit_iter:
        total_scanned += 1

        if total_scanned % 500 == 0:
            logger.info("Processed %d commits...", total_scanned)

        author_email = raw_commit.author.email or "unknown@unknown"
        author_name = raw_commit.author.name or "Unknown"
        developers[author_email] = author_name

        ts = datetime.fromtimestamp(raw_commit.committed_date, tz=UTC)

        file_changes = _parse_diff_stats(raw_commit)
        numstats = _extract_numstat(raw_commit)

        filtered_changes: list[FileChange] = []
        for fc in file_changes:
            if _is_excluded(fc.path, config.excluded_paths):
                continue
            if fc.path in numstats:
                fc.additions, fc.deletions = numstats[fc.path]
            filtered_changes.append(fc)
            if fc.change_type != "D":
                files.add(fc.path)

        commit_info = CommitInfo(
            hash=raw_commit.hexsha,
            message=raw_commit.message.strip()[:200],
            author_name=author_name,
            author_email=author_email,
            timestamp=ts,
            files=filtered_changes,
        )
        commits.append(commit_info)

    logger.info(
        "Analysis complete: %d commits, %d developers, %d files",
        len(commits),
        len(developers),
        len(files),
    )

    return AnalysisResult(
        repo_path=str(repo_path),
        commits=commits,
        developers=developers,
        files=files,
        total_commits_scanned=total_scanned,
    )
