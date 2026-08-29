"""Unit tests for github_reopen_issue, github_get_issue, github_update_issue,
and github_list_comments -- the four issue-lifecycle tools that fill gaps
found during real use of this server (no reopen, no single-issue read, no
in-place edit, no comment read-back)."""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from github import GithubException
from base.clients import LazyClient
from server import (
    github_reopen_issue,
    github_get_issue,
    github_update_issue,
    github_list_comments,
)


@pytest.fixture(autouse=True)
def reset_github_client():
    """Reset all LazyClient singletons after each test to prevent state leakage."""
    yield
    LazyClient.reset_all()


def _make_github_exception(status: int) -> GithubException:
    """Construct a GithubException with a specific HTTP status code.

    Args:
        status: The HTTP status code to assign.

    Returns:
        A GithubException mock with the given status attribute.
    """
    return GithubException(status, {"message": "GitHub API error"}, {})


class TestReopenIssue:
    """Unit tests for github_reopen_issue."""

    @patch("server.GitHubApiClient")
    def test_reopen_issue_success(self, mock_client_cls):
        """Verify happy-path: issue.edit(state='open') is called and the response reports state=open."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        result = json.loads(github_reopen_issue(number=34))

        assert result["success"] is True
        assert result["issue_number"] == 34
        assert result["state"] == "open"
        mock_repo.get_issue.assert_called_once_with(34)
        mock_issue.edit.assert_called_once_with(state="open")
        mock_issue.create_comment.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_reopen_issue_with_comment_posts_before_reopening(self, mock_client_cls):
        """Verify the comment is posted before the state edit, in that order."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        manager = MagicMock()
        manager.attach_mock(mock_issue.create_comment, "create_comment")
        manager.attach_mock(mock_issue.edit, "edit")

        result = json.loads(github_reopen_issue(
            number=34, comment="Reopening -- closed in error."
        ))

        assert result["success"] is True
        mock_issue.create_comment.assert_called_once_with("Reopening -- closed in error.")
        assert [c[0] for c in manager.mock_calls] == ["create_comment", "edit"]

    @patch("server.GitHubApiClient")
    def test_reopen_issue_no_comment_skips_create_comment(self, mock_client_cls):
        """Verify that omitting comment does not call create_comment at all."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        json.loads(github_reopen_issue(number=34))

        mock_issue.create_comment.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_reopen_issue_already_open_still_succeeds(self, mock_client_cls):
        """Verify reopening an already-open issue is a harmless redundant edit, not an error."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        result = json.loads(github_reopen_issue(number=45))

        assert result["success"] is True
        assert result["state"] == "open"

    @patch("server.GitHubApiClient")
    def test_reopen_issue_not_found(self, mock_client_cls):
        """Verify a 404 from get_issue surfaces as a failed result, not an unhandled exception."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.side_effect = _make_github_exception(404)

        result = json.loads(github_reopen_issue(number=9999))

        assert result["success"] is False
        assert result["error_type"] == "GithubException"


class TestGetIssue:
    """Unit tests for github_get_issue."""

    @staticmethod
    def _make_issue(**overrides):
        """Build a MagicMock issue with sane defaults, overridable per test.

        Args:
            **overrides: Attribute name/value pairs applied after the defaults.

        Returns:
            A MagicMock standing in for a PyGithub Issue.
        """
        issue = MagicMock()
        issue.number = 34
        issue.title = "operation_summary's target_descriptor is still undeliverable"
        issue.body = "Full issue body text."
        issue.state = "closed"
        issue.labels = []
        issue.assignees = []
        issue.comments = 2
        issue.created_at = datetime(2026, 8, 27, 9, 56, 43)
        issue.updated_at = datetime(2026, 8, 29, 5, 0, 0)
        issue.closed_at = datetime(2026, 8, 27, 10, 0, 0)
        issue.html_url = "https://github.com/owner/repo/issues/34"
        issue.pull_request = None
        for key, value in overrides.items():
            setattr(issue, key, value)
        return issue

    @patch("server.GitHubApiClient")
    def test_get_issue_success_all_fields(self, mock_client_cls):
        """Verify every declared response key is populated from a closed issue with labels and assignees."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo

        label = MagicMock()
        label.name = "docs-drift"
        assignee = MagicMock()
        assignee.login = "octocat"
        issue = self._make_issue(labels=[label], assignees=[assignee])
        mock_repo.get_issue.return_value = issue

        result = json.loads(github_get_issue(number=34))

        assert result["success"] is True
        assert result["issue_number"] == 34
        assert result["title"] == issue.title
        assert result["body"] == "Full issue body text."
        assert result["state"] == "closed"
        assert result["labels"] == ["docs-drift"]
        assert result["assignees"] == ["octocat"]
        assert result["comments"] == 2
        assert result["created_at"] == "2026-08-27T09:56:43"
        assert result["updated_at"] == "2026-08-29T05:00:00"
        assert result["closed_at"] == "2026-08-27T10:00:00"
        assert result["html_url"] == "https://github.com/owner/repo/issues/34"
        mock_repo.get_issue.assert_called_once_with(34)

    @patch("server.GitHubApiClient")
    def test_get_issue_open_issue_closed_at_is_none(self, mock_client_cls):
        """Verify an open issue's closed_at reports None rather than a stale prior value."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo

        issue = self._make_issue(state="open", closed_at=None)
        mock_repo.get_issue.return_value = issue

        result = json.loads(github_get_issue(number=45))

        assert result["success"] is True
        assert result["state"] == "open"
        assert result["closed_at"] is None

    @patch("server.GitHubApiClient")
    def test_get_issue_body_none_becomes_empty_string(self, mock_client_cls):
        """Verify a None body (issue filed with no description) normalizes to an empty string, not null."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo

        issue = self._make_issue(body=None)
        mock_repo.get_issue.return_value = issue

        result = json.loads(github_get_issue(number=34))

        assert result["success"] is True
        assert result["body"] == ""

    @patch("server.GitHubApiClient")
    def test_get_issue_rejects_pull_request_number(self, mock_client_cls):
        """Verify a PR number is rejected rather than silently returned as an issue with no body."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo

        pr_as_issue = self._make_issue()
        pr_as_issue.pull_request = MagicMock()
        mock_repo.get_issue.return_value = pr_as_issue

        result = json.loads(github_get_issue(number=17))

        assert result["success"] is False
        assert result["error_type"] == "ValueError"
        assert "pull request" in result["error"].lower()

    @patch("server.GitHubApiClient")
    def test_get_issue_not_found(self, mock_client_cls):
        """Verify a 404 from get_issue surfaces as a failed result."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.side_effect = _make_github_exception(404)

        result = json.loads(github_get_issue(number=9999))

        assert result["success"] is False
        assert result["error_type"] == "GithubException"

    @patch("server.GitHubApiClient")
    def test_get_issue_empty_labels_and_assignees(self, mock_client_cls):
        """Verify an issue with no labels and no assignees returns empty lists, not null or an error."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo

        issue = self._make_issue()
        mock_repo.get_issue.return_value = issue

        result = json.loads(github_get_issue(number=34))

        assert result["success"] is True
        assert result["labels"] == []
        assert result["assignees"] == []


class TestUpdateIssue:
    """Unit tests for github_update_issue."""

    @patch("server.GitHubApiClient")
    def test_update_issue_title_only(self, mock_client_cls):
        """Verify passing only title calls edit(title=...) and reports one updated field."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        result = json.loads(github_update_issue(number=34, title="Corrected title"))

        assert result["success"] is True
        assert result["issue_number"] == 34
        assert result["updated_fields"] == ["title"]
        mock_issue.edit.assert_called_once_with(title="Corrected title")

    @patch("server.GitHubApiClient")
    def test_update_issue_body_only(self, mock_client_cls):
        """Verify passing only body calls edit(body=...) and does not touch title/labels/assignee."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        result = json.loads(github_update_issue(number=34, body="Corrected body text."))

        assert result["success"] is True
        assert result["updated_fields"] == ["body"]
        mock_issue.edit.assert_called_once_with(body="Corrected body text.")

    @patch("server.GitHubApiClient")
    def test_update_issue_labels_parsed_from_csv(self, mock_client_cls):
        """Verify a comma-separated labels string is split, trimmed, and passed as a list."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        result = json.loads(github_update_issue(number=34, labels="docs-drift, coupling"))

        assert result["success"] is True
        assert result["updated_fields"] == ["labels"]
        mock_issue.edit.assert_called_once_with(labels=["docs-drift", "coupling"])

    @patch("server.GitHubApiClient")
    def test_update_issue_multiple_fields_all_reported(self, mock_client_cls):
        """Verify title+body+assignee together call edit once with all three kwargs."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        result = json.loads(github_update_issue(
            number=34, title="New title", body="New body", assignee="octocat"
        ))

        assert result["success"] is True
        assert result["updated_fields"] == ["assignee", "body", "title"]
        mock_issue.edit.assert_called_once_with(
            title="New title", body="New body", assignee="octocat"
        )

    @patch("server.GitHubApiClient")
    def test_update_issue_no_fields_rejected(self, mock_client_cls):
        """Verify calling with nothing to update raises ValueError before touching the API."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo

        result = json.loads(github_update_issue(number=34))

        assert result["success"] is False
        assert result["error_type"] == "ValueError"
        mock_repo.get_issue.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_update_issue_empty_labels_string_clears_labels(self, mock_client_cls):
        """Verify labels='' is treated as an explicit empty list (clear all labels), not 'unchanged'."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        result = json.loads(github_update_issue(number=34, labels=""))

        assert result["success"] is True
        assert result["updated_fields"] == ["labels"]
        mock_issue.edit.assert_called_once_with(labels=[])

    @patch("server.GitHubApiClient")
    def test_update_issue_not_found(self, mock_client_cls):
        """Verify a 404 from get_issue surfaces as a failed result."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.side_effect = _make_github_exception(404)

        result = json.loads(github_update_issue(number=9999, title="x"))

        assert result["success"] is False
        assert result["error_type"] == "GithubException"


class TestListComments:
    """Unit tests for github_list_comments."""

    @staticmethod
    def _make_comment(comment_id, body, author="octocat"):
        """Build a MagicMock comment with the fields github_list_comments reads.

        Args:
            comment_id: Comment id.
            body: Comment body text.
            author: Login of the comment's author.

        Returns:
            A MagicMock standing in for a PyGithub IssueComment.
        """
        comment = MagicMock()
        comment.id = comment_id
        comment.body = body
        comment.user.login = author
        comment.created_at = datetime(2026, 8, 29, 5, 0, 0)
        comment.updated_at = datetime(2026, 8, 29, 5, 0, 0)
        comment.html_url = f"https://github.com/owner/repo/issues/34#issuecomment-{comment_id}"
        return comment

    @patch("server.GitHubApiClient")
    def test_list_comments_issue_default_type(self, mock_client_cls):
        """Verify the default type='issue' reads repo.get_issue(number).get_comments()."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue
        mock_issue.get_comments.return_value = [
            self._make_comment(1, "First comment."),
            self._make_comment(2, "Second comment."),
        ]

        result = json.loads(github_list_comments(number=34))

        assert result["success"] is True
        assert result["count"] == 2
        assert result["truncated"] is False
        assert result["comments"][0]["id"] == 1
        assert result["comments"][0]["author"] == "octocat"
        assert result["comments"][0]["body"] == "First comment."
        assert result["comments"][0]["created_at"] == "2026-08-29T05:00:00"
        mock_repo.get_pull.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_list_comments_pr_uses_issue_comments_not_review_comments(self, mock_client_cls):
        """Verify type='pr' reads get_issue_comments() (conversation), never get_comments() (inline review)."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_pull.return_value = mock_pr
        mock_pr.get_issue_comments.return_value = [self._make_comment(3, "PR comment.")]

        result = json.loads(github_list_comments(number=12, type="pr"))

        assert result["success"] is True
        assert result["count"] == 1
        assert result["comments"][0]["body"] == "PR comment."
        mock_pr.get_issue_comments.assert_called_once()
        mock_pr.get_comments.assert_not_called()
        mock_repo.get_issue.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_list_comments_truncation_flag(self, mock_client_cls):
        """Verify truncated=True and count==limit when more comments exist than the limit."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue
        mock_issue.get_comments.return_value = [
            self._make_comment(i, f"Comment {i}.") for i in range(5)
        ]

        result = json.loads(github_list_comments(number=34, limit=3))

        assert result["success"] is True
        assert result["count"] == 3
        assert result["truncated"] is True
        assert result["limit"] == 3

    @patch("server.GitHubApiClient")
    def test_list_comments_empty(self, mock_client_cls):
        """Verify zero comments returns an empty list with truncated=False, not an error."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue
        mock_issue.get_comments.return_value = []

        result = json.loads(github_list_comments(number=34))

        assert result["success"] is True
        assert result["comments"] == []
        assert result["count"] == 0
        assert result["truncated"] is False

    @patch("server.GitHubApiClient")
    def test_list_comments_author_none_when_user_missing(self, mock_client_cls):
        """Verify a comment whose user is None (e.g. a deleted account) reports author=None, not a crash."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue

        comment = self._make_comment(4, "Orphaned comment.")
        comment.user = None
        mock_issue.get_comments.return_value = [comment]

        result = json.loads(github_list_comments(number=34))

        assert result["success"] is True
        assert result["comments"][0]["author"] is None

    @patch("server.GitHubApiClient")
    def test_list_comments_not_found(self, mock_client_cls):
        """Verify a 404 from get_issue surfaces as a failed result."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.side_effect = _make_github_exception(404)

        result = json.loads(github_list_comments(number=9999))

        assert result["success"] is False
        assert result["error_type"] == "GithubException"
