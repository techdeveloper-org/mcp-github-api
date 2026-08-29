"""
GitHub MCP Server - FastMCP-based GitHub operations for Claude Code.

Replaces 8+ subprocess calls in github_integration.py with PyGithub library.
Backend: PyGithub (primary) + gh CLI fallback for critical operations
Transport: stdio

Tools (18):
  github_create_issue, github_close_issue, github_reopen_issue,
  github_update_issue, github_add_comment, github_list_comments,
  github_create_pr, github_merge_pr, github_list_issues, github_get_issue,
  github_get_pr_status, github_create_issue_branch, github_auto_commit_and_pr,
  github_validate_build, github_label_issue, github_create_label,
  github_create_milestone, github_full_merge_cycle
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Ensure src/mcp/ is in path for base package imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

# mcp 2.0 renamed FastMCP to MCPServer and moved it to mcp.server.mcpserver.
# Both names are probed so this server runs under either major version; the
# API used below (tool decorator, run(transport=...)) is identical in both.
try:
    from mcp.server.mcpserver import MCPServer
except ImportError:  # mcp < 2.0
    from mcp.server.fastmcp import FastMCP as MCPServer

try:
    from mcp.types import ToolAnnotations
except ImportError:  # pragma: no cover - annotations unsupported on this mcp
    ToolAnnotations = None

from base.decorators import mcp_tool_handler
from base.clients import GitHubApiClient, GitRepoClient
from input_validator import validate_input
from idempotency import run_once

try:
    from github import GithubException
except ImportError:
    GithubException = Exception  # Fallback so except clauses don't fail

mcp = MCPServer("github-api", instructions="GitHub operations via PyGithub (no subprocess)")


def _tool(read_only=False, destructive=True, idempotent=False, open_world=True):
    """Register a tool with explicit MCP ToolAnnotations.

    The MCP specification's per-hint defaults are readOnlyHint=false,
    destructiveHint=true, idempotentHint=false and openWorldHint=true -- every
    default points at the more dangerous value, so an unannotated tool is
    indistinguishable from an explicit worst-case declaration. A host may
    therefore refuse to auto-approve it, or conversely may auto-retry a tool
    whose retry-safety was never actually established. Every tool on this server
    declares its four hints explicitly so that auto-approval and automatic retry
    decisions rest on a stated property rather than on an omission.

    Args:
        read_only: True when the tool has no side effects at all.
        destructive: True when the tool's effect is irreversible.
        idempotent: True only when repeating the call with identical arguments
            leaves the same cumulative effect as a single call. A tool that is
            merely made retry-safe by a caller-supplied idempotency key does not
            qualify: the underlying operation is still non-idempotent and the
            protection is conditional on the caller reusing the key.
        open_world: True when the tool reaches an external system.

    Returns:
        The decorator returned by the underlying MCP tool registration.
    """
    if ToolAnnotations is None:
        return mcp.tool()
    try:
        return mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=read_only,
                destructiveHint=destructive,
                idempotentHint=idempotent,
                openWorldHint=open_world,
            )
        )
    except TypeError:  # pragma: no cover - older mcp without annotations kwarg
        return mcp.tool()


def _gh_cli_merge_fallback(number: int, method: str, delete_branch: bool,
                           commit_message: str) -> Optional[dict]:
    """Fallback: merge PR via gh CLI if PyGithub fails.

    Args:
        number: PR number to merge.
        method: Merge method ('merge', 'squash', 'rebase').
        delete_branch: Whether to delete the head branch after merging.
        commit_message: Merge commit body.

    Returns:
        A result dict on success, or None when the CLI is unavailable or the
        merge command failed. The failure reason is carried in the returned
        dict rather than discarded, so the caller can surface why the fallback
        did not help instead of reporting a bare re-raised primary error.
    """
    cmd = ["gh", "pr", "merge", str(number), f"--{method}"]
    if delete_branch:
        cmd.append("--delete-branch")
    if commit_message:
        cmd.extend(["--body", commit_message])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        return {
            "success": False,
            "pr_number": number,
            "merged": False,
            "fallback": "gh_cli",
            "fallback_error": f"{type(exc).__name__}: {exc}",
        }

    if result.returncode == 0:
        return {
            "success": True,
            "pr_number": number,
            "merged": True,
            "method": method,
            "branch_deleted": delete_branch,
            "fallback": "gh_cli"
        }
    return {
        "success": False,
        "pr_number": number,
        "merged": False,
        "fallback": "gh_cli",
        "fallback_error": (result.stderr or result.stdout or "").strip()[:500],
        "fallback_exit_code": result.returncode,
    }


def _pr_is_merged(number: int, repo_path: str) -> bool:
    """Re-read a pull request and report whether it is already merged.

    Used on the merge failure path to distinguish "the merge never happened"
    from "the merge happened and only the acknowledgment was lost". Returns
    False when the state cannot be established, so an unverifiable outcome
    never masquerades as a completed merge.

    Args:
        number: PR number.
        repo_path: Local repo path used to resolve owner/repo.

    Returns:
        True only when GitHub confirms the PR is merged.
    """
    try:
        repo = GitHubApiClient.instance().get_repo(repo_path)
        return bool(repo.get_pull(number).merged)
    except Exception:
        return False


@_tool(read_only=False, destructive=False, idempotent=False, open_world=True)
@mcp_tool_handler
def github_create_issue(
    title: str,
    body: str = "",
    labels: Optional[str] = None,
    assignee: Optional[str] = None,
    repo_path: str = ".",
    idempotency_key: Optional[str] = None
) -> dict:
    """Create a GitHub issue.

    Creating an issue is not idempotent: the GitHub API has no natural
    de-duplication, so a retry after a lost response files a second issue.
    Supply ``idempotency_key`` to make a retry safe. Generate that key once,
    when you decide to file the issue, and send the same value on every retry
    of that same decision -- a key regenerated per attempt provides no
    protection at all.

    Args:
        title: Issue title
        body: Issue description (markdown supported)
        labels: Comma-separated label names (e.g., 'bug,priority-high')
        assignee: GitHub username to assign the issue to
        repo_path: Local repo path for auto-detecting owner/repo
        idempotency_key: Optional caller-generated key scoped to one logical
            issue-creation intent. When a previously completed key is replayed,
            the original result is returned with ``idempotent_replay`` true and
            no second issue is filed.
    """
    def _create() -> dict:
        """Perform the underlying non-idempotent issue creation."""
        repo = GitHubApiClient.instance().get_repo(repo_path)
        label_list = (
            [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
            if labels else []
        )

        kwargs = {"title": title, "body": body, "labels": label_list}
        if assignee:
            kwargs["assignee"] = assignee

        issue = repo.create_issue(**kwargs)

        return {
            "issue_number": issue.number,
            "issue_url": issue.html_url,
            "assignee": assignee,
            "created_at": issue.created_at.isoformat()
        }

    return run_once("github_create_issue", idempotency_key, _create)


@_tool(read_only=False, destructive=False, idempotent=False, open_world=True)
@mcp_tool_handler
def github_close_issue(
    number: int,
    comment: Optional[str] = None,
    repo_path: str = "."
) -> dict:
    """Close a GitHub issue with optional closing comment.

    Args:
        number: Issue number
        comment: Optional comment to add before closing
        repo_path: Local repo path
    """
    repo = GitHubApiClient.instance().get_repo(repo_path)
    issue = repo.get_issue(number)

    if comment:
        issue.create_comment(comment)

    issue.edit(state="closed")

    return {
        "issue_number": number,
        "state": "closed"
    }


@_tool(read_only=False, destructive=False, idempotent=False, open_world=True)
@mcp_tool_handler
def github_reopen_issue(
    number: int,
    comment: Optional[str] = None,
    repo_path: str = "."
) -> dict:
    """Reopen a closed GitHub issue with optional reopening comment.

    Mirrors github_close_issue in reverse. Reopening is not idempotent in
    the sense the ``idempotent`` annotation above tracks: calling it twice on
    an already-open issue is harmless (GitHub accepts a redundant state edit),
    but it is not safe to blindly retry against an issue whose state a
    concurrent actor may have since changed again -- the same caution that
    applies to github_close_issue.

    Args:
        number: Issue number
        comment: Optional comment to add before reopening
        repo_path: Local repo path
    """
    repo = GitHubApiClient.instance().get_repo(repo_path)
    issue = repo.get_issue(number)

    if comment:
        issue.create_comment(comment)

    issue.edit(state="open")

    return {
        "issue_number": number,
        "state": "open"
    }


@_tool(read_only=False, destructive=False, idempotent=False, open_world=True)
@mcp_tool_handler
def github_update_issue(
    number: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    labels: Optional[str] = None,
    assignee: Optional[str] = None,
    repo_path: str = "."
) -> dict:
    """Update an existing issue's title, body, labels, or assignee.

    Fills the gap between github_create_issue (title/body fixed at filing
    time) and github_label_issue (labels only, additive). Correcting a filed
    issue's title or body -- a mistaken root-cause name, a status note that
    belongs in the body rather than a comment -- currently has no tool. Only
    fields explicitly passed are changed; PyGithub leaves every omitted field
    as-is. Unlike github_label_issue, a supplied ``labels`` REPLACES the
    issue's full label set rather than adding to it, matching PyGithub's
    ``edit(labels=...)`` semantics -- pass the existing labels back if only
    adding one.

    Args:
        number: Issue number
        title: New title, or None to leave unchanged
        body: New body, or None to leave unchanged
        labels: Comma-separated label names REPLACING the issue's current
            labels, or None to leave the label set unchanged
        assignee: GitHub username to assign, or None to leave unchanged
        repo_path: Local repo path

    Raises:
        ValueError: If none of title, body, labels, or assignee is provided --
            an update with nothing to update is a caller error, not a no-op
            success.
    """
    kwargs = {}
    if title is not None:
        kwargs["title"] = title
    if body is not None:
        kwargs["body"] = body
    if labels is not None:
        kwargs["labels"] = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
    if assignee is not None:
        kwargs["assignee"] = assignee

    if not kwargs:
        raise ValueError(
            "At least one of title, body, labels, or assignee must be provided"
        )

    repo = GitHubApiClient.instance().get_repo(repo_path)
    issue = repo.get_issue(number)
    issue.edit(**kwargs)

    return {
        "issue_number": number,
        "updated_fields": sorted(kwargs.keys())
    }


@_tool(read_only=False, destructive=False, idempotent=False, open_world=True)
@mcp_tool_handler
def github_add_comment(
    number: int,
    body: str,
    type: str = "issue",
    repo_path: str = "."
) -> dict:
    """Add a comment to an issue or pull request.

    Args:
        number: Issue or PR number
        body: Comment text (markdown supported)
        type: 'issue' or 'pr'
        repo_path: Local repo path
    """
    repo = GitHubApiClient.instance().get_repo(repo_path)

    if type == "pr":
        pr = repo.get_pull(number)
        comment = pr.create_issue_comment(body)
    else:
        issue = repo.get_issue(number)
        comment = issue.create_comment(body)

    return {
        "comment_url": comment.html_url,
        "type": type
    }


@_tool(read_only=True, destructive=False, idempotent=True, open_world=True)
@mcp_tool_handler
def github_list_comments(
    number: int,
    type: str = "issue",
    repo_path: str = ".",
    limit: int = 100
) -> dict:
    """List comments on an issue or pull request.

    github_add_comment can write a comment but nothing on this server could
    read one back -- a caller checking whether a prior comment landed, or
    reviewing prior discussion before adding to it, had to leave the tool
    surface entirely. Mirrors github_list_issues' truncation contract: a
    caller that checks ``truncated`` is safe, one that assumes a short result
    is complete is not.

    For a pull request, this returns the conversation (issue-style) comments
    -- the same comment kind github_add_comment(type="pr") writes -- and NOT
    inline review comments attached to a diff line, which PyGithub exposes
    through a separate collection this tool does not read.

    Args:
        number: Issue or PR number
        type: 'issue' or 'pr'
        repo_path: Local repo path
        limit: Maximum comments to return

    Returns:
        Dict with ``comments``, ``count``, ``truncated`` and the effective
        ``limit``.
    """
    repo = GitHubApiClient.instance().get_repo(repo_path)

    if type == "pr":
        comment_source = repo.get_pull(number).get_issue_comments()
    else:
        comment_source = repo.get_issue(number).get_comments()

    comments = []
    truncated = False
    for comment in comment_source:
        if len(comments) >= limit:
            truncated = True
            break
        comments.append({
            "id": comment.id,
            "author": comment.user.login if comment.user else None,
            "body": comment.body,
            "created_at": comment.created_at.isoformat(),
            "updated_at": comment.updated_at.isoformat(),
            "html_url": comment.html_url
        })

    return {
        "comments": comments,
        "count": len(comments),
        "truncated": truncated,
        "limit": limit
    }


@_tool(read_only=False, destructive=False, idempotent=False, open_world=True)
@mcp_tool_handler
def github_create_pr(
    title: str,
    body: str = "",
    head: str = "",
    base: str = "main",
    labels: Optional[str] = None,
    repo_path: str = ".",
    idempotency_key: Optional[str] = None
) -> dict:
    """Create a pull request.

    Opening a PR is not idempotent. GitHub rejects a second open PR for the
    same head/base pair, but a retry issued after a lost response still costs a
    confusing 422 that is indistinguishable from a genuine conflict. Supply
    ``idempotency_key`` -- generated once per logical intent and reused
    unchanged across every retry -- to replay the original result instead.

    Args:
        title: PR title
        body: PR description (markdown)
        head: Source branch name
        base: Target branch (default: main)
        labels: Comma-separated label names
        repo_path: Local repo path
        idempotency_key: Optional caller-generated key scoped to one logical
            PR-creation intent.

    Returns:
        Dict with pr_number, pr_url, created_at, and labels_failed listing any
        label that could not be attached.
    """
    if not head:
        raise ValueError("head branch is required")

    def _create() -> dict:
        """Perform the underlying non-idempotent pull request creation."""
        repo = GitHubApiClient.instance().get_repo(repo_path)
        pr = repo.create_pull(title=title, body=body, head=head, base=base)

        labels_failed = []
        if labels:
            label_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
            for label in label_list:
                try:
                    pr.add_to_labels(label)
                except GithubException as exc:
                    labels_failed.append({"label": label, "error": str(exc)[:200]})

        return {
            "pr_number": pr.number,
            "pr_url": pr.html_url,
            "created_at": pr.created_at.isoformat(),
            "labels_failed": labels_failed
        }

    return run_once("github_create_pr", idempotency_key, _create)


@_tool(read_only=False, destructive=True, idempotent=False, open_world=True)
@mcp_tool_handler
def github_merge_pr(
    number: int,
    method: str = "squash",
    delete_branch: bool = True,
    commit_message: Optional[str] = None,
    repo_path: str = "."
) -> dict:
    """Merge a pull request with gh CLI fallback for safety.

    Merging is irreversible, so the failure path is deliberately conservative.
    If the PyGithub merge call raises, the PR state is re-read before anything
    else happens: a merge that landed server-side but whose response was lost
    reports ``merged`` true on that re-read, and this tool returns success
    rather than re-issuing the merge through the CLI. Falling back blindly on
    any exception would turn an ambiguous outcome into a second merge attempt
    against a repository whose state has already changed.

    ``pr.mergeable`` is null while GitHub computes mergeability in the
    background. Null is reported as unknown rather than collapsed into
    "conflicts exist", because treating a pending computation as a conflict
    blocks merges that would have succeeded moments later.

    Args:
        number: PR number
        method: Merge method - 'merge', 'squash', or 'rebase'
        delete_branch: Delete source branch after merge
        commit_message: Custom merge commit message (default: 'Merge PR #N')
        repo_path: Local repo path
    """
    merge_msg = commit_message or f"Merge PR #{number}"

    # Primary: PyGithub
    try:
        repo = GitHubApiClient.instance().get_repo(repo_path)
        pr = repo.get_pull(number)

        if pr.merged:
            return {
                "pr_number": number,
                "merged": True,
                "method": method,
                "branch_deleted": False,
                "already_merged": True
            }

        if pr.mergeable is None:
            return {
                "success": False,
                "error": (
                    f"PR #{number} mergeability is still being computed by "
                    "GitHub. Retry shortly; do not treat this as a conflict."
                )
            }

        if pr.mergeable is False:
            return {
                "success": False,
                "error": f"PR #{number} is not mergeable (conflicts exist)"
            }

        pr.merge(
            commit_message=merge_msg,
            merge_method=method
        )

        branch_deleted = False
        branch_delete_error = None
        if delete_branch:
            try:
                ref = repo.get_git_ref(f"heads/{pr.head.ref}")
                ref.delete()
                branch_deleted = True
            except GithubException as exc:
                branch_delete_error = str(exc)[:200]

        result = {
            "pr_number": number,
            "merged": True,
            "method": method,
            "branch_deleted": branch_deleted
        }
        if branch_delete_error:
            result["branch_delete_error"] = branch_delete_error
        return result
    except Exception as primary_err:
        if _pr_is_merged(number, repo_path):
            return {
                "pr_number": number,
                "merged": True,
                "method": method,
                "branch_deleted": False,
                "already_merged": True,
                "note": (
                    "The merge landed upstream but the API call raised "
                    f"({type(primary_err).__name__}). No second merge was "
                    "attempted."
                )
            }

        fallback = _gh_cli_merge_fallback(number, method, delete_branch, merge_msg)
        if fallback and fallback.get("success"):
            return fallback
        if fallback:
            raise RuntimeError(
                f"Merge of PR #{number} failed. Primary: {primary_err}. "
                f"Fallback: {fallback.get('fallback_error', 'unknown')}"
            ) from primary_err
        raise


@_tool(read_only=True, destructive=False, idempotent=True, open_world=True)
@mcp_tool_handler
def github_list_issues(
    labels: Optional[str] = None,
    state: str = "open",
    repo_path: str = ".",
    limit: int = 100
) -> dict:
    """List issues in the repository, excluding pull requests.

    The returned ``truncated`` flag reports whether more issues matched than
    were returned. A caller that treats an un-flagged short result as complete
    is safe; a caller that ignores the flag is not. This matters because the
    previous implementation sliced the first 25 results silently, and callers
    read the short list as exhaustive.

    Pull requests are filtered before the limit is applied, not after. GitHub
    shares one number space between issues and PRs, so slicing first meant a
    repository with many PRs could return far fewer than ``limit`` issues while
    more existed -- on one observed run, 9 issues came back from 25 fetched
    rows while the number space reached 257.

    Args:
        labels: Comma-separated label filter
        state: 'open', 'closed', or 'all'
        repo_path: Local repo path
        limit: Maximum issues to return. Pagination is handled by PyGithub, so
            raising this costs additional API calls rather than failing.

    Returns:
        Dict with ``issues``, ``count``, ``truncated`` and the effective
        ``limit``.
    """
    repo = GitHubApiClient.instance().get_repo(repo_path)

    kwargs = {"state": state}
    if labels:
        label_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
        kwargs["labels"] = [repo.get_label(lbl) for lbl in label_list]

    issues = []
    truncated = False
    for issue in repo.get_issues(**kwargs):
        if issue.pull_request:
            continue
        if len(issues) >= limit:
            truncated = True
            break
        issues.append({
            "number": issue.number,
            "title": issue.title,
            "state": issue.state,
            "labels": [lbl.name for lbl in issue.labels],
            "created_at": issue.created_at.isoformat()
        })

    return {
        "issues": issues,
        "count": len(issues),
        "truncated": truncated,
        "limit": limit
    }


@_tool(read_only=True, destructive=False, idempotent=True, open_world=True)
@mcp_tool_handler
def github_get_issue(number: int, repo_path: str = ".") -> dict:
    """Get full detail for a single issue by number, including body and state.

    github_list_issues returns a page of per-issue summaries (title, state,
    labels, created_at) with no body text, so a caller that needs to check
    one specific issue's current state or read its description has no tool
    to reach for -- it must re-list and hope the issue is on the first page,
    or grep a local copy of the issue text that may already be stale.

    Args:
        number: Issue number
        repo_path: Local repo path

    Raises:
        ValueError: If ``number`` identifies a pull request rather than an
            issue -- GitHub shares one number space between the two, and a PR
            returned here would silently present as an issue with no body.
    """
    repo = GitHubApiClient.instance().get_repo(repo_path)
    issue = repo.get_issue(number)

    if issue.pull_request is not None:
        raise ValueError(
            f"#{number} is a pull request, not an issue. "
            "Use github_get_pr_status for pull request detail."
        )

    return {
        "issue_number": issue.number,
        "title": issue.title,
        "body": issue.body or "",
        "state": issue.state,
        "labels": [lbl.name for lbl in issue.labels],
        "assignees": [a.login for a in issue.assignees],
        "comments": issue.comments,
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
        "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
        "html_url": issue.html_url,
    }


@_tool(read_only=True, destructive=False, idempotent=True, open_world=True)
@mcp_tool_handler
def github_get_pr_status(number: int, repo_path: str = ".") -> dict:
    """Get pull request status and check details.

    Args:
        number: PR number
        repo_path: Local repo path
    """
    repo = GitHubApiClient.instance().get_repo(repo_path)
    pr = repo.get_pull(number)

    checks = []
    try:
        commit = repo.get_commit(pr.head.sha)
        for status in commit.get_statuses():
            checks.append({
                "context": status.context,
                "state": status.state,
                "description": status.description
            })
    except Exception:
        pass

    return {
        "pr_number": number,
        "title": pr.title,
        "state": pr.state,
        "mergeable": pr.mergeable,
        "merged": pr.merged,
        "head": pr.head.ref,
        "base": pr.base.ref,
        "checks": checks,
        "review_comments": pr.review_comments,
        "commits": pr.commits
    }


# =============================================================================
# PR WORKFLOW + ISSUE MANAGEMENT (Enhanced from github_pr_workflow.py + github_issue_manager.py)
# =============================================================================

@_tool(read_only=False, destructive=False, idempotent=False, open_world=True)
@mcp_tool_handler
def github_create_issue_branch(
    issue_number: int,
    subject: str,
    issue_type: str = "feature",
    repo_path: str = "."
) -> dict:
    """Create a git branch linked to a GitHub issue.

    Branch format: {type}/issue-{number}-{slugified-subject}

    Args:
        issue_number: GitHub issue number
        subject: Issue subject (used for branch name)
        issue_type: 'feature', 'fix', 'refactor', 'docs', 'test'
        repo_path: Local repo path
    """
    import re as _re

    # Slugify subject
    slug = _re.sub(r"[^a-z0-9]+", "-", subject.lower())[:40].strip("-")
    prefix_map = {
        "feature": "feature", "fix": "fix", "bugfix": "fix",
        "refactor": "refactor", "docs": "docs", "test": "test",
    }
    prefix = prefix_map.get(issue_type, "feature")
    branch_name = f"{prefix}/issue-{issue_number}-{slug}"

    # Create branch via GitPython or fallback to subprocess
    try:
        repo = GitRepoClient.for_path(repo_path)
        origin = repo.remotes.origin

        # Stash if dirty
        had_stash = False
        if repo.is_dirty(untracked_files=True):
            repo.git.stash("push", "--include-untracked", "-m", f"auto-stash-{branch_name}")
            had_stash = True

        try:
            origin.fetch("main")
            repo.git.checkout("-b", branch_name, "FETCH_HEAD")
        except Exception:
            repo.git.checkout("-b", branch_name)

        if had_stash:
            try:
                repo.git.stash("pop")
            except Exception:
                pass

        try:
            origin.push(branch_name, set_upstream=True)
        except Exception:
            pass

        return {
            "branch": branch_name,
            "issue_number": issue_number,
            "stash_restored": had_stash
        }
    except RuntimeError:
        # GitPython not available - fallback to subprocess
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            capture_output=True, text=True, timeout=15, cwd=repo_path
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git checkout failed")
        return {
            "branch": branch_name,
            "issue_number": issue_number
        }


@_tool(read_only=False, destructive=False, idempotent=False, open_world=True)
@mcp_tool_handler
def github_auto_commit_and_pr(
    title: str,
    body: str = "",
    base: str = "main",
    labels: Optional[str] = None,
    repo_path: str = ".",
    idempotency_key: Optional[str] = None
) -> dict:
    """Auto-commit all changes and create a PR in one step.

    Workflow: stage all -> commit -> push -> create PR

    This composes three non-idempotent steps and is the most damaging tool on
    this server to retry blind: a retry after a lost response can produce a
    second commit and a second PR. Supply ``idempotency_key``, generated once
    per logical intent and reused unchanged across every retry, so a repeat
    call replays the recorded outcome instead of re-running the workflow.

    Args:
        title: PR title (also used as commit message)
        body: PR description
        base: Target branch
        labels: Comma-separated labels
        repo_path: Local repo path
        idempotency_key: Optional caller-generated key scoped to one logical
            commit-and-open-PR intent.

    Returns:
        Dict with commit, branch, pr_number, pr_url, and labels_failed listing
        any label that could not be attached.
    """
    def _commit_and_open() -> dict:
        """Perform the underlying non-idempotent commit-push-open-PR workflow."""
        repo = GitRepoClient.for_path(repo_path)

        if not repo.is_dirty(untracked_files=True):
            raise ValueError("No changes to commit")

        branch = str(repo.active_branch)

        repo.git.add("-A")
        commit = repo.index.commit(title)

        origin = repo.remotes.origin
        try:
            origin.push(branch, set_upstream=True)
        except Exception as push_err:
            raise RuntimeError(f"Push failed: {push_err}") from push_err

        gh_repo = GitHubApiClient.instance().get_repo(repo_path)
        pr = gh_repo.create_pull(title=title, body=body, head=branch, base=base)

        labels_failed = []
        if labels:
            for label in [lbl.strip() for lbl in labels.split(",") if lbl.strip()]:
                try:
                    pr.add_to_labels(label)
                except GithubException as exc:
                    labels_failed.append({"label": label, "error": str(exc)[:200]})

        return {
            "commit": str(commit.hexsha)[:7],
            "branch": branch,
            "pr_number": pr.number,
            "pr_url": pr.html_url,
            "labels_failed": labels_failed,
        }

    return run_once(
        "github_auto_commit_and_pr", idempotency_key, _commit_and_open
    )


@_tool(read_only=False, destructive=False, idempotent=False, open_world=True)
@mcp_tool_handler
def github_validate_build(repo_path: str = ".") -> dict:
    """Run project build validation before PR.

    Auto-detects build system (npm, gradle, pip, cargo) and runs appropriate check.

    Args:
        repo_path: Project root path
    """
    root = Path(repo_path).resolve()

    build_cmd = None
    build_system = "unknown"

    if (root / "package.json").exists():
        build_system = "npm"
        try:
            pkg = json.loads((root / "package.json").read_text())
            if "build" in pkg.get("scripts", {}):
                build_cmd = ["npm", "run", "build"]
            elif "test" in pkg.get("scripts", {}):
                build_cmd = ["npm", "test"]
        except Exception:
            pass
    elif (root / "pom.xml").exists():
        build_system = "maven"
        build_cmd = ["mvn", "compile", "-q"]
    elif (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        build_system = "gradle"
        build_cmd = ["gradle", "build", "-q"]
    elif (root / "requirements.txt").exists() or (root / "setup.py").exists():
        build_system = "python"
        if (root / "tests").exists():
            build_cmd = ["python", "-m", "pytest", "--co", "-q"]
        else:
            build_cmd = ["python", "-c", "import py_compile; print('OK')"]
    elif (root / "Cargo.toml").exists():
        build_system = "cargo"
        build_cmd = ["cargo", "check"]

    if not build_cmd:
        return {
            "build_system": build_system,
            "validated": False,
            "message": "No build system detected"
        }

    result = subprocess.run(
        build_cmd, capture_output=True, text=True,
        timeout=120, cwd=str(root)
    )

    return {
        "build_system": build_system,
        "validated": result.returncode == 0,
        "command": " ".join(build_cmd),
        "exit_code": result.returncode,
        "stdout": result.stdout[:500] if result.stdout else "",
        "stderr": result.stderr[:500] if result.stderr else "",
    }


@_tool(read_only=False, destructive=False, idempotent=True, open_world=True)
@mcp_tool_handler
def github_label_issue(
    number: int,
    labels: str,
    repo_path: str = "."
) -> dict:
    """Add labels to an issue or PR.

    Adding a label the issue already carries is a no-op upstream, so this tool
    is genuinely idempotent and safe to retry without a key.

    Args:
        number: Issue or PR number
        labels: Comma-separated label names
        repo_path: Local repo path

    Returns:
        Dict with issue_number, labels_added, labels_failed (name plus the
        reason each rejected label could not be attached), and total_labels.
    """
    repo = GitHubApiClient.instance().get_repo(repo_path)
    issue = repo.get_issue(number)
    label_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]

    added = []
    failed = []
    for label in label_list:
        try:
            issue.add_to_labels(label)
            added.append(label)
        except GithubException as exc:
            failed.append({"label": label, "error": str(exc)[:200]})

    return {
        "issue_number": number,
        "labels_added": added,
        "labels_failed": failed,
        "total_labels": [lbl.name for lbl in issue.labels]
    }


@_tool(read_only=False, destructive=False, idempotent=True, open_world=True)
@mcp_tool_handler
def github_create_label(
    repo: str,
    name: str,
    color: str,
    description: str = ""
) -> dict:
    """Create a new label in a GitHub repository.

    Creates the label with the given name, hex color, and optional description.
    Returns the existing label (with already_exists: true) if the label name
    already exists -- enabling idempotent pipeline calls.

    Args:
        repo: Repository in 'owner/repo' format, e.g. 'techdeveloper-org/my-app'.
        name: Label name (1-50 characters).
        color: Hex color without '#', e.g. '0075ca'. Leading '#' is stripped if present.
        description: Optional label description.

    Returns:
        Dict with name, color, description, url, already_exists fields.

    Raises:
        ValueError: If repo format is invalid, name exceeds 50 chars, color is not
            valid hex, description exceeds 1000 chars, or repo is inaccessible.
    """
    repo = validate_input(repo, max_length=200, field_name="repo")
    if not repo or "/" not in repo or repo.startswith("/") or repo.endswith("/"):
        raise ValueError("repo must be in 'owner/repo' format")

    name = validate_input(name, max_length=50, field_name="name")
    if not name or len(name) > 50:
        raise ValueError("Label name must be 1-50 characters")

    color = color.lstrip("#")
    if len(color) != 6 or not all(c in "0123456789abcdefABCDEF" for c in color):
        raise ValueError("Color must be 6 hex characters without #")

    description = validate_input(description, max_length=1000, field_name="description")

    client = GitHubApiClient.instance().get_or_raise()
    gh_repo = client.get_repo(repo)

    try:
        label = gh_repo.create_label(name=name, color=color, description=description)
        return {
            "name": label.name,
            "color": label.color,
            "description": label.description or "",
            "url": label.url,
            "already_exists": False
        }
    except GithubException as e:
        if e.status == 422:
            try:
                existing = gh_repo.get_label(name)
                return {
                    "name": existing.name,
                    "color": existing.color,
                    "description": existing.description or "",
                    "url": existing.url,
                    "already_exists": True
                }
            except GithubException:
                raise ValueError(f"Label '{name}' conflict but could not be retrieved")
        if e.status == 404:
            raise ValueError(f"Repository {repo} not found or no access")
        if e.status == 403:
            raise ValueError(f"Token lacks write permission on {repo}")
        raise


@_tool(read_only=False, destructive=False, idempotent=True, open_world=True)
@mcp_tool_handler
def github_create_milestone(
    repo: str,
    title: str,
    description: str = "",
    due_on: str = "",
    state: str = "open"
) -> dict:
    """Create a new Milestone in a GitHub repository.

    Milestones act as Sprint containers in the GitHub Issues-based sprint planning
    workflow. Issues assigned to a milestone form the sprint backlog.
    Returns the existing milestone (with already_exists: true) if a milestone with
    the same title already exists -- enabling idempotent pipeline calls.

    Args:
        repo: Repository in 'owner/repo' format, e.g. 'techdeveloper-org/my-app'.
        title: Milestone title, e.g. 'Sprint 1'.
        description: Sprint goal or milestone description.
        due_on: Due date as 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SSZ'. Empty = no due date.
        state: 'open' or 'closed' (default: 'open').

    Returns:
        Dict with number, title, description, due_on, state, open_issues, html_url,
        already_exists fields.

    Raises:
        ValueError: If repo format is invalid, title is empty or exceeds 255 chars,
            description exceeds 1000 chars, state is invalid, due_on format is
            unrecognized, or repo is inaccessible.
    """
    repo = validate_input(repo, max_length=200, field_name="repo")
    if not repo or "/" not in repo or repo.startswith("/") or repo.endswith("/"):
        raise ValueError("repo must be in 'owner/repo' format")

    title = validate_input(title, max_length=255, field_name="title")
    if not title:
        raise ValueError("Milestone title must not be empty")

    description = validate_input(description, max_length=1000, field_name="description")

    if state not in ("open", "closed"):
        raise ValueError("state must be 'open' or 'closed'")

    due_date = None
    if due_on:
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                due_date = datetime.strptime(due_on.strip(), fmt)
                break
            except ValueError:
                continue
        if due_date is None:
            raise ValueError("due_on must be YYYY-MM-DD or ISO 8601 format")

    client = GitHubApiClient.instance().get_or_raise()
    gh_repo = client.get_repo(repo)

    kwargs = {"title": title, "state": state, "description": description}
    if due_date:
        kwargs["due_on"] = due_date

    try:
        ms = gh_repo.create_milestone(**kwargs)
        return {
            "number": ms.number,
            "title": ms.title,
            "description": ms.description or "",
            "due_on": ms.due_on.isoformat() if ms.due_on else None,
            "state": ms.state,
            "open_issues": ms.open_issues,
            "html_url": ms.html_url,
            "already_exists": False
        }
    except GithubException as e:
        if e.status == 422:
            for i, existing in enumerate(gh_repo.get_milestones(state="all")):
                if i >= 500:
                    raise ValueError(f"Milestone '{title}' not found in first 500 milestones")
                if existing.title == title:
                    return {
                        "number": existing.number,
                        "title": existing.title,
                        "description": existing.description or "",
                        "due_on": existing.due_on.isoformat() if existing.due_on else None,
                        "state": existing.state,
                        "open_issues": existing.open_issues,
                        "html_url": existing.html_url,
                        "already_exists": True
                    }
        if e.status == 404:
            raise ValueError(f"Repository {repo} not found or no access")
        if e.status == 403:
            raise ValueError(f"Token lacks write permission on {repo}")
        raise


@_tool(read_only=False, destructive=True, idempotent=False, open_world=True)
@mcp_tool_handler
def github_full_merge_cycle(
    number: int,
    method: str = "squash",
    validate_build: bool = True,
    repo_path: str = "."
) -> dict:
    """Full merge cycle: validate build -> merge PR -> cleanup branch.

    Args:
        number: PR number
        method: Merge method ('merge', 'squash', 'rebase')
        validate_build: Run build validation before merge
        repo_path: Local repo path
    """
    steps_completed = []

    # Step 1: Build validation (optional)
    if validate_build:
        build_result = json.loads(github_validate_build(repo_path))
        steps_completed.append({
            "step": "build_validation",
            "success": build_result.get("validated", False),
            "system": build_result.get("build_system", "unknown")
        })
        if not build_result.get("validated", True):
            return {
                "success": False,
                "error": "Build validation failed",
                "steps": steps_completed
            }

    # Step 2: Check PR is mergeable
    repo = GitHubApiClient.instance().get_repo(repo_path)
    pr = repo.get_pull(number)
    if pr.mergeable is None:
        return {
            "success": False,
            "error": (
                f"PR #{number} mergeability is still being computed by GitHub. "
                "Retry shortly; this is not a conflict."
            ),
            "steps": steps_completed
        }
    if pr.mergeable is False:
        return {
            "success": False,
            "error": f"PR #{number} has conflicts",
            "steps": steps_completed
        }
    steps_completed.append({"step": "mergeable_check", "success": True})

    # Step 3: Merge
    merge_result = json.loads(github_merge_pr(
        number=number, method=method, delete_branch=True,
        repo_path=repo_path
    ))
    steps_completed.append({
        "step": "merge",
        "success": merge_result.get("success", False)
    })

    if not merge_result.get("success"):
        return {
            "success": False,
            "error": merge_result.get("error", "Merge failed"),
            "steps": steps_completed
        }

    return {
        "pr_number": number,
        "method": method,
        "steps": steps_completed,
        "message": f"PR #{number} merged successfully"
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
