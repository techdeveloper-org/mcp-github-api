"""Integration tests for github_create_label and github_create_milestone.

Requires env vars:
  GITHUB_TOKEN      — personal access token with repo write access
  GITHUB_TEST_REPO  — target repo in 'owner/repo' format (e.g. 'techdeveloper-org/test-repo')

These tests create real labels and milestones on GitHub and clean up after themselves.
Skip automatically when env vars are absent.
"""
import json
import os
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base.clients import LazyClient, GitHubApiClient
from server import github_create_label, github_create_milestone

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_TEST_REPO = os.environ.get("GITHUB_TEST_REPO", "")

requires_live_github = pytest.mark.skipif(
    not GITHUB_TOKEN or not GITHUB_TEST_REPO,
    reason="GITHUB_TOKEN and GITHUB_TEST_REPO env vars required for integration tests"
)


@pytest.fixture
def cleanup_label(request):
    """Yield a list that tests populate with label names to delete after the test.

    Teardown runs even if the test body raises, guaranteeing no orphaned labels
    are left in the test repository.
    """
    created_names = []
    yield created_names
    try:
        client = GitHubApiClient.instance().get_or_raise()
        gh_repo = client.get_repo(GITHUB_TEST_REPO)
        for name in created_names:
            try:
                gh_repo.get_label(name).delete()
            except Exception:
                pass
    except Exception:
        pass
    finally:
        LazyClient.reset_all()


@pytest.fixture
def cleanup_milestone(request):
    """Yield a list that tests populate with milestone titles to delete after the test.

    Teardown closes and deletes each milestone regardless of test outcome.
    """
    created_titles = []
    yield created_titles
    try:
        client = GitHubApiClient.instance().get_or_raise()
        gh_repo = client.get_repo(GITHUB_TEST_REPO)
        for title in created_titles:
            for ms in gh_repo.get_milestones(state="all"):
                if ms.title == title:
                    try:
                        ms.edit(state="closed")
                        ms.delete()
                    except Exception:
                        pass
    except Exception:
        pass
    finally:
        LazyClient.reset_all()


class TestCreateLabelIntegration:
    """Live-API integration tests for github_create_label (IT-01, IT-02)."""

    @requires_live_github
    def test_create_label_live(self, cleanup_label):
        """IT-01 (happy path): Create a brand-new label on the real GitHub repo.

        Verifies the full round-trip: the MCP function calls the GitHub API,
        GitHub creates the label, and the response reflects the created resource
        with already_exists=False.
        """
        label_name = f"test-integ-label-{int(time.time())}"
        cleanup_label.append(label_name)

        raw = github_create_label(
            repo=GITHUB_TEST_REPO,
            name=label_name,
            color="0075ca",
            description="Integration test label",
        )
        result = json.loads(raw)

        assert result["success"] is True, f"Expected success=True, got: {result}"
        assert result["name"] == label_name, (
            f"Expected name={label_name!r}, got: {result['name']!r}"
        )
        assert result["color"] == "0075ca", (
            f"Expected color='0075ca', got: {result['color']!r}"
        )
        assert result["already_exists"] is False, (
            f"Expected already_exists=False on first creation, got: {result['already_exists']}"
        )

    @requires_live_github
    def test_create_label_idempotent_live(self, cleanup_label):
        """IT-01 (idempotency): Calling github_create_label twice with the same name/color
        succeeds on both calls — the second call returns already_exists=True.

        This exercises the 422 fallback path in github_create_label: when GitHub rejects
        the duplicate create, the function fetches the existing label and returns it.
        """
        label_name = f"test-integ-idempotent-{int(time.time())}"
        cleanup_label.append(label_name)

        first_raw = github_create_label(
            repo=GITHUB_TEST_REPO,
            name=label_name,
            color="e4e669",
            description="Integration test idempotency label",
        )
        first_result = json.loads(first_raw)

        assert first_result["success"] is True, (
            f"First call must succeed. Got: {first_result}"
        )
        assert first_result["already_exists"] is False, (
            f"First call must return already_exists=False. Got: {first_result}"
        )

        second_raw = github_create_label(
            repo=GITHUB_TEST_REPO,
            name=label_name,
            color="e4e669",
            description="Integration test idempotency label",
        )
        second_result = json.loads(second_raw)

        assert second_result["success"] is True, (
            f"Second (idempotent) call must succeed. Got: {second_result}"
        )
        assert second_result["already_exists"] is True, (
            f"Second call must return already_exists=True. Got: {second_result}"
        )
        assert second_result["name"] == label_name, (
            f"Second call name must match. Expected {label_name!r}, got: {second_result['name']!r}"
        )


class TestCreateMilestoneIntegration:
    """Live-API integration tests for github_create_milestone (IT-03, IT-04)."""

    @requires_live_github
    def test_create_milestone_live(self, cleanup_milestone):
        """IT-03 (happy path): Create a brand-new milestone on the real GitHub repo.

        Verifies the full round-trip: the MCP function calls the GitHub API,
        GitHub creates the milestone, and the response reflects the created resource
        with already_exists=False, state='open', and a valid milestone number.
        """
        title = f"Test Sprint {int(time.time())}"
        cleanup_milestone.append(title)

        raw = github_create_milestone(
            repo=GITHUB_TEST_REPO,
            title=title,
            description="Integration test sprint",
            due_on="2026-12-31",
            state="open",
        )
        result = json.loads(raw)

        assert result["success"] is True, f"Expected success=True, got: {result}"
        assert result["title"] == title, (
            f"Expected title={title!r}, got: {result['title']!r}"
        )
        assert result["state"] == "open", (
            f"Expected state='open', got: {result['state']!r}"
        )
        assert isinstance(result["number"], int) and result["number"] >= 1, (
            f"Expected number to be a positive int, got: {result['number']}"
        )
        assert result["already_exists"] is False, (
            f"Expected already_exists=False on first creation, got: {result['already_exists']}"
        )

    @requires_live_github
    def test_create_milestone_idempotent_live(self, cleanup_milestone):
        """IT-03 (idempotency): Calling github_create_milestone twice with the same title
        succeeds on both calls — the second call returns already_exists=True with the same
        milestone number.

        This exercises the 422 fallback path in github_create_milestone: when GitHub rejects
        the duplicate create, the function scans get_milestones(state='all') for a title match
        and returns the existing milestone.
        """
        title = f"Test Sprint Idempotent {int(time.time())}"
        cleanup_milestone.append(title)

        first_raw = github_create_milestone(
            repo=GITHUB_TEST_REPO,
            title=title,
            description="Integration idempotency sprint",
            state="open",
        )
        first_result = json.loads(first_raw)

        assert first_result["success"] is True, (
            f"First call must succeed. Got: {first_result}"
        )
        assert first_result["already_exists"] is False, (
            f"First call must return already_exists=False. Got: {first_result}"
        )
        first_number = first_result["number"]

        second_raw = github_create_milestone(
            repo=GITHUB_TEST_REPO,
            title=title,
            description="Integration idempotency sprint",
            state="open",
        )
        second_result = json.loads(second_raw)

        assert second_result["success"] is True, (
            f"Second (idempotent) call must succeed. Got: {second_result}"
        )
        assert second_result["already_exists"] is True, (
            f"Second call must return already_exists=True. Got: {second_result}"
        )
        assert second_result["title"] == title, (
            f"Second call title must match. Expected {title!r}, got: {second_result['title']!r}"
        )
        assert second_result["number"] == first_number, (
            f"Second call must return the same milestone number. "
            f"Expected {first_number}, got: {second_result['number']}"
        )
