"""Tests for multi-repo support."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from repograph.core.multi_repo import (
    CrossRepoExpert,
    RepoInfo,
    list_repositories,
    query_cross_repo_experts,
    query_repo_summary,
    register_repository,
    tag_graph_with_repo,
)


class MockQueryResult:
    """Mock FalkorDB query result."""

    def __init__(self, result_set=None):
        self.result_set = result_set


@pytest.fixture()
def mock_db():
    """Create a mock DatabaseManager."""
    return MagicMock()


class TestRegisterRepository:
    """Tests for register_repository()."""

    def test_creates_repo_node(self, mock_db):
        """Test that a Repository node is created."""
        mock_db.query.return_value = MockQueryResult([])

        register_repository(
            mock_db, name="my-repo", path="/path/to/repo", url="https://example.com"
        )

        mock_db.query.assert_called_once()
        query_call = mock_db.query.call_args
        assert "MERGE (r:Repository" in query_call[0][0]
        assert query_call[1]["params"]["name"] == "my-repo"
        assert query_call[1]["params"]["path"] == "/path/to/repo"

    def test_default_empty_path_and_url(self, mock_db):
        """Test defaults for path and url."""
        mock_db.query.return_value = MockQueryResult([])

        register_repository(mock_db, name="test")

        params = mock_db.query.call_args[1]["params"]
        assert params["path"] == ""
        assert params["url"] == ""


class TestTagGraphWithRepo:
    """Tests for tag_graph_with_repo()."""

    def test_tags_files_and_commits(self, mock_db):
        """Test tagging untagged nodes."""
        # File tag query returns count, commit tag returns count, then two MERGE queries
        mock_db.query.side_effect = [
            MockQueryResult([[15]]),  # files tagged
            MockQueryResult([[50]]),  # commits tagged
            MockQueryResult([]),  # BELONGS_TO merge
            MockQueryResult([]),  # IN_REPO merge
        ]

        stats = tag_graph_with_repo(mock_db, "my-repo")

        assert stats["files"] == 15
        assert stats["commits"] == 50
        assert mock_db.query.call_count == 4


class TestListRepositories:
    """Tests for list_repositories()."""

    def test_returns_repo_list(self, mock_db):
        """Test listing repositories."""
        mock_db.query.return_value = MockQueryResult(
            [
                ["repo-a", "/path/a", "https://a.com", 5, 20, 100],
                ["repo-b", "/path/b", "", 3, 10, 50],
            ]
        )

        result = list_repositories(mock_db)

        assert len(result) == 2
        assert isinstance(result[0], RepoInfo)
        assert result[0].name == "repo-a"
        assert result[0].developer_count == 5
        assert result[1].name == "repo-b"
        assert result[1].url == ""

    def test_empty_repos(self, mock_db):
        """Test with no repos."""
        mock_db.query.return_value = MockQueryResult([])

        result = list_repositories(mock_db)
        assert result == []

    def test_none_path_and_url(self, mock_db):
        """Test handling of None path/url values."""
        mock_db.query.return_value = MockQueryResult(
            [
                ["repo-c", None, None, 1, 5, 10],
            ]
        )

        result = list_repositories(mock_db)
        assert result[0].path == ""
        assert result[0].url == ""


class TestQueryCrossRepoExperts:
    """Tests for query_cross_repo_experts()."""

    def test_finds_cross_repo_experts(self, mock_db):
        """Test finding developers across repos."""
        mock_db.query.return_value = MockQueryResult(
            [
                ["Alice", "alice@example.com", 3, ["repo-a", "repo-b", "repo-c"], 15.5],
                ["Bob", "bob@example.com", 2, ["repo-a", "repo-b"], 8.2],
            ]
        )

        result = query_cross_repo_experts(mock_db, min_repos=2, min_score=0.5)

        assert len(result) == 2
        assert isinstance(result[0], CrossRepoExpert)
        assert result[0].name == "Alice"
        assert result[0].repo_count == 3
        assert result[0].repos == ["repo-a", "repo-b", "repo-c"]
        assert result[0].total_score == 15.5

    def test_empty_cross_repo(self, mock_db):
        """Test with no cross-repo experts."""
        mock_db.query.return_value = MockQueryResult([])

        result = query_cross_repo_experts(mock_db)
        assert result == []

    def test_non_list_repos_handled(self, mock_db):
        """Test handling of non-list repos value."""
        mock_db.query.return_value = MockQueryResult(
            [
                ["Alice", "alice@example.com", 1, "not-a-list", 5.0],
            ]
        )

        result = query_cross_repo_experts(mock_db)
        assert result[0].repos == []


class TestQueryRepoSummary:
    """Tests for query_repo_summary()."""

    def test_returns_summary(self, mock_db):
        """Test repo summary."""
        mock_db.query.return_value = MockQueryResult(
            [
                [5, 20, 3, 100],
            ]
        )

        result = query_repo_summary(mock_db, repo_name="my-repo")

        assert result["repository"] == "my-repo"
        assert result["developers"] == 5
        assert result["files"] == 20
        assert result["modules"] == 3
        assert result["commits"] == 100

    def test_empty_summary(self, mock_db):
        """Test empty repo summary."""
        mock_db.query.return_value = MockQueryResult([])

        result = query_repo_summary(mock_db, repo_name="empty")

        assert result["developers"] == 0
        assert result["files"] == 0

    def test_none_result_set(self, mock_db):
        """Test None result set returns zeros."""
        mock_db.query.return_value = MockQueryResult(None)

        result = query_repo_summary(mock_db, repo_name="none")
        assert result["developers"] == 0
