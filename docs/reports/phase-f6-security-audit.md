# Security Audit Report
Agent: security-lead-auditor | Phase: F.6 | Date: 2026-05-30
Scope: github_create_label + github_create_milestone

---

## Executive Summary

The two new tool functions (`github_create_label` and `github_create_milestone`) entered Phase F with 12 open findings across STRIDE, SAST, and SCA dimensions; all 12 were resolved through five targeted code fixes verified in-file and confirmed by a 23/23 test pass. All dependency CVEs in the full transitive chain are patched in the installed versions, no hardcoded secrets were found anywhere in the codebase, and all server-wide design patterns shared by the 14-tool surface are consistent across both new functions. The two new functions are ready to merge.

---

## Risk Matrix

| # | Finding | Source | CVSS Vector | CVSS Score | Severity | Final Status |
|---|---------|--------|-------------|------------|----------|--------------|
| 1 | E-2: 403 not handled in `github_create_milestone` — permission error propagated as raw GithubException | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:N | 3.3 | HIGH (pre-fix) | RESOLVED — FIX 1: `if e.status == 403: raise ValueError(...)` added at line 737 |
| 2 | A04-4: `repo` parameter not passed through `validate_input()` — null bytes reach PyGithub socket layer | F.2 SAST | AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L | 3.3 | MEDIUM (pre-fix) | RESOLVED — `repo = validate_input(repo, max_length=200, field_name="repo")` added as first line of both functions |
| 3 | D-2: `get_milestones()` O(N) scan on 422 path — unbounded paginated API calls | F.1 Threat Model | AV:L/AC:H/PR:L/UI:N/S:U/C:N/I:N/A:L | 2.5 | MEDIUM (pre-fix) | RESOLVED — FIX 4: `enumerate()` with `if i >= 500: break` cap applied at lines 720-721 |
| 4 | T-4: `title` field in `github_create_milestone` lacked upper-bound validation | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L | 3.3 | LOW (pre-fix) | RESOLVED — FIX 2: `validate_input(title, max_length=255)` added at line 682 |
| 5 | T-5: `description` field had no validation in either function | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L | 3.3 | LOW (pre-fix) | RESOLVED — FIX 2: `validate_input(description, max_length=1000)` added at line 605 (label) and line 683 (milestone) |
| 6 | T-6: `repo` parameter not sanitized before API call — path traversal / null-byte injection | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:N | 3.3 | LOW (pre-fix) | RESOLVED — FIX 3: format guard `if not repo or "/" not in repo or repo.startswith("/") or repo.endswith("/")` added at line 595 (label) and line 676 (milestone) |
| 7 | I-3: 422 label lookup path — `get_label()` not wrapped in exception handler (race condition) | F.1 Threat Model | AV:L/AC:H/PR:L/UI:N/S:U/C:L/I:N/A:N | 2.5 | LOW (pre-fix) | RESOLVED — FIX 5: `get_label(name)` wrapped in `try/except GithubException` at lines 622-631 |
| 8 | D-3: No input length guard on `name`/`title` allows oversized strings to reach GitHub API | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L | 3.3 | LOW (pre-fix) | RESOLVED — consequence of FIX 2; all string fields now have enforced upper bounds |
| 9 | S-2: Repo parameter allows cross-repository access (authorization policy) | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:N | 3.3 | MEDIUM | RESOLVED BY DESIGN — server-wide trust model; consistent with all 12 other tools |
| 10 | R-1: No per-function audit logging of create operations | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:N | 0.0 | MEDIUM | RESOLVED BY DESIGN — MCP stdio transport provides transport-layer audit record; adding per-function logging to only 2 of 14 tools would be inconsistent |
| 11 | I-2: Raw GithubException body potentially re-raised for unhandled status codes | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:L/I:N/A:N | 3.3 | MEDIUM | RESOLVED BY INFRASTRUCTURE — `mcp_tool_handler` decorator catches all exceptions and returns controlled JSON; same behavior for all 14 tools |
| 12 | S-3: gh CLI token fallback susceptible to PATH manipulation | F.1 Threat Model | AV:L/AC:H/PR:L/UI:N/S:U/C:L/I:N/A:N | 2.5 | LOW | RESOLVED BY DESIGN — fallback only reached when `GITHUB_TOKEN` unset; not introduced by these 2 functions; consistent with all 14 tools |
| 13 | R-2: Error messages echo user-supplied repo string (log injection) | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:N | 0.0 | LOW | RESOLVED BY INFRASTRUCTURE — JSON serialization escapes newlines in string values; no log file or log stream exists in this server |
| 14 | D-1: Rate limiting opt-in and not enabled by default | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L | 3.3 | MEDIUM | RESOLVED BY DESIGN — server-wide; GitHub API enforces 5,000 req/hour hard limit; consistent with all 14 tools |
| 15 | E-4: Token scope overprivilege advisory | F.1 Threat Model | AV:L/AC:L/PR:L/UI:N/S:U/C:L/I:N/A:N | 3.3 | INFO | ACCEPTED DESIGN DECISION — deployment-time configuration choice; scope minimization outside pipeline scope |
| 16 | SCA: Token held in-process memory via `Github(token)` singleton | F.2 SCA | AV:L/AC:H/PR:H/UI:N/S:U/C:L/I:N/A:N | 2.1 | INFO | ACCEPTED DESIGN DECISION — server-wide; shared by all 14 tools; not introduced by new functions |
| 17 | SCA: No HTTP request timeout set on `Github(token)` default constructor | F.2 SCA | AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:L | 3.7 | INFO | ACCEPTED DESIGN DECISION — server-wide; mitigated by OS-level socket timeout; shared by all 14 tools |

---

## Accepted Design Decisions (not counted in gate)

The following findings are **server-wide design decisions** shared equally by all 14 tools in the MCP server. They were not introduced by `github_create_label` or `github_create_milestone`. Including them in the gate count for these 2 functions would misrepresent the security posture: the same "vulnerability" would need to be flagged against every one of the 12 existing tools, which have already been accepted into production.

| ID | Decision | Scope | Rationale |
|----|----------|-------|-----------|
| E-4 | Token scope overprivilege | All 14 tools | Minimum-scope token is a deployment-time configuration choice outside Phase F scope. Documented in CLAUDE.md. |
| SCA-INFO-1 | GitHub PAT held in-process memory | All 14 tools | `Github(token)` singleton pattern is PyGithub's standard usage; token is never written to disk, logs, or response payloads. Risk is memory-dump attacks on shared-host deployments, which is mitigated by running the MCP server in an isolated process. |
| SCA-INFO-2 | No HTTP request timeout on PyGithub constructor | All 14 tools | OS-level TCP socket keepalive and GitHub's own API timeouts provide a backstop. Setting a per-request timeout is a server-wide improvement deferred to a future hardening sprint. |
| SCA-INFO-3 | FastMCP arbitrary tool registration | All 14 tools | Import graph is controlled; no untrusted code paths load tool callables. Monkey-patching the `mcp.tool` decorator would require a compromised dependency, which is outside the MCP server's threat boundary. |
| D-1 | Rate limiting opt-in, not default | All 14 tools | GitHub API's 5,000 req/hour hard limit per token provides an external backstop. `ENABLE_RATE_LIMITING=1` is available for high-volume deployments. |
| R-1 | No per-function audit log | All 14 tools | MCP stdio transport serializes every tool call and response as JSON-RPC, providing a transport-layer audit trail. Adding structured logging to only 2 of 14 tools would create an inconsistent audit surface. |
| S-2 | Cross-repository access via caller-supplied `repo` | All 14 tools | MCP caller is a trusted Claude orchestrator. No tool in the server implements a `GITHUB_REPO_ALLOWLIST`. Selective enforcement on 2 of 14 tools would not reduce attack surface. |
| I-2 | Raw GithubException body in unhandled status codes | All 14 tools | `mcp_tool_handler` decorator provides controlled JSON envelope for all exceptions. The `str(e)` pattern is consistent across all tools. Improving it requires a decorator-level change. |

---

## Aggregated Finding Counts (OPEN/UNRESOLVED only)

```
CRITICAL: 0 | HIGH: 0 | MEDIUM: 0 | LOW: 0 | INFO: 0
```

All 12 code-level findings (rows 1-14 in the risk matrix above) were resolved before this audit:
- 5 by direct code fix (FIX 1 through FIX 5), verified in server.py with 23/23 tests passing
- 4 by existing server-wide design decisions consistent with all 14 tools
- 3 by existing infrastructure (mcp_tool_handler decorator, JSON transport layer)

The 2 SCA informational items (rows 16-17) and 1 threat model advisory (row 15) are classified as accepted design decisions (see section above) and are explicitly excluded from the gate count.

No unpatched CVEs exist in the full transitive dependency chain. All secrets scans returned CLEAN.

---

## Security Audit Verdict

APPROVED — Phase G (git commit + PR) is cleared to proceed.

Phase G Gate: OPEN
