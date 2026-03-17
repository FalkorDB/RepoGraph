"""Unit tests for GitHub integration."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from repograph.integrations.github import (
    PRReview,
    fetch_pr_reviews,
    integrate_reviews,
)


class TestFetchPRReviews:
    @patch("repograph.integrations.github.subprocess.run")
    def test_fetch_reviews_success(self, mock_run: MagicMock) -> None:
        # Mock PR list response
        pr_list = [
            {"number": 1, "files": [{"path": "src/main.py"}, {"path": "src/utils.py"}]},
            {"number": 2, "files": [{"path": "src/api.py"}]},
        ]
        # Mock review response
        reviews_data = {
            "reviews": [
                {
                    "author": {"login": "alice"},
                    "state": "APPROVED",
                    "submittedAt": "2024-01-01T00:00:00Z",
                }
            ]
        }

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(pr_list)),
            MagicMock(returncode=0, stdout=json.dumps(reviews_data)),
            MagicMock(returncode=0, stdout=json.dumps(reviews_data)),
        ]

        reviews = fetch_pr_reviews("owner/repo", limit=2)
        assert len(reviews) == 2
        assert reviews[0].pr_number == 1
        assert reviews[0].reviewer_name == "alice"
        assert reviews[0].files_reviewed == ["src/main.py", "src/utils.py"]

    @patch("repograph.integrations.github.subprocess.run")
    def test_fetch_reviews_gh_not_found(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("gh not found")
        reviews = fetch_pr_reviews("owner/repo")
        assert reviews == []

    @patch("repograph.integrations.github.subprocess.run")
    def test_fetch_reviews_gh_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="auth error")
        reviews = fetch_pr_reviews("owner/repo")
        assert reviews == []

    @patch("repograph.integrations.github.subprocess.run")
    def test_fetch_reviews_timeout(self, mock_run: MagicMock) -> None:
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=30)
        reviews = fetch_pr_reviews("owner/repo")
        assert reviews == []


class TestIntegrateReviews:
    def test_integrate_approved_reviews(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(result_set=[["Alice"]])

        reviews = [
            PRReview(
                pr_number=1,
                reviewer_email="alice@github",
                reviewer_name="alice",
                files_reviewed=["src/main.py", "src/utils.py"],
                state="APPROVED",
                submitted_at="2024-01-01",
            )
        ]

        stats = integrate_reviews(mock_db, reviews)
        assert stats["reviews_processed"] == 1
        assert stats["knowledge_boosted"] == 2

    def test_skip_commented_reviews(self) -> None:
        mock_db = MagicMock()

        reviews = [
            PRReview(
                pr_number=1,
                reviewer_email="alice@github",
                reviewer_name="alice",
                files_reviewed=["src/main.py"],
                state="COMMENTED",
                submitted_at="2024-01-01",
            )
        ]

        stats = integrate_reviews(mock_db, reviews)
        assert stats["reviews_processed"] == 0
        assert stats["knowledge_boosted"] == 0
        mock_db.query.assert_not_called()

    def test_integrate_changes_requested(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(result_set=[["Bob"]])

        reviews = [
            PRReview(
                pr_number=1,
                reviewer_email="bob@github",
                reviewer_name="bob",
                files_reviewed=["src/api.py"],
                state="CHANGES_REQUESTED",
                submitted_at="2024-01-01",
            )
        ]

        stats = integrate_reviews(mock_db, reviews)
        assert stats["reviews_processed"] == 1
        assert stats["knowledge_boosted"] == 1

    def test_integrate_reviewer_not_found(self) -> None:
        mock_db = MagicMock()
        mock_db.query.return_value = MagicMock(result_set=[])

        reviews = [
            PRReview(
                pr_number=1,
                reviewer_email="unknown@github",
                reviewer_name="unknown",
                files_reviewed=["src/main.py"],
                state="APPROVED",
                submitted_at="2024-01-01",
            )
        ]

        stats = integrate_reviews(mock_db, reviews)
        assert stats["reviews_processed"] == 1
        assert stats["knowledge_boosted"] == 0
