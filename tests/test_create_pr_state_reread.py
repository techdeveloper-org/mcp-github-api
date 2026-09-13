"""Tests for github_create_pr re-reading state after a failed create (#9).

Hit in real use: five consecutive 500s from GitHub for one branch while
`gh pr create` succeeded with the identical head/base, and the response gave
the caller no way to tell whether a PR had been created.

Retrying is not the answer and must not become one -- POST is deliberately
excluded from retries because retrying a create produced duplicate issues
#256 and #257 on claude-workflow-engine from a single call. Reading the state
back is safe; retrying a non-idempotent write is not.

Windows-safe: ASCII only.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402
from github import GithubException  # noqa: E402


class _FakePR:
    def __init__(self, number=42, head="feature", base="master"):
        self.number = number
        self.html_url = f"https://github.com/acme/widget/pull/{number}"
        self.created_at = __import__("datetime").datetime(2026, 9, 13, 12, 0, 0)
        self._labels = []

    def add_to_labels(self, label):
        self._labels.append(label)


class _FakeRepo:
    """A repo whose create_pull fails, with configurable existing PRs."""

    full_name = "acme/widget"

    def __init__(self, existing=None, status=500, qualified_only=False):
        self.existing = existing or []
        self.status = status
        self.qualified_only = qualified_only
        self.head_queries = []

    def create_pull(self, **kwargs):
        raise GithubException(self.status, None, None)

    def get_pulls(self, state=None, head=None, base=None):
        self.head_queries.append(head)
        if self.qualified_only and ":" not in (head or ""):
            return []
        return list(self.existing)


@pytest.fixture(autouse=True)
def _stub_client(monkeypatch):
    """Point the tool at a fake repo and neutralise idempotency caching."""
    monkeypatch.setattr(server, "run_once", lambda name, key, fn: fn())
    yield


def _create(repo, monkeypatch, **kwargs):
    class _Client:
        @staticmethod
        def instance():
            return _Client()

        def get_repo(self, repo_path):
            return repo

    monkeypatch.setattr(server, "GitHubApiClient", _Client)
    raw = server.github_create_pr(
        title=kwargs.pop("title", "t"),
        body=kwargs.pop("body", "b"),
        head=kwargs.pop("head", "feature"),
        base=kwargs.pop("base", "master"),
        **kwargs,
    )
    return json.loads(raw) if isinstance(raw, str) else raw


class TestWhenThePrActuallyLanded:
    def test_it_is_reported_as_success(self, monkeypatch):
        """A write whose response was lost must not look like a failure."""
        repo = _FakeRepo(existing=[_FakePR(number=7)])
        result = _create(repo, monkeypatch)

        assert result.get("success") is not False
        assert result["pr_number"] == 7

    def test_it_says_it_was_found_rather_than_created(self, monkeypatch):
        """The caller needs to know it did not create this PR just now."""
        result = _create(_FakeRepo(existing=[_FakePR()]), monkeypatch)

        assert result["found_not_created"] is True
        assert result["upstream_error"] == "500"

    def test_the_qualified_head_form_is_tried(self, monkeypatch):
        """GitHub wants owner:branch when filtering and silently matches
        nothing for a bare name on some repos."""
        repo = _FakeRepo(existing=[_FakePR()], qualified_only=True)
        result = _create(repo, monkeypatch)

        assert result["pr_number"] == 42
        assert repo.head_queries[0] == "acme:feature"


class TestWhenNothingWasCreated:
    def test_the_failure_says_a_retry_is_safe(self, monkeypatch):
        """The whole point: an opaque 500 becomes an actionable answer."""
        result = _create(_FakeRepo(existing=[]), monkeypatch)

        assert result.get("success") is False
        blob = json.dumps(result)
        assert "nothing was created" in blob
        assert "retry is safe" in blob

    def test_the_upstream_status_is_preserved(self, monkeypatch):
        result = _create(_FakeRepo(existing=[], status=502), monkeypatch)

        assert "502" in json.dumps(result)

    def test_both_head_forms_are_tried_before_giving_up(self, monkeypatch):
        repo = _FakeRepo(existing=[])
        _create(repo, monkeypatch)

        assert repo.head_queries == ["acme:feature", "feature"]


class TestTheHappyPathIsUnchanged:
    def test_a_successful_create_reports_normally(self, monkeypatch):
        class _OkRepo(_FakeRepo):
            def create_pull(self, **kwargs):
                return _FakePR(number=99)

        result = _create(_OkRepo(), monkeypatch)

        assert result["pr_number"] == 99
        assert "found_not_created" not in result

    def test_labels_still_attach(self, monkeypatch):
        created = _FakePR(number=100)

        class _OkRepo(_FakeRepo):
            def create_pull(self, **kwargs):
                return created

        result = _create(_OkRepo(), monkeypatch, labels="bug,urgent")

        assert result["labels_failed"] == []
        assert created._labels == ["bug", "urgent"]

    def test_a_lookup_failure_during_recovery_does_not_mask_the_original(self, monkeypatch):
        """If even the re-read fails, the caller must still learn the original
        status rather than an error about the recovery attempt."""

        class _BlindRepo(_FakeRepo):
            def get_pulls(self, **kwargs):
                raise GithubException(503, None, None)

        result = _create(_BlindRepo(existing=[]), monkeypatch)

        assert result.get("success") is False
        assert "500" in json.dumps(result)
