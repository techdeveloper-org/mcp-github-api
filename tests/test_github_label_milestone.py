"""Unit tests for github_create_label and github_create_milestone tools."""
import json
import sys
import os
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from github import GithubException
from base.clients import LazyClient
import server
from server import github_create_label, github_create_milestone


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


class TestCreateLabel:
    """Unit tests for github_create_label."""

    @patch("server.GitHubApiClient")
    def test_create_label_success(self, mock_client_cls):
        """Verify happy-path: create_label returns mock label with all expected keys and already_exists=False."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_label = MagicMock()
        mock_label.name = "bug"
        mock_label.color = "d73a4a"
        mock_label.description = "Something is broken"
        mock_label.url = "https://api.github.com/repos/owner/repo/labels/bug"
        mock_repo.create_label.return_value = mock_label

        result = json.loads(github_create_label(
            repo="owner/repo", name="bug", color="d73a4a",
            description="Something is broken"
        ))

        assert result["success"] is True
        assert result["name"] == "bug"
        assert result["color"] == "d73a4a"
        assert result["description"] == "Something is broken"
        assert result["url"] == "https://api.github.com/repos/owner/repo/labels/bug"
        assert result["already_exists"] is False

    @patch("server.GitHubApiClient")
    def test_create_label_color_strip_hash(self, mock_client_cls):
        """Verify that a leading '#' in color is stripped before calling create_label."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_label = MagicMock()
        mock_label.name = "enhancement"
        mock_label.color = "d73a4a"
        mock_label.description = ""
        mock_label.url = "https://api.github.com/repos/owner/repo/labels/enhancement"
        mock_repo.create_label.return_value = mock_label

        result = json.loads(github_create_label(
            repo="owner/repo", name="enhancement", color="#d73a4a"
        ))

        assert result["success"] is True
        assert result["already_exists"] is False
        mock_repo.create_label.assert_called_once_with(
            name="enhancement", color="d73a4a", description=""
        )

    @patch("server.GitHubApiClient")
    def test_create_label_already_exists_returns_existing(self, mock_client_cls):
        """Verify that a 422 from create_label triggers get_label and returns already_exists=True."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_repo.create_label.side_effect = _make_github_exception(422)

        existing_label = MagicMock()
        existing_label.name = "bug"
        existing_label.color = "ee0701"
        existing_label.description = "Existing description"
        existing_label.url = "https://api.github.com/repos/owner/repo/labels/bug"
        mock_repo.get_label.return_value = existing_label

        result = json.loads(github_create_label(
            repo="owner/repo", name="bug", color="d73a4a"
        ))

        assert result["success"] is True
        assert result["already_exists"] is True
        assert result["name"] == "bug"
        assert result["color"] == "ee0701"
        assert result["description"] == "Existing description"
        mock_repo.get_label.assert_called_once_with("bug")

    @patch("server.GitHubApiClient")
    def test_create_label_invalid_color_not_hex(self, mock_client_cls):
        """Verify that a non-hex color string is rejected with a descriptive error."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_label(
            repo="owner/repo", name="bug", color="zzzzzz"
        ))

        assert result["success"] is False
        assert "hex" in result["error"].lower()
        mock_repo.create_label.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_create_label_invalid_color_wrong_length(self, mock_client_cls):
        """Verify that a 3-char color (wrong length) is rejected with an error mentioning '6 hex'."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_label(
            repo="owner/repo", name="bug", color="abc"
        ))

        assert result["success"] is False
        assert "6 hex" in result["error"].lower() or "6 hex" in result["error"]
        mock_repo.create_label.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_create_label_invalid_color_with_hash_wrong_length(self, mock_client_cls):
        """Verify that '#ab' (2 chars after stripping '#') fails the 6-char validation."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_label(
            repo="owner/repo", name="bug", color="#ab"
        ))

        assert result["success"] is False
        assert result["error_type"] == "ValueError"
        mock_repo.create_label.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_create_label_empty_name(self, mock_client_cls):
        """Verify that an empty name is rejected with a '1-50' error message."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_label(
            repo="owner/repo", name="", color="d73a4a"
        ))

        assert result["success"] is False
        assert "1-50" in result["error"]
        mock_repo.create_label.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_create_label_name_too_long(self, mock_client_cls):
        """Verify that a name with 51 characters is rejected with a validation error."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_label(
            repo="owner/repo", name="a" * 51, color="d73a4a"
        ))

        assert result["success"] is False
        assert result["error_type"] == "ValueError"
        mock_repo.create_label.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_create_label_404(self, mock_client_cls):
        """Verify that a 404 from create_label raises a ValueError mentioning 'not found'."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_repo.create_label.side_effect = _make_github_exception(404)

        result = json.loads(github_create_label(
            repo="owner/repo", name="bug", color="d73a4a"
        ))

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @patch("server.GitHubApiClient")
    def test_create_label_403(self, mock_client_cls):
        """Verify that a 403 from create_label raises a ValueError mentioning 'write permission'."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_repo.create_label.side_effect = _make_github_exception(403)

        result = json.loads(github_create_label(
            repo="owner/repo", name="bug", color="d73a4a"
        ))

        assert result["success"] is False
        assert "write permission" in result["error"].lower()

    @patch("server.GitHubApiClient")
    def test_create_label_unknown_github_error(self, mock_client_cls):
        """Verify that an unhandled GithubException (e.g. 500) is re-raised and surfaces as error_type=GithubException."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_repo.create_label.side_effect = _make_github_exception(500)

        result = json.loads(github_create_label(
            repo="owner/repo", name="bug", color="d73a4a"
        ))

        assert result["success"] is False
        assert result["error_type"] == "GithubException"

    @patch("server.GitHubApiClient")
    def test_create_label_description_none_becomes_empty(self, mock_client_cls):
        """Verify that a None description on the created label is normalized to empty string."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_label = MagicMock()
        mock_label.name = "bug"
        mock_label.color = "d73a4a"
        mock_label.description = None
        mock_label.url = "https://api.github.com/repos/owner/repo/labels/bug"
        mock_repo.create_label.return_value = mock_label

        result = json.loads(github_create_label(
            repo="owner/repo", name="bug", color="d73a4a"
        ))

        assert result["success"] is True
        assert result["description"] == ""

    @patch("server.GitHubApiClient")
    def test_create_label_existing_description_none_becomes_empty(self, mock_client_cls):
        """Verify that a None description on the existing (422-path) label is normalized to empty string."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_repo.create_label.side_effect = _make_github_exception(422)

        existing_label = MagicMock()
        existing_label.name = "bug"
        existing_label.color = "ee0701"
        existing_label.description = None
        existing_label.url = "https://api.github.com/repos/owner/repo/labels/bug"
        mock_repo.get_label.return_value = existing_label

        result = json.loads(github_create_label(
            repo="owner/repo", name="bug", color="d73a4a"
        ))

        assert result["success"] is True
        assert result["already_exists"] is True
        assert result["description"] == ""

    @patch("server.GitHubApiClient")
    def test_create_label_invalid_repo_no_slash(self, mock_client_cls):
        """Verify that a repo string without '/' is rejected with an 'owner/repo' error."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_label(repo="nodash", name="bug", color="d73a4a"))

        assert result["success"] is False
        assert "owner/repo" in result["error"]

    @patch("server.GitHubApiClient")
    def test_create_label_invalid_repo_leading_slash(self, mock_client_cls):
        """Verify that a repo string starting with '/' is rejected."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_label(repo="/leading", name="bug", color="d73a4a"))

        assert result["success"] is False

    @patch("server.GitHubApiClient")
    def test_create_label_invalid_repo_trailing_slash(self, mock_client_cls):
        """Verify that a repo string ending with '/' is rejected."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_label(repo="trailing/", name="bug", color="d73a4a"))

        assert result["success"] is False

    @patch("server.GitHubApiClient")
    def test_create_label_name_with_null_byte(self, mock_client_cls):
        """Verify that a null byte in name is sanitised by validate_input before reaching the API."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_label = MagicMock()
        mock_label.name = "buginjected"
        mock_label.color = "d73a4a"
        mock_label.description = ""
        mock_label.url = "https://api.github.com/repos/owner/repo/labels/buginjected"
        mock_repo.create_label.return_value = mock_label

        result = json.loads(github_create_label(repo="owner/repo", name="bug\x00injected", color="d73a4a"))

        if result["success"]:
            call_args = mock_repo.create_label.call_args
            assert "\x00" not in call_args.kwargs.get("name", ""), "Null byte must not reach API"
        else:
            assert result["success"] is False


class TestCreateMilestone:
    """Unit tests for github_create_milestone."""

    @patch("server.GitHubApiClient")
    def test_create_milestone_success_no_due_on(self, mock_client_cls):
        """Verify happy-path with no due_on: create_milestone called without due_on kwarg, all 8 response keys present."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_ms = MagicMock()
        mock_ms.number = 1
        mock_ms.title = "Sprint 1"
        mock_ms.description = "First sprint"
        mock_ms.due_on = None
        mock_ms.state = "open"
        mock_ms.open_issues = 0
        mock_ms.html_url = "https://github.com/owner/repo/milestone/1"
        mock_repo.create_milestone.return_value = mock_ms

        result = json.loads(github_create_milestone(
            repo="owner/repo", title="Sprint 1", description="First sprint"
        ))

        assert result["success"] is True
        assert result["number"] == 1
        assert result["title"] == "Sprint 1"
        assert result["description"] == "First sprint"
        assert result["due_on"] is None
        assert result["state"] == "open"
        assert result["open_issues"] == 0
        assert result["html_url"] == "https://github.com/owner/repo/milestone/1"
        assert result["already_exists"] is False

        call_kwargs = mock_repo.create_milestone.call_args
        assert "due_on" not in call_kwargs.kwargs

    @patch("server.GitHubApiClient")
    def test_create_milestone_success_due_on_date_format(self, mock_client_cls):
        """Verify that 'YYYY-MM-DD' due_on is parsed to a datetime and passed to create_milestone."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_ms = MagicMock()
        mock_ms.number = 2
        mock_ms.title = "Sprint 2"
        mock_ms.description = ""
        mock_ms.due_on = datetime(2026, 6, 13)
        mock_ms.state = "open"
        mock_ms.open_issues = 0
        mock_ms.html_url = "https://github.com/owner/repo/milestone/2"
        mock_repo.create_milestone.return_value = mock_ms

        result = json.loads(github_create_milestone(
            repo="owner/repo", title="Sprint 2", due_on="2026-06-13"
        ))

        assert result["success"] is True
        call_kwargs = mock_repo.create_milestone.call_args.kwargs
        assert call_kwargs["due_on"] == datetime(2026, 6, 13)

    @patch("server.GitHubApiClient")
    def test_create_milestone_success_due_on_iso_format(self, mock_client_cls):
        """Verify that an ISO 8601 'YYYY-MM-DDTHH:MM:SSZ' due_on is parsed to the correct datetime."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_ms = MagicMock()
        mock_ms.number = 3
        mock_ms.title = "Sprint 3"
        mock_ms.description = ""
        mock_ms.due_on = datetime(2026, 6, 13, 23, 59, 59)
        mock_ms.state = "open"
        mock_ms.open_issues = 0
        mock_ms.html_url = "https://github.com/owner/repo/milestone/3"
        mock_repo.create_milestone.return_value = mock_ms

        result = json.loads(github_create_milestone(
            repo="owner/repo", title="Sprint 3", due_on="2026-06-13T23:59:59Z"
        ))

        assert result["success"] is True
        call_kwargs = mock_repo.create_milestone.call_args.kwargs
        assert call_kwargs["due_on"] == datetime(2026, 6, 13, 23, 59, 59)

    @patch("server.GitHubApiClient")
    def test_create_milestone_already_exists(self, mock_client_cls):
        """Verify that a 422 triggers get_milestones scan and returns already_exists=True for a title match."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_repo.create_milestone.side_effect = _make_github_exception(422)

        existing_ms = MagicMock()
        existing_ms.number = 5
        existing_ms.title = "Sprint 1"
        existing_ms.description = "Existing sprint"
        existing_ms.due_on = None
        existing_ms.state = "open"
        existing_ms.open_issues = 3
        existing_ms.html_url = "https://github.com/owner/repo/milestone/5"
        mock_repo.get_milestones.return_value = [existing_ms]

        result = json.loads(github_create_milestone(
            repo="owner/repo", title="Sprint 1"
        ))

        assert result["success"] is True
        assert result["already_exists"] is True
        assert result["number"] == 5
        assert result["title"] == "Sprint 1"
        mock_repo.get_milestones.assert_called_once_with(state="all")

    @patch("server.GitHubApiClient")
    def test_create_milestone_invalid_state(self, mock_client_cls):
        """Verify that an invalid state value is rejected with a descriptive error mentioning 'open'."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_milestone(
            repo="owner/repo", title="Sprint 1", state="invalid"
        ))

        assert result["success"] is False
        assert "open" in result["error"]
        mock_repo.create_milestone.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_create_milestone_empty_title(self, mock_client_cls):
        """Verify that an empty title is rejected with an error mentioning 'empty'."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_milestone(
            repo="owner/repo", title=""
        ))

        assert result["success"] is False
        assert "empty" in result["error"].lower()
        mock_repo.create_milestone.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_create_milestone_invalid_due_on(self, mock_client_cls):
        """Verify that an unrecognized due_on format is rejected with 'YYYY-MM-DD' in the error."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_milestone(
            repo="owner/repo", title="Sprint 1", due_on="not-a-date"
        ))

        assert result["success"] is False
        assert "YYYY-MM-DD" in result["error"]
        mock_repo.create_milestone.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_create_milestone_404(self, mock_client_cls):
        """Verify that a 404 from create_milestone raises a ValueError mentioning 'not found'."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_repo.create_milestone.side_effect = _make_github_exception(404)

        result = json.loads(github_create_milestone(
            repo="owner/repo", title="Sprint 1"
        ))

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @patch("server.GitHubApiClient")
    def test_create_milestone_unknown_github_error(self, mock_client_cls):
        """Verify that an unrecognised GithubException (e.g. 500) is re-raised as-is."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_repo.create_milestone.side_effect = _make_github_exception(500)

        result = json.loads(github_create_milestone(
            repo="owner/repo", title="Sprint 1"
        ))

        assert result["success"] is False
        assert result.get("error_type") == "GithubException"

    @patch("server.GitHubApiClient")
    def test_create_milestone_due_on_none_in_response(self, mock_client_cls):
        """Verify that a milestone with due_on=None returns due_on=None in the response (not an error)."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        mock_ms = MagicMock()
        mock_ms.number = 7
        mock_ms.title = "Sprint 7"
        mock_ms.description = ""
        mock_ms.due_on = None
        mock_ms.state = "open"
        mock_ms.open_issues = 0
        mock_ms.html_url = "https://github.com/owner/repo/milestone/7"
        mock_repo.create_milestone.return_value = mock_ms

        result = json.loads(github_create_milestone(
            repo="owner/repo", title="Sprint 7"
        ))

        assert result["success"] is True
        assert result["due_on"] is None

    @patch("server.GitHubApiClient")
    def test_create_milestone_whitespace_only_title(self, mock_client_cls):
        """Verify that a whitespace-only title is rejected as empty after validate_input strips it."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_milestone(repo="owner/repo", title="   "))

        assert result["success"] is False
        assert "empty" in result["error"].lower()
        mock_repo.create_milestone.assert_not_called()

    @patch("server.GitHubApiClient")
    def test_create_milestone_invalid_repo_no_slash(self, mock_client_cls):
        """Verify that a repo string without '/' is rejected with an 'owner/repo' error."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_client_cls.instance.return_value.get_or_raise.return_value = mock_github
        mock_github.get_repo.return_value = mock_repo

        result = json.loads(github_create_milestone(repo="nodash", title="Sprint 1"))

        assert result["success"] is False
        assert "owner/repo" in result["error"]
