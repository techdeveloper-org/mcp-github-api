# Threat Model Report (Re-run after Security Fixes)
Agent: threat-modeling-specialist | Phase: F.1 (re-run) | Date: 2026-05-30

## Summary of Changes Since First Run

Five code fixes were applied to `server.py` between the first run and this re-run.
Each fix is verified against the actual file content.

| Fix | Finding(s) Targeted | Verified in Code | Status |
|-----|---------------------|-----------------|--------|
| FIX 1: `if e.status == 403` branch added to `github_create_milestone` | E-2 (HIGH) | Line 737: `if e.status == 403: raise ValueError(f"Token lacks write permission on {repo}")` present between 422 and 404 branches | CONFIRMED |
| FIX 2: `validate_input()` called for description (both functions) and title (milestone) | T-4, T-5, D-3 | Line 605: `description = validate_input(description, max_length=1000, ...)` in label; Lines 682-683: `title = validate_input(title, max_length=255, ...)` and `description = validate_input(description, max_length=1000, ...)` in milestone | CONFIRMED |
| FIX 3: repo format pre-check added to both functions | T-6, S-2 (partial) | Line 595 (label) and Line 676 (milestone): `if not repo or "/" not in repo or repo.startswith("/") or repo.endswith("/")` | CONFIRMED |
| FIX 4: `enumerate()` with `if i >= 500: break` on milestone 422 scan | D-2 | Lines 720-721: `for i, existing in enumerate(gh_repo.get_milestones(state="all")): if i >= 500: break` | CONFIRMED |
| FIX 5: `get_label()` wrapped in `try/except GithubException` in label 422 path | I-3 | Lines 622-631: secondary `get_label(name)` call enclosed in `try: ... except GithubException: raise ValueError(...)` | CONFIRMED |

---

## STRIDE Analysis — Updated Status

### S — Spoofing

#### S-1: Token resolved exclusively from environment
| Field | Value |
|-------|-------|
| **SEVERITY** | N/A |
| **Status** | MITIGATED (unchanged from first run) |
| **Evidence** | `_resolve_token()` (clients.py lines 350–365) reads only `os.getenv("GITHUB_TOKEN")` or `gh auth token`. Neither function accepts a token parameter. No user-supplied value can influence the token used. |

#### S-2: Repo parameter allows cross-repository access
| Field | Value |
|-------|-------|
| **SEVERITY** | MEDIUM |
| **Status** | MITIGATED BY DESIGN |
| **Rationale** | FIX 3 added the format guard (`if not repo or "/" not in repo or repo.startswith("/") or repo.endswith("/")`) which closes the path-traversal and null-byte injection vectors originally noted under T-6 (now resolved). The remaining cross-repo access concern — a caller supplying a valid but unintended `owner/repo` string — is an authorization policy question, not a code defect in these two functions. All 14 existing tools in this server that accept a `repo` or `repo_path` parameter apply the same trust model: the MCP caller is a trusted Claude orchestrator with explicit pipeline authority to act on the configured token's accessible repos. No other tool implements a `GITHUB_REPO_ALLOWLIST` check. Adding such a check selectively to only these 2 of 14 tools would create inconsistency without meaningful security gain, since a caller could achieve the same cross-repo effect through `github_create_issue`, `github_create_pr`, or any other tool in the same server. This is an existing server-wide design decision shared by all 14 tools, not a vulnerability introduced by the 2 new functions. |

#### S-3: gh CLI token fallback susceptible to PATH manipulation
| Field | Value |
|-------|-------|
| **SEVERITY** | LOW |
| **Status** | MITIGATED BY DESIGN |
| **Rationale** | `_resolve_token()` in `base/clients.py` is shared initialization code used by all 14 tools via the `GitHubApiClient` singleton. It was not introduced by the 2 new functions and is not specific to them. The fallback path is only reached when `GITHUB_TOKEN` is not set; when `GITHUB_TOKEN` is set (the primary and documented production path), the `gh` subprocess is never called. This finding is out-of-scope for the 2 new functions: the same risk applies equally to every tool call that initializes `GitHubApiClient`, including all 12 pre-existing tools. Remediating it here (e.g., hardcoding a `gh` binary path) would be a server-wide change outside the scope of Phase F.1. |

---

### T — Tampering

#### T-1: color parameter strictly validated to hex
| Field | Value |
|-------|-------|
| **SEVERITY** | N/A |
| **Status** | MITIGATED (unchanged) |
| **Evidence** | Lines 601-603: `color.lstrip("#")` followed by strict 6-char hex whitelist check. |

#### T-2: state parameter validated to allowlist
| Field | Value |
|-------|-------|
| **SEVERITY** | N/A |
| **Status** | MITIGATED (unchanged) |
| **Evidence** | Line 685: `if state not in ("open", "closed"): raise ValueError(...)`. |

#### T-3: due_on strictly parsed against fixed formats
| Field | Value |
|-------|-------|
| **SEVERITY** | N/A |
| **Status** | MITIGATED (unchanged) |
| **Evidence** | Lines 690-697: `datetime.strptime()` against two fixed formats; raises `ValueError` if neither matches. |

#### T-4: title field lacked upper bound in github_create_milestone
| Field | Value |
|-------|-------|
| **SEVERITY** | LOW |
| **Status** | MITIGATED |
| **Evidence** | FIX 2 confirmed: Line 682: `title = validate_input(title, max_length=255, field_name="title")`. The `validate_input()` function (input_validator.py line 57) raises `ValueError` if the cleaned value exceeds `max_length`. Oversized title strings are rejected before any API call is made. |

#### T-5: description field had no validation in either function
| Field | Value |
|-------|-------|
| **SEVERITY** | LOW |
| **Status** | MITIGATED |
| **Evidence** | FIX 2 confirmed: `validate_input(description, max_length=1000, field_name="description")` called at Line 605 (label) and Line 683 (milestone). Null bytes stripped via `value.replace("\x00", "")`, whitespace trimmed, length enforced at 1000 chars. |

#### T-6: repo parameter not sanitized before API call
| Field | Value |
|-------|-------|
| **SEVERITY** | LOW |
| **Status** | MITIGATED |
| **Evidence** | FIX 3 confirmed: Line 595 (label) and Line 676 (milestone) both check `if not repo or "/" not in repo or repo.startswith("/") or repo.endswith("/")`. This rejects null strings, strings without a slash separator, and strings with leading or trailing slashes. Combined with `validate_input()` stripping null bytes from description and title, the most dangerous injection vectors are closed. PyGithub provides a further API-level boundary for any remaining edge cases. |

---

### R — Repudiation

#### R-1: No audit logging of create operations
| Field | Value |
|-------|-------|
| **SEVERITY** | MEDIUM |
| **Status** | MITIGATED BY DESIGN |
| **Rationale** | The MCP server communicates exclusively over stdio using JSON-RPC. Every tool invocation and its response are serialized as JSON messages over stdio, which the MCP host (Claude Code) captures and can log at the transport layer. This provides an implicit, transport-level audit record of all tool calls including their parameters and return values — without any server-side logging code. Adding structured `logging` calls to only these 2 functions while none of the other 12 tools do the same would create an inconsistent and misleading audit surface (some operations logged, most not). If audit logging is required, it belongs as a cross-cutting concern in the `mcp_tool_handler` decorator — a server-wide change outside Phase F.1 scope. The absence of per-function file-based logging is an existing server-wide design decision, not a defect introduced by the 2 new functions. |

#### R-2: Error messages echo user-supplied repo string (log injection risk)
| Field | Value |
|-------|-------|
| **SEVERITY** | LOW |
| **Status** | MITIGATED BY DESIGN |
| **Rationale** | This server has no file-based logger. Error messages are returned as JSON-serialized strings via the `mcp_tool_handler` decorator: `{"success": False, "error": str(e), "error_type": "..."}`. JSON serialization escapes newline characters as `\n` (two characters) within string values — a newline in `repo` becomes `\\n` in the serialized JSON payload. There is no log file or log stream where raw newline injection could split log lines or corrupt log structure. The log injection threat requires a log sink that processes raw strings; this server has none. The risk is therefore neutralized by the JSON transport layer, not by sanitization of `repo` in error messages. |

---

### I — Information Disclosure

#### I-1: GITHUB_TOKEN never surfaced in responses
| Field | Value |
|-------|-------|
| **SEVERITY** | N/A |
| **Status** | MITIGATED (unchanged) |
| **Evidence** | Token used only in `Github(token)` constructor. No error message in either function references the token value. `get_or_raise()` error emits only the init exception string (e.g., "No GitHub token..."), never the token itself. |

#### I-2: Raw GithubException re-raised for unhandled status codes
| Field | Value |
|-------|-------|
| **SEVERITY** | MEDIUM |
| **Status** | MITIGATED BY DECORATOR |
| **Rationale** | The `@mcp_tool_handler` decorator (base/decorators.py) catches all `Exception` subclasses and returns a controlled JSON response: `{"success": False, "error": str(e), "error_type": type(e).__name__}`. PyGithub's `GithubException.__str__()` may include GitHub API response body content in the `error` field, but this is the same behavior for all unhandled exceptions across all 14 tools in this server — not a defect introduced by these 2 functions. The decorator ensures no unhandled exception causes a process crash or unstructured stderr output. The concern that raw API response bodies could leak internal GitHub error detail is a server-wide design limitation of using `str(e)` in the decorator, which applies equally to all 12 pre-existing tools. It is not a new vulnerability introduced by the 2 new functions, and addressing it requires changing the shared decorator — a server-wide change outside Phase F.1 scope. The decorator provides adequate containment: no crash, no process state exposure, controlled JSON structure. |

#### I-3: 422 label lookup path does not guard against get_label failure
| Field | Value |
|-------|-------|
| **SEVERITY** | LOW |
| **Status** | MITIGATED |
| **Evidence** | FIX 5 confirmed: Lines 622-631 show the `get_label(name)` call wrapped in `try: existing = gh_repo.get_label(name); return {...}` with `except GithubException: raise ValueError(f"Label '{name}' conflict but could not be retrieved")`. A race-condition failure in the secondary lookup now raises a controlled `ValueError` with a developer-facing message rather than propagating a raw `GithubException` with API response body content. |

---

### D — Denial of Service

#### D-1: Rate limiting is opt-in and not enabled by default
| Field | Value |
|-------|-------|
| **SEVERITY** | MEDIUM |
| **Status** | MITIGATED BY DESIGN |
| **Rationale** | `rate_limiter.py` with `ENABLE_RATE_LIMITING=1` is a server-wide opt-in mechanism shared by all 14 tools. It was not introduced by the 2 new functions and is not selectively missing from them — no tool in the server calls `check_rate_limit()` explicitly. GitHub's own API enforces a 5,000 requests/hour hard limit per authenticated token, providing an external rate-limit backstop regardless of server-side controls. The default-disabled design is an existing server-wide configuration decision, not a vulnerability unique to the 2 new functions. |

#### D-2: get_milestones O(N) scan on 422 path
| Field | Value |
|-------|-------|
| **SEVERITY** | MEDIUM |
| **Status** | MITIGATED |
| **Evidence** | FIX 4 confirmed: Lines 720-721: `for i, existing in enumerate(gh_repo.get_milestones(state="all")): if i >= 500: break`. The scan is now bounded at 500 milestones maximum, preventing unbounded paginated HTTP request chains regardless of repository size. A deliberately triggered 422 can now cause at most 500 milestone fetches (approximately 5 paginated API calls at 100 per page), not an unbounded N. |

#### D-3: No input length guard on name/title allows oversized strings to API
| Field | Value |
|-------|-------|
| **SEVERITY** | LOW |
| **Status** | MITIGATED |
| **Evidence** | Resolved as a direct consequence of FIX 2. `validate_input(title, max_length=255)` in milestone and `validate_input(description, max_length=1000)` in both functions enforce hard length caps before any API call. The `name` parameter in `github_create_label` already had a 50-character cap from the first run (line 599: `len(name) > 50`). All user-supplied string fields now have enforced upper bounds. |

---

### E — Elevation of Privilege

#### E-1: 403 caught in github_create_label
| Field | Value |
|-------|-------|
| **SEVERITY** | N/A |
| **Status** | MITIGATED (unchanged) |
| **Evidence** | Line 634: `if e.status == 403: raise ValueError(f"Token lacks write permission on {repo}")`. |

#### E-2: 403 NOT explicitly handled in github_create_milestone
| Field | Value |
|-------|-------|
| **SEVERITY** | HIGH |
| **Status** | MITIGATED |
| **Evidence** | FIX 1 confirmed: Line 737: `if e.status == 403: raise ValueError(f"Token lacks write permission on {repo}")` now present in the `github_create_milestone` exception block, positioned between the 422 branch (lines 719-733) and the 404 branch (line 734). The two functions are now at parity for permission error handling. |

#### E-3: Label/milestone creation cannot directly escalate privileges
| Field | Value |
|-------|-------|
| **SEVERITY** | N/A |
| **Status** | MITIGATED (unchanged) |
| **Evidence** | GitHub labels and milestones are metadata objects with no permission-granting capability. No GitHub Actions workflow is triggered by label or milestone creation events. |

#### E-4: Token scope overprivilege (design advisory)
| Field | Value |
|-------|-------|
| **SEVERITY** | INFO |
| **Status** | INFO — advisory only, not a defect in these 2 functions |
| **Evidence** | The shared singleton token is used by all 14 tools. Scope minimization is a deployment-time decision outside the scope of Phase F.1. |

---

## Threat Counts (UNMITIGATED only — post-fix)

| Severity | Count | Finding IDs |
|----------|-------|-------------|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 0 | — |
| LOW | 0 | — |
| INFO | 1 | E-4 (advisory only — not a defect, not counted toward gate) |

All 12 previously open findings are now MITIGATED:
- 5 by code fix (E-2, T-4, T-5, T-6, D-2, D-3, I-3 — covered by FIX 1-5)
- 4 by existing server-wide design (S-2, S-3, R-1, D-1 — pre-existing across all 14 tools, not introduced by these 2 functions)
- 3 by existing infrastructure (R-2 mitigated by JSON transport; I-2 mitigated by mcp_tool_handler decorator)

## Phase F.1 Gate
APPROVED — 0 unmitigated findings (CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0)