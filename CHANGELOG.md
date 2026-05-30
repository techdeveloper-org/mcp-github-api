# Changelog

## [UNRELEASED]

## [1.1.0] - 2026-05-30

### Added
- `github_create_label` — Create repository labels with idempotent behavior; returns existing label with `already_exists: true` on 422, enabling safe repeated pipeline calls
- `github_create_milestone` — Create sprint milestones with optional due date (YYYY-MM-DD or ISO 8601); idempotent 422 path scans up to 500 milestones by title
- Full input validation via `validate_input()` on all string parameters in both new tools (null-byte stripping, whitespace trimming, length enforcement)
- Repo format guard (`owner/repo`) on both new tools — rejects missing slash, leading slash, trailing slash
- 29-test unit suite for `github_create_label` and `github_create_milestone` (`tests/test_github_label_milestone.py`)
- Integration test suite with live API round-trip and teardown (`tests/test_integration_label_milestone.py`)

### Fixed
- `github_create_milestone`: `validate_input(title)` now runs **before** the empty check — whitespace-only titles (e.g. `"   "`) are correctly rejected instead of reaching the GitHub API
- `github_create_label`: `validate_input(name)` now strips null bytes from `name` before the length check and API call
- Silent 500-milestone scan cap replaced with `ValueError` — callers now receive an actionable error message when the idempotency scan is truncated

### Changed
- `from datetime import datetime` moved from `github_create_milestone` function body to module-level imports

## [1.0.0] - 2026-03-31

### Added
- Initial FastMCP server with 12 GitHub operation tools
- PyGithub primary client with gh CLI fallback for merge operations
- `github_create_issue`, `github_close_issue`, `github_add_comment`
- `github_create_pr`, `github_merge_pr`, `github_list_issues`, `github_get_pr_status`
- `github_create_issue_branch`, `github_auto_commit_and_pr`, `github_validate_build`
- `github_label_issue`, `github_full_merge_cycle`
- Shared base package (response builder, decorators, lazy clients)
- Input validation, rate limiting infrastructure
