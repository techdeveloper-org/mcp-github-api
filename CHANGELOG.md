# Changelog

## [UNRELEASED]

### Added
- `github_create_label`: Create repository labels with idempotent behavior for sprint planning setup
- `github_create_milestone`: Create milestones as Sprint containers for GitHub Issues sprint board

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
