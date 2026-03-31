# mcp-github-api

A FastMCP server providing **Github Api** capabilities for Claude Code workflows.

---

## Overview

GitHub repository operations via PyGithub with gh CLI fallback for merge operations. Creates and manages issues, pull requests, comments, labels, and runs full merge cycles with optional build validation gates.

---

## Tools

| Tool | Description |
|------|-------------|
| `github_create_issue` | Create a GitHub issue with title, body, labels, assignees |
| `github_close_issue` | Close an issue with a closing comment |
| `github_add_comment` | Add a comment to an issue or PR |
| `github_create_pr` | Create a pull request from a branch with title and body |
| `github_merge_pr` | Merge a PR (squash/merge/rebase strategies supported) |
| `github_list_issues` | List open/closed issues with filters |
| `github_get_pr_status` | Get PR status: checks, reviews, mergability |
| `github_create_issue_branch` | Create a branch named from an issue number |
| `github_auto_commit_and_pr` | Commit staged changes and open a PR automatically |
| `github_validate_build` | Wait for CI checks to pass before proceeding |
| `github_label_issue` | Add or remove labels from an issue |
| `github_full_merge_cycle` | Full cycle: build validate -> merge PR -> close issue -> cleanup |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/techdeveloper-org/mcp-github-api.git
cd mcp-github-api
```

### 2. Install dependencies

```bash
pip install mcp fastmcp PyGithub
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

---

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub personal access token (required) |
| `GITHUB_REPO` | Default repo in owner/repo format (optional) |

---

## Usage in Claude Code

Add to your `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "github-api": {
      "command": "python",
      "args": [
        "/path/to/mcp-github-api/server.py"
      ],
      "env": {}
    }
  }
}
```

---

## Benefits

- Full SDLC integration: issue -> branch -> PR -> merge -> close in one pipeline
- Build validation gate prevents merging broken code
- PyGithub library provides rich object model; gh CLI handles edge cases
- auto_commit_and_pr reduces 5 manual steps to 1 tool call

---

## Requirements

- Python 3.8+
- `mcp fastmcp PyGithub`
- See `requirements.txt` for pinned versions

---

## Project Context

This MCP server is part of the **Claude Workflow Engine** ecosystem — a LangGraph-based
orchestration pipeline for automating Claude Code development workflows.

Related repos:
- [`claude-workflow-engine`](https://github.com/techdeveloper-org/claude-workflow-engine) — Main pipeline
- [`mcp-base`](https://github.com/techdeveloper-org/mcp-base) — Shared base utilities used by all MCP servers

---

## License

Private — techdeveloper-org
