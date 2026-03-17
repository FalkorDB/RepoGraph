"""Unit tests for the git analyzer module."""

from __future__ import annotations

import subprocess
from datetime import UTC
from pathlib import Path

import pytest

from repograph.core.config import AnalysisConfig
from repograph.core.git_analyzer import (
    AnalysisResult,
    CommitInfo,
    FileChange,
    _is_excluded,
    analyze_repository,
)


class TestIsExcluded:
    def test_excluded_path(self) -> None:
        assert _is_excluded("node_modules/foo/bar.js", ["node_modules"]) is True

    def test_not_excluded(self) -> None:
        assert _is_excluded("src/main.py", ["node_modules"]) is False

    def test_excluded_git(self) -> None:
        assert _is_excluded(".git/objects/abc", [".git"]) is True

    def test_partial_match_not_excluded(self) -> None:
        assert _is_excluded("src/node_modules_utils.py", ["node_modules"]) is False


class TestExtractModule:
    """Test module extraction from file paths - imported via the private helper."""

    def test_simple_path(self) -> None:
        from repograph.core.graph_builder import _extract_module

        modules = _extract_module("src/core/engine.py", depth=2)
        assert len(modules) == 2
        assert modules[0] == ("src", "src", 0)
        assert modules[1] == ("core", "src/core", 1)

    def test_shallow_path(self) -> None:
        from repograph.core.graph_builder import _extract_module

        modules = _extract_module("README.md", depth=2)
        assert len(modules) == 0

    def test_deep_path_limited(self) -> None:
        from repograph.core.graph_builder import _extract_module

        modules = _extract_module("a/b/c/d/e.py", depth=2)
        assert len(modules) == 2


class TestAnalyzeRepository:
    def test_not_a_repo(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Not a git repository"):
            analyze_repository(str(tmp_path))

    def test_analyze_simple_repo(self, tmp_path: Path) -> None:
        """Create a minimal git repo and analyze it."""
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Init repo and create commits
        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )

        # Create a file and commit
        (repo_dir / "src").mkdir()
        (repo_dir / "src" / "main.py").write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )

        # Create another file and commit
        (repo_dir / "src" / "utils.py").write_text("def helper(): pass")
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add utils"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )

        config = AnalysisConfig(max_commits=100)
        result = analyze_repository(str(repo_dir), config)

        assert isinstance(result, AnalysisResult)
        assert result.total_commits_scanned == 2
        assert len(result.developers) == 1
        assert "test@example.com" in result.developers
        assert "src/main.py" in result.files
        assert "src/utils.py" in result.files


class TestFileChange:
    def test_creation(self) -> None:
        fc = FileChange(path="src/main.py", additions=10, deletions=5, change_type="M")
        assert fc.path == "src/main.py"
        assert fc.additions == 10
        assert fc.change_type == "M"


class TestCommitInfo:
    def test_creation(self) -> None:
        from datetime import datetime

        ci = CommitInfo(
            hash="abc123",
            message="test commit",
            author_name="Test",
            author_email="test@test.com",
            timestamp=datetime.now(tz=UTC),
        )
        assert ci.hash == "abc123"
        assert ci.files == []
