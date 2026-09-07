"""Regression coverage for issue #6 -- repo_full_name echo mitigation.

Under a burst of many rapid/parallel tool calls against different repos, a
response can come back attributed to the wrong repo_path: the caller receives
another repo's real data, labeled as if it were the answer for the repo it
asked about. Observed directly: a sweep of ~19 repos via github_list_issues
returned claude-visual-learner's four open issues under claude-marketing-tool
(which has zero, ever), and gateway's issue #1 under eureka-server (which
also has zero, ever). No shared mutable state was found in this repo's own
GitHubApiClient.get_repo() to explain it -- the suspected mechanism is
upstream, in the installed mcp SDK's concurrent request/response dispatch.

This is a mitigation, not a root-cause fix: every tool that resolves a
repo_path now echoes back the resolved repo.full_name (PyGithub's own
resolved "owner/repo" string) so a caller can self-verify alignment
immediately instead of trusting positional/sequential correlation.
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base.clients import LazyClient
from server import (
    github_add_comment,
    github_close_issue,
    github_create_issue,
    github_get_issue,
    github_get_pr_status,
    github_label_issue,
    github_list_comments,
    github_list_issues,
    github_reopen_issue,
    github_update_issue,
)


@pytest.fixture(autouse=True)
def reset_github_client():
    """Reset all LazyClient singletons after each test to prevent state leakage."""
    yield
    LazyClient.reset_all()


class TestRepoFullNameEcho:
    """Each repo_path-resolving tool must echo the resolved repo.full_name."""

    @patch("server.GitHubApiClient")
    def test_list_issues_echoes_repo_full_name(self, mock_client_cls):
        """github_list_issues reports which repo it actually queried."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "techdeveloper-org/claude-visual-learner"
        mock_repo.get_issues.return_value = []
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo

        result = json.loads(github_list_issues())

        assert result["success"] is True
        assert result["repo_full_name"] == "techdeveloper-org/claude-visual-learner"

    @patch("server.GitHubApiClient")
    def test_get_issue_echoes_repo_full_name(self, mock_client_cls):
        """github_get_issue reports which repo the returned issue belongs to."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "techdeveloper-org/gateway"
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo

        issue = MagicMock()
        issue.pull_request = None
        issue.labels = []
        issue.assignees = []
        mock_repo.get_issue.return_value = issue

        result = json.loads(github_get_issue(number=1))

        assert result["success"] is True
        assert result["repo_full_name"] == "techdeveloper-org/gateway"

    @patch("server.GitHubApiClient")
    def test_close_issue_echoes_repo_full_name(self, mock_client_cls):
        """github_close_issue reports which repo it actually closed the issue in."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "techdeveloper-org/claude-marketing-tool"
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = MagicMock()

        result = json.loads(github_close_issue(number=4))

        assert result["success"] is True
        assert result["repo_full_name"] == "techdeveloper-org/claude-marketing-tool"

    @patch("server.GitHubApiClient")
    def test_reopen_issue_echoes_repo_full_name(self, mock_client_cls):
        """github_reopen_issue reports which repo it actually reopened the issue in."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "techdeveloper-org/eureka-server"
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = MagicMock()

        result = json.loads(github_reopen_issue(number=1))

        assert result["success"] is True
        assert result["repo_full_name"] == "techdeveloper-org/eureka-server"

    @patch("server.GitHubApiClient")
    def test_update_issue_echoes_repo_full_name(self, mock_client_cls):
        """github_update_issue reports which repo it actually edited the issue in."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "techdeveloper-org/mcp-github-api"
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = MagicMock()

        result = json.loads(github_update_issue(number=6, title="Renamed"))

        assert result["success"] is True
        assert result["repo_full_name"] == "techdeveloper-org/mcp-github-api"

    @patch("server.GitHubApiClient")
    def test_add_comment_echoes_repo_full_name(self, mock_client_cls):
        """github_add_comment reports which repo the comment actually landed in."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "techdeveloper-org/mcp-git-ops"
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        comment = MagicMock()
        comment.html_url = "https://github.com/techdeveloper-org/mcp-git-ops/issues/1#comment"
        mock_repo.get_issue.return_value.create_comment.return_value = comment

        result = json.loads(github_add_comment(number=1, body="test"))

        assert result["success"] is True
        assert result["repo_full_name"] == "techdeveloper-org/mcp-git-ops"

    @patch("server.GitHubApiClient")
    def test_list_comments_echoes_repo_full_name(self, mock_client_cls):
        """github_list_comments reports which repo it actually read comments from."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "techdeveloper-org/shakti-os"
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value.get_comments.return_value = []

        result = json.loads(github_list_comments(number=1))

        assert result["success"] is True
        assert result["repo_full_name"] == "techdeveloper-org/shakti-os"

    @patch("server.GitHubApiClient")
    def test_label_issue_echoes_repo_full_name(self, mock_client_cls):
        """github_label_issue reports which repo it actually labeled the issue in."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "techdeveloper-org/third-eye"
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        issue = MagicMock()
        issue.labels = []
        mock_repo.get_issue.return_value = issue

        result = json.loads(github_label_issue(number=1, labels="bug"))

        assert result["success"] is True
        assert result["repo_full_name"] == "techdeveloper-org/third-eye"

    @patch("server.GitHubApiClient")
    def test_get_pr_status_echoes_repo_full_name(self, mock_client_cls):
        """github_get_pr_status reports which repo the returned PR belongs to."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "techdeveloper-org/surgricalswale-category-service"
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        pr = MagicMock()
        pr.head.sha = "abc123"
        mock_repo.get_pull.return_value = pr
        mock_repo.get_commit.side_effect = Exception("no commit status")

        result = json.loads(github_get_pr_status(number=1))

        assert result["success"] is True
        assert result["repo_full_name"] == "techdeveloper-org/surgricalswale-category-service"

    @patch("server.GitHubApiClient")
    def test_create_issue_echoes_repo_full_name(self, mock_client_cls):
        """github_create_issue reports which repo the new issue was actually filed in."""
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "techdeveloper-org/mcp-github-api"
        mock_client_cls.instance.return_value = mock_client
        mock_client.get_repo.return_value = mock_repo
        issue = MagicMock()
        issue.number = 7
        mock_repo.create_issue.return_value = issue

        result = json.loads(github_create_issue(title="test"))

        assert result["success"] is True
        assert result["repo_full_name"] == "techdeveloper-org/mcp-github-api"

    @patch("server.GitHubApiClient")
    def test_different_repos_report_different_full_names(self, mock_client_cls):
        """Two calls with distinctly-mocked repos must never echo the same repo_full_name.

        This is the direct regression scenario: a caller comparing this field
        across two rapid-fire calls to different repos must be able to detect
        misattribution rather than silently trusting positional order.
        """
        mock_client = MagicMock()
        mock_client_cls.instance.return_value = mock_client

        repo_a = MagicMock()
        repo_a.full_name = "techdeveloper-org/claude-marketing-tool"
        repo_a.get_issues.return_value = []
        mock_client.get_repo.return_value = repo_a
        result_a = json.loads(github_list_issues(repo_path="/path/to/claude-marketing-tool"))

        repo_b = MagicMock()
        repo_b.full_name = "techdeveloper-org/claude-visual-learner"
        repo_b.get_issues.return_value = []
        mock_client.get_repo.return_value = repo_b
        result_b = json.loads(github_list_issues(repo_path="/path/to/claude-visual-learner"))

        assert result_a["repo_full_name"] != result_b["repo_full_name"]
        assert result_a["repo_full_name"] == "techdeveloper-org/claude-marketing-tool"
        assert result_b["repo_full_name"] == "techdeveloper-org/claude-visual-learner"
