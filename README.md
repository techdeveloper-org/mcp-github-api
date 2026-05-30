# mcp-github-api

![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Part of claude-workflow-engine](https://img.shields.io/badge/Part%20of-claude--workflow--engine-lightgrey)

A FastMCP server that exposes GitHub operations as Claude Code tools via stdio JSON-RPC. Provides 14 tools covering the full GitHub development lifecycle: issue creation, branch management, pull request creation and review, merge operations with conflict detection, label and milestone management, build validation, and full automated merge cycles. Part of the [Claude Workflow Engine](https://github.com/techdeveloper-org/claude-workflow-engine) ecosystem of 13 MCP servers.

---

## Features

- Create, list, label, and close GitHub issues
- Create feature branches linked to issues with automatic slug generation
- Create and merge pull requests (squash, merge, rebase) with `gh` CLI fallback for safety
- Check PR status, check runs, and merge readiness
- Add comments to issues and pull requests
- Create repository labels with idempotent behavior (returns existing on 422)
- Create sprint milestones with optional due dates and idempotent behavior
- Auto-commit staged changes and open a PR in a single tool call
- Build validation before merge — auto-detects npm, Maven, Gradle, Python, and Cargo projects
- Full merge cycle: build check + mergeability check + merge + branch cleanup in one call
- PyGithub primary path with `gh` CLI fallback on merge operations
- Shared `base/` library for consistent response formatting and client lifecycle

---

## Tool Reference

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `github_create_issue` | Create a GitHub issue | `title`, `body`, `labels`, `assignee`, `repo_path` |
| `github_close_issue` | Close an issue with optional closing comment | `number`, `comment`, `repo_path` |
| `github_add_comment` | Add a comment to an issue or PR | `number`, `body`, `type` (`issue`/`pr`), `repo_path` |
| `github_create_pr` | Create a pull request | `title`, `body`, `head`, `base`, `labels`, `repo_path` |
| `github_merge_pr` | Merge a PR (PyGithub + gh CLI fallback) | `number`, `method`, `delete_branch`, `commit_message`, `repo_path` |
| `github_list_issues` | List repository issues with optional filters | `labels`, `state`, `repo_path` |
| `github_get_pr_status` | Get PR state, checks, and review details | `number`, `repo_path` |
| `github_create_issue_branch` | Create a git branch linked to a GitHub issue | `issue_number`, `subject`, `issue_type`, `repo_path` |
| `github_auto_commit_and_pr` | Stage all changes, commit, push, and open a PR | `title`, `body`, `base`, `labels`, `repo_path` |
| `github_validate_build` | Run build validation before PR (auto-detects build system) | `repo_path` |
| `github_label_issue` | Add labels to an issue or PR | `number`, `labels`, `repo_path` |
| `github_create_label` | Create a repo label — returns existing if already present (idempotent) | `repo`, `name`, `color`, `description` |
| `github_create_milestone` | Create a sprint milestone — returns existing if title matches (idempotent) | `repo`, `title`, `description`, `due_on`, `state` |
| `github_full_merge_cycle` | Full cycle: build validate + mergeability + merge + cleanup | `number`, `method`, `validate_build`, `repo_path` |

### Parameter Details

**`github_create_issue`**
- `title` (required) — Issue title
- `body` — Issue description, markdown supported
- `labels` — Comma-separated label names, e.g. `"bug,priority-high"`
- `assignee` — GitHub username to assign
- `repo_path` — Local repo path for owner/repo auto-detection (default: `"."`)

**`github_create_pr`**
- `title` (required) — PR title
- `head` (required) — Source branch name
- `body` — PR description, markdown supported
- `base` — Target branch (default: `"main"`)
- `labels` — Comma-separated label names

**`github_merge_pr`**
- `number` (required) — PR number
- `method` — `"merge"`, `"squash"`, or `"rebase"` (default: `"squash"`)
- `delete_branch` — Delete source branch after merge (default: `true`)
- `commit_message` — Custom merge commit message (default: `"Merge PR #N"`)

**`github_create_issue_branch`**
- `issue_number` (required) — GitHub issue number
- `subject` (required) — Subject text used to build branch slug
- `issue_type` — `"feature"`, `"fix"`, `"refactor"`, `"docs"`, or `"test"` (default: `"feature"`)
- Branch format produced: `{type}/issue-{number}-{slugified-subject}`

**`github_create_label`**
- `repo` (required) — Repository in `"owner/repo"` format
- `name` (required) — Label name, 1–50 characters
- `color` (required) — 6-character hex color without `#`, e.g. `"0075ca"`. Leading `#` is stripped automatically.
- `description` — Optional label description (max 1000 chars)
- Returns `already_exists: true` when the label name already exists instead of raising

**`github_create_milestone`**
- `repo` (required) — Repository in `"owner/repo"` format
- `title` (required) — Milestone title, e.g. `"Sprint 1"` (max 255 chars)
- `description` — Sprint goal or description (max 1000 chars)
- `due_on` — Due date as `"YYYY-MM-DD"` or `"YYYY-MM-DDTHH:MM:SSZ"`. Omit for no due date.
- `state` — `"open"` or `"closed"` (default: `"open"`)
- Returns `already_exists: true` when a milestone with the same title already exists

**`github_full_merge_cycle`**
- `number` (required) — PR number
- `method` — Merge method (default: `"squash"`)
- `validate_build` — Run build validation before merge (default: `true`)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/techdeveloper-org/mcp-github-api.git
cd mcp-github-api
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Core dependencies: `fastmcp`, `PyGithub`, `gitpython`

### 3. Configure in Claude Code

Add the server to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "github-api": {
      "command": "python",
      "args": ["C:/path/to/mcp-github-api/server.py"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

Replace `C:/path/to/mcp-github-api/server.py` with the absolute path on your machine.

---

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | GitHub personal access token with `repo` scope. Create at: Settings > Developer settings > Personal access tokens |

### Token Scopes Required

The `GITHUB_TOKEN` must have the following scopes:
- `repo` — Full control of private and public repositories (issues, PRs, branches)
- `read:org` — Required if targeting organization repositories

---

## Usage Examples

### Create an issue and branch

```python
# Create an issue
github_create_issue(
    title="Add rate limiting to API endpoints",
    body="We need token bucket rate limiting on all public endpoints.\n\n**Acceptance Criteria:**\n- 100 requests/min per client\n- Returns 429 with Retry-After header",
    labels="enhancement,priority-high",
    assignee="myusername"
)
# Returns: {"issue_number": 42, "issue_url": "https://github.com/org/repo/issues/42", ...}

# Create a linked branch
github_create_issue_branch(
    issue_number=42,
    subject="Add rate limiting to API endpoints",
    issue_type="feature"
)
# Returns: {"branch": "feature/issue-42-add-rate-limiting-to-api-endpoints", ...}
```

### Create a pull request and check its status

```python
# Create the PR after committing your changes
github_create_pr(
    title="feat: add token bucket rate limiting",
    body="Closes #42\n\n## Changes\n- Added TokenBucket class\n- Applied to all public route handlers\n- Returns 429 with Retry-After header",
    head="feature/issue-42-add-rate-limiting-to-api-endpoints",
    base="main",
    labels="enhancement"
)
# Returns: {"pr_number": 15, "pr_url": "https://github.com/org/repo/pull/15", ...}

# Check PR status
github_get_pr_status(number=15)
# Returns: {"state": "open", "mergeable": true, "checks": [...], "review_comments": 2, ...}
```

### Run a full merge cycle

```python
# Validate build, check merge readiness, merge, and delete branch
github_full_merge_cycle(
    number=15,
    method="squash",
    validate_build=True
)
# Returns: {"pr_number": 15, "method": "squash", "steps": [...], "message": "PR #15 merged successfully"}
```

### Set up sprint labels and a milestone (Phase 6 sprint planning)

```python
# Create a label — safe to call multiple times, returns existing on duplicate
github_create_label(
    repo="techdeveloper-org/my-app",
    name="type:epic",
    color="0075ca",
    description="Epic issue grouping feature stories"
)
# Returns: {"name": "type:epic", "color": "0075ca", "already_exists": false, ...}

# Call again on the same repo — no error, returns the existing label
github_create_label(
    repo="techdeveloper-org/my-app",
    name="type:epic",
    color="0075ca"
)
# Returns: {"name": "type:epic", "color": "0075ca", "already_exists": true, ...}

# Create a sprint milestone with a due date
github_create_milestone(
    repo="techdeveloper-org/my-app",
    title="Sprint 1",
    description="Goal: deliver user auth and order creation",
    due_on="2026-06-13"
)
# Returns: {"number": 1, "title": "Sprint 1", "due_on": "2026-06-13T00:00:00", "already_exists": false, ...}
```

### Auto-commit and open a PR in one step

```python
# Stage all local changes, commit, push, and create PR atomically
github_auto_commit_and_pr(
    title="fix: correct null check in user service",
    body="Fixes an unhandled None case when user profile is incomplete.",
    base="main",
    labels="bug"
)
# Returns: {"commit": "a3f9b12", "branch": "fix/...", "pr_number": 16, "pr_url": "..."}
```

---

## Integration with Claude Workflow Engine

This server is the GitHub integration layer for the Claude Workflow Engine's 8-step execution pipeline. It is invoked at three pipeline steps:

### Step 8 — Issue Creation

At the start of every task, the pipeline calls `github_create_issue` to create a tracked GitHub issue. The issue URL is stored in pipeline state and linked to any Jira issue created in the same step (when `ENABLE_JIRA=1`).

```
Step 8:
  github_create_issue(title, body, labels) -> issue_number stored in state
  (optional) jira_create_issue cross-linked to GitHub issue number
```

### Step 9 — Branch Creation

The pipeline creates a feature branch linked to the issue number created in Step 8.

```
Step 9:
  github_create_issue_branch(issue_number, subject, issue_type) -> branch_name stored in state
```

### Step 11 — PR Creation, Review, and Merge

After implementation completes, Step 11 calls this server to:
1. Create the pull request from the implementation branch (`github_create_pr`)
2. Validate the build (`github_validate_build`)
3. Merge once CI passes and reviews are approved (`github_merge_pr` or `github_full_merge_cycle`)

```
Step 11:
  github_create_pr(head=feature_branch, base=main) -> pr_number
  github_validate_build() -> build pass/fail
  github_merge_pr(number, method="squash") -> merged
```

When `ENABLE_JIRA=1`, the Jira issue is transitioned to "In Review" and the PR URL is linked to the Jira ticket during this step.

### Step 12 — Issue Closure

After the PR is merged, Step 12 closes the original GitHub issue and adds a closing summary comment.

```
Step 12:
  github_add_comment(number=issue_number, body="Implemented in PR #N")
  github_close_issue(number=issue_number)
```

### Phase 6 — Sprint Planning

Before sprint work begins, Phase 6 calls `github_create_label` and `github_create_milestone` to provision the GitHub board for the new sprint. Both tools are idempotent — safe to call on every pipeline run without checking whether labels or milestones already exist.

```
Phase 6:
  github_create_label(repo, name, color) × N    -> labels created or confirmed existing
  github_create_milestone(repo, title, due_on)  -> sprint milestone created or confirmed existing
```

### Pipeline Wiring Summary

| Pipeline Step | Tools Used | Purpose |
|---------------|-----------|---------|
| Phase 6 | `github_create_label`, `github_create_milestone` | Provision sprint labels and milestone |
| Step 8 | `github_create_issue` | Track task as a GitHub issue |
| Step 9 | `github_create_issue_branch` | Create feature branch linked to issue |
| Step 11 | `github_create_pr`, `github_validate_build`, `github_merge_pr` | PR lifecycle |
| Step 12 | `github_add_comment`, `github_close_issue` | Close issue after merge |

---

## Build Validation Detection

`github_validate_build` automatically detects the project's build system and runs the appropriate check command:

| Build System | Detection File | Command Run |
|--------------|---------------|-------------|
| npm | `package.json` | `npm run build` or `npm test` |
| Maven | `pom.xml` | `mvn compile -q` |
| Gradle | `build.gradle` / `build.gradle.kts` | `gradle build -q` |
| Python | `requirements.txt` / `setup.py` | `pytest --co -q` or syntax check |
| Cargo | `Cargo.toml` | `cargo check` |

---

## Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Make your changes with tests
4. Open a pull request against `main`

Please follow the existing code style (PEP 8, type hints, `@mcp_tool_handler` decorator on all tools).

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Related

- [claude-workflow-engine](https://github.com/techdeveloper-org/claude-workflow-engine) — Parent orchestration pipeline
- [mcp-base](https://github.com/techdeveloper-org/mcp-base) — Shared base library used by all 13 servers
- [mcp-git-ops](https://github.com/techdeveloper-org/mcp-git-ops) — Git operations (branch, commit, push, diff)
- [mcp-jira-api](https://github.com/techdeveloper-org/mcp-jira-api) — Jira issue tracking integration
