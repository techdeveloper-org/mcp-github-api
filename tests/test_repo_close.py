"""Tests that every local Repo a tool opens is closed when the tool returns (#8).

GitPython keeps ``git cat-file`` helper processes and open ``.git`` handles
alive until ``Repo.close()`` is called. In this long-lived MCP server on
Windows an unclosed Repo locks the repository directory for the life of the
server.

Windows-safe: ASCII only, no Unicode characters.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402


class _FakeRepo:
    """Stand-in Repo that records whether it was closed."""

    def __init__(self):
        """Start unclosed."""
        self.closed = False

    def close(self):
        """Record the close."""
        self.closed = True


@pytest.fixture
def fake_repos(monkeypatch):
    """Make GitRepoClient.for_path hand out recording fakes.

    Yields:
        list: Every fake Repo created during the test, in creation order.
    """
    created = []

    def fake_for_path(repo_path="."):
        """Return a new recording fake for any path."""
        repo = _FakeRepo()
        created.append(repo)
        return repo

    monkeypatch.setattr(server.GitRepoClient, "for_path", staticmethod(fake_for_path))
    yield created


class TestOpenedReposAreClosed:
    """The wrapper closes what the tool opened, on success and on failure."""

    def test_every_repo_opened_during_a_call_is_closed_on_return(self, fake_repos):
        def tool_body(path):
            server._open_repo(path)
            server._open_repo(path)
            return "done"

        assert server._closes_opened_repos(tool_body)("x") == "done"
        assert len(fake_repos) == 2
        assert all(repo.closed for repo in fake_repos)

    def test_repos_are_closed_when_the_tool_raises(self, fake_repos):
        def failing_tool(path):
            server._open_repo(path)
            raise RuntimeError("tool failed")

        with pytest.raises(RuntimeError):
            server._closes_opened_repos(failing_tool)("x")
        assert fake_repos[0].closed

    def test_registry_is_reset_after_the_call(self, fake_repos):
        server._closes_opened_repos(lambda path: server._open_repo(path))("x")
        assert server._OPENED_REPOS.get() is None

    def test_open_repo_outside_a_tool_call_is_not_tracked_or_closed(self, fake_repos):
        repo = server._open_repo("x")
        assert repo.closed is False
        assert server._OPENED_REPOS.get() is None

    def test_git_backed_tools_carry_the_cleanup_wrapper(self):
        """Both tools that open a local Repo are registered through _tool."""
        wrapper_code = server._closes_opened_repos(lambda: None).__code__
        assert server.github_create_issue_branch.__code__ is wrapper_code
        assert server.github_auto_commit_and_pr.__code__ is wrapper_code

    def test_wrapped_still_exposes_the_undecorated_body(self):
        """``tool.__wrapped__`` must stay the raw body so callers can observe raw exceptions."""
        raw = server.github_create_issue_branch.__wrapped__
        assert not hasattr(raw, "__wrapped__")
        assert raw.__name__ == "github_create_issue_branch"
