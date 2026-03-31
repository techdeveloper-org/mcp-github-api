# mcp-github-api — Claude Project Context

**Type:** FastMCP Server
**Transport:** stdio
**Python:** 3.8+

---

## What This Server Does

GitHub repository operations via PyGithub with gh CLI fallback for merge operations. Creates and manages issues, pull requests, comments, labels, and runs full merge cycles with optional build validation gates.

---

## Entry Point

```
server.py
```

Run via `python server.py` — communicates over stdio using the MCP protocol.

---

## Available Tools

- `github_create_issue` — Create a GitHub issue with title, body, labels, assignees
- `github_close_issue` — Close an issue with a closing comment
- `github_add_comment` — Add a comment to an issue or PR
- `github_create_pr` — Create a pull request from a branch with title and body
- `github_merge_pr` — Merge a PR (squash/merge/rebase strategies supported)
- `github_list_issues` — List open/closed issues with filters
- `github_get_pr_status` — Get PR status: checks, reviews, mergability
- `github_create_issue_branch` — Create a branch named from an issue number
- `github_auto_commit_and_pr` — Commit staged changes and open a PR automatically
- `github_validate_build` — Wait for CI checks to pass before proceeding
- `github_label_issue` — Add or remove labels from an issue
- `github_full_merge_cycle` — Full cycle: build validate -> merge PR -> close issue -> cleanup

---

## Shared Utilities (in this repo)

- `base/` — Shared MCP infrastructure package (response builder, decorators, persistence, clients)
- `mcp_errors.py` — Structured error response helpers
- `input_validator.py` — Null-byte strip, length limits, prompt injection detection
- `rate_limiter.py` — Token bucket rate limiter (enable via ENABLE_RATE_LIMITING=1)

---

## Environment Variables

- `GITHUB_TOKEN` — GitHub personal access token (required)
- `GITHUB_REPO` — Default repo in owner/repo format (optional)

---

## Development

### Running locally

```bash
# Install deps
pip install -r requirements.txt

# Run the MCP server (stdio mode)
python server.py
```

### Testing a tool call manually

```python
import subprocess, json

proc = subprocess.Popen(
    ["python", "server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
)
# Send MCP initialize + tool call via stdin
```

### File structure

```
mcp-github-api/
+-- server.py          # Main FastMCP server (entry point)
+-- base/              # Shared base package (response, decorators, persistence, clients)
+-- mcp_errors.py      # Error helpers
+-- input_validator.py # Input validation
+-- rate_limiter.py    # Rate limiting
+-- requirements.txt
+-- .gitignore
+-- README.md
+-- CLAUDE.md
```

---

## Key Rules

1. Do NOT edit `base/` directly — it is a copy from `mcp-base` repo
2. To update shared utilities, edit in `mcp-base` and re-copy
3. Keep `server.py` as the single entry point
4. All tool handlers must use `@mcp_tool_handler` decorator for consistent error handling
5. All responses must use `success()` / `error()` / `MCPResponse` builder from `base.response`

---

**Last Updated:** 2026-03-31
