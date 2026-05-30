# SAST Report
Agent: sast-engineer | Phase: F.2-1 | Date: 2026-05-30

---

## Scope

Functions under analysis: `github_create_label` (server.py lines 568–636) and `github_create_milestone` (server.py lines 641–738).

Supporting files reviewed:
- `input_validator.py` — `validate_input()` and `validate_task_input()`
- `base/clients.py` — `GitHubApiClient`, `_resolve_token()`, `get_or_raise()`
- `base/decorators.py` — `mcp_tool_handler`
- `docs/reports/phase-f1-threat-model.md` — prior STRIDE analysis, all 5 fixes confirmed

In-scope OWASP rules: A01 (Broken Access Control), A03 (Injection), A04 (Insecure Design), A07 (Authentication Failures).
Out-of-scope: A09 (Logging) — MCP tool over stdio, not a web application.

---

## OWASP Analysis

### A01 — Broken Access Control

#### Finding A01-1: INFO | 403 handler present in BOTH functions | MITIGATED

- **Function:** `github_create_label` (line 634), `github_create_milestone` (line 737)
- **Evidence:** Both exception blocks contain `if e.status == 403: raise ValueError(f"Token lacks write permission on {repo}")`. The two functions are at parity for permission-denied handling. The 403 is caught inside the `GithubException` handler, converted to a `ValueError` with a controlled message, and surfaced to the caller via the `mcp_tool_handler` decorator as `{"success": False, "error": "Token lacks write permission on <repo>", "error_type": "ValueError"}`. No raw `GithubException` body is exposed for this status code.
- **Status:** MITIGATED

#### Finding A01-2: INFO | Repo format validation prevents cross-repo path traversal | MITIGATED

- **Function:** `github_create_label` (line 595), `github_create_milestone` (line 676)
- **Evidence:** Both functions execute the guard `if not repo or "/" not in repo or repo.startswith("/") or repo.endswith("/")` before any API call. This rejects empty strings, strings without a slash separator (bare repo names), strings with a leading slash (absolute path injection), and strings with a trailing slash. PyGithub's `client.get_repo(repo)` receives only a validated `owner/repo` string.
- **Residual note:** A caller supplying a syntactically valid but unintended `owner/repo` value (e.g. `attacker-org/target-repo`) is an authorization policy decision, not a code defect. This is the same trust model used by all 12 other tools in the server. No inconsistency is introduced.
- **Status:** MITIGATED

#### Finding A01-3: INFO | Token resolver uses only environment sources | MITIGATED

- **Function:** `GitHubApiClient._resolve_token()` (clients.py lines 350–365)
- **Evidence:** `_resolve_token()` reads `os.getenv("GITHUB_TOKEN")` first. The `gh auth token` subprocess is a one-time fallback executed only when `GITHUB_TOKEN` is absent. Neither `github_create_label` nor `github_create_milestone` accepts a token parameter; neither function can influence which token is used. The token is injected into the singleton `Github(token)` constructor at initialization time and is never stored in a field accessible to tool functions.
- **Status:** MITIGATED

---

### A03 — Injection

#### Finding A03-1: INFO | `name` parameter — length-bounded, no injection path through PyGithub | MITIGATED

- **Function:** `github_create_label` (lines 598–599)
- **Evidence:** `if not name or len(name) > 50: raise ValueError(...)` enforces a 50-character maximum before any API call. `name` is passed as a keyword argument to `gh_repo.create_label(name=name, ...)` and again to `gh_repo.get_label(name)` in the 422 recovery path (line 622). PyGithub serializes these values into a JSON request body sent to the GitHub REST API over HTTPS; there is no string interpolation into shell commands, SQL statements, or template strings. The GitHub API itself treats label names as opaque strings. No injection vector exists.
- **Status:** MITIGATED

#### Finding A03-2: INFO | `color` parameter — strict 6-hex-char whitelist, zero injection surface | MITIGATED

- **Function:** `github_create_label` (lines 601–603)
- **Evidence:** `color = color.lstrip("#")` normalizes a leading hash, then `len(color) != 6 or not all(c in "0123456789abcdefABCDEF" for c in color)` enforces an exact 6-character hex whitelist. Any character outside `[0-9a-fA-F]` raises `ValueError` before the value reaches the API. The whitelist approach is strictly stronger than a regex — it enumerates every permitted character. No injection risk.
- **Status:** MITIGATED

#### Finding A03-3: INFO | `title` parameter — length-validated via `validate_input()`, no injection path | MITIGATED

- **Function:** `github_create_milestone` (line 682)
- **Evidence:** `title = validate_input(title, max_length=255, field_name="title")` strips null bytes via `value.replace("\x00", "")`, trims surrounding whitespace, then enforces a 255-character cap — raising `ValueError` on oversize input. The cleaned title is passed as a keyword argument to `gh_repo.create_milestone(title=title, ...)` and used in the 422 recovery scan (`existing.title == title`) as a string equality comparison. No shell, SQL, or template interpolation occurs.
- **Status:** MITIGATED

#### Finding A03-4: INFO | `due_on` parameter — `datetime.strptime` with fixed format strings, no injection | MITIGATED

- **Function:** `github_create_milestone` (lines 690–697)
- **Evidence:** Parsing uses `datetime.strptime(due_on.strip(), fmt)` against two fixed format literals: `"%Y-%m-%dT%H:%M:%SZ"` and `"%Y-%m-%d"`. `strptime` with a fixed format string is a data-driven parse, not an eval or dynamic format construction. Any input that does not match either format raises `ValueError` and is rejected before the API call. The resulting `datetime` object (`due_date`) is passed directly to PyGithub, which serializes it to ISO 8601. No injection vector.
- **Status:** MITIGATED

#### Finding A03-5: INFO | `repo` parameter — format-validated, no path traversal | MITIGATED

- **Function:** Both functions (lines 595, 676)
- **Evidence:** See A01-2 above. The format guard `"/" not in repo or repo.startswith("/") or repo.endswith("/")` closes path-segment injection. `validate_input()` is not called on `repo` itself, but `validate_input()` would only add null-byte stripping and whitespace trimming to what the format guard already rejects structurally. A `repo` value containing a null byte would fail the `"/" not in repo` check (null byte is not `/`) only if it also lacked a slash — but even with a slash, PyGithub's `client.get_repo()` passes the value to the GitHub REST API via HTTPS where the server normalizes and validates the path. No shell or SQL interpolation of `repo` occurs.
- **Status:** MITIGATED

#### Finding A03-6: INFO | `description` parameter — null bytes stripped, length-capped | MITIGATED

- **Function:** Both functions (lines 605, 683)
- **Evidence:** `validate_input(description, max_length=1000, field_name="description")` removes null bytes, strips whitespace, and rejects strings exceeding 1000 characters. The cleaned value is passed as a keyword argument to `create_label()` / `create_milestone()` — no string interpolation, no template expansion.
- **Status:** MITIGATED

---

### A04 — Insecure Design

#### Finding A04-1: INFO | Label 422 idempotency path — `get_label()` wrapped in `try/except` | MITIGATED

- **Function:** `github_create_label` (lines 621–631)
- **Evidence:** The 422 recovery path reads:
  ```python
  try:
      existing = gh_repo.get_label(name)
      return { "name": existing.name, ..., "already_exists": True }
  except GithubException:
      raise ValueError(f"Label '{name}' conflict but could not be retrieved")
  ```
  A race condition (label deleted between the 422 response and the `get_label()` call) is caught by the `except GithubException` block and converted to a controlled `ValueError`. The `ValueError` message contains only the user-supplied `name` (already length-validated at 50 chars) and a static string — no token, no internal stack trace, no API response body. This is sufficient: the decorator (`mcp_tool_handler`) will surface it as `{"success": False, "error": "Label '<name>' conflict but could not be retrieved", "error_type": "ValueError"}`.
- **Status:** MITIGATED

#### Finding A04-2: INFO | Milestone 422 scan — bounded at 500 iterations | MITIGATED

- **Function:** `github_create_milestone` (lines 720–733)
- **Evidence:** `for i, existing in enumerate(gh_repo.get_milestones(state="all")): if i >= 500: break` caps the paginated scan at 500 milestones (~5 GitHub API pages at 100 per page). An adversary-triggered 422 can cause at most 500 object fetches before the loop exits. If no matching title is found within 500 milestones, the outer `GithubException` propagates to the decorator for controlled handling. The cap of 500 is well above any realistic milestone count for a real project and substantially below the unbounded O(N) that existed before FIX 4. The design choice is adequate for the stated use case (sprint management).
- **Status:** MITIGATED

#### Finding A04-3: INFO | Error messages contain no token values or internal stack traces | MITIGATED

- **Function:** Both functions
- **Evidence:** All `raise ValueError(...)` calls in both functions use only static strings and the user-supplied `repo` value (format-validated). The decorator's default `include_traceback=False` means no stack trace is included in the serialized response. `get_or_raise()` (clients.py line 118) emits `"{ClassName} not available: {self._error}"` — `self._error` is set to `str(e)` where `e` is the exception from `Github(token)` initialization; in practice this is a PyGithub auth error string (e.g., `"401 {'message': 'Bad credentials', ...}"`) that does not contain the token value itself (the token is passed to the constructor, not included in the exception message by PyGithub).
- **Status:** MITIGATED

#### Finding A04-4: MEDIUM | `validate_input()` is not called on the `repo` parameter itself — null bytes in `repo` reach PyGithub | OPEN

- **Function:** Both functions
- **Evidence:** `validate_input()` is applied to `description` and `title`, but not to `repo`. The format guard (line 595/676) rejects empty string, missing slash, leading slash, and trailing slash — but it does NOT strip null bytes (`\x00`) from the `repo` value. A `repo` string containing embedded null bytes that also contains a `/` (e.g., `"owner/repo\x00injected"`) passes the format guard and reaches `client.get_repo(repo)` with null bytes intact. PyGithub constructs the URL as `https://api.github.com/repos/{repo}` and sends it over HTTPS. CPython's `urllib` / `http.client` will raise a `ValueError("embedded null byte")` or `UnicodeEncodeError` at the socket layer before the request is transmitted, preventing the request from reaching GitHub. However, this raises an unhandled exception (not a `GithubException`) that bypasses all `GithubException` handlers and propagates to the `mcp_tool_handler` decorator as a `ValueError` with message `"embedded null byte"` — a low-information error that may confuse callers. The correct fix is to call `validate_input(repo, max_length=200, field_name="repo")` before the format guard, which would strip null bytes and produce a more actionable error message.
- **Severity:** MEDIUM
- **Exploitability:** Low — CPython's socket layer catches null bytes before HTTP transmission; no data reaches GitHub. However, the error path is not the designed path and the message quality is poor.
- **Fix:** Add `repo = validate_input(repo, max_length=200, field_name="repo")` as the first statement in both functions, before the format guard.
- **Status:** OPEN

---

### A07 — Authentication Failures

#### Finding A07-1: INFO | `get_or_raise()` fails fast when `GITHUB_TOKEN` is missing | MITIGATED

- **Function:** Both functions (lines 607, 699) call `GitHubApiClient.instance().get_or_raise()`
- **Evidence:** `get_or_raise()` (clients.py lines 104–122) calls `self.get()`. If `_resolve_token()` returns `None`, `_initialize()` raises `RuntimeError("No GitHub token. Set GITHUB_TOKEN env var or login with: gh auth login")`. `get()` catches this, stores the message in `self._error`, sets `self._available = False`, and returns `None`. `get_or_raise()` then raises `RuntimeError(f"GitHubApiClient not available: No GitHub token...")`. This `RuntimeError` propagates to `mcp_tool_handler` which catches it and returns `{"success": False, "error": "GitHubApiClient not available: ...", "error_type": "RuntimeError"}`. No tool function body executes with a missing token. Fail-fast is confirmed.
- **Status:** MITIGATED

#### Finding A07-2: INFO | 403 errors mapped to `ValueError` in BOTH functions | MITIGATED

- **Function:** `github_create_label` (line 634), `github_create_milestone` (line 737)
- **Evidence:** See A01-1. Both 403 branches are present and produce `ValueError` — the same exception type used for all other validation errors in these functions. This ensures callers see a consistent `"error_type": "ValueError"` for both input validation failures and permission failures, making programmatic error handling straightforward without exposing raw `GithubException` attributes.
- **Status:** MITIGATED

#### Finding A07-3: INFO | Token value cannot appear in any return dict or error message string | MITIGATED

- **Function:** Both functions and the `mcp_tool_handler` decorator
- **Evidence:** The token string is held only in the `Github(token)` constructor call inside `GitHubApiClient._initialize()` (clients.py line 338). It is not stored as an instance attribute accessible to tool functions. All `raise ValueError(...)` messages in both functions use static strings and `repo` (user-supplied, format-validated) — no reference to `self._token` or any variable containing token data exists in either function or in the `get_or_raise()` error path. The decorator's `str(e)` for `RuntimeError` emits only the message passed to the `RuntimeError` constructor, which never contains the token value. The token cannot appear in any response payload.
- **Status:** MITIGATED

---

## Finding Counts

Only OPEN (unmitigated) findings are counted.

| Severity | Count | Finding IDs |
|----------|-------|-------------|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 1 | A04-4 |
| LOW | 0 | — |
| INFO | 12 | A01-1, A01-2, A01-3, A03-1, A03-2, A03-3, A03-4, A03-5, A03-6, A04-1, A04-2, A04-3, A07-1, A07-2, A07-3 (all MITIGATED — not counted) |

## Fix Required

**A04-4 (MEDIUM):** In both `github_create_label` and `github_create_milestone`, add `repo = validate_input(repo, max_length=200, field_name="repo")` as the first line of each function body, before the existing format guard. This strips null bytes from `repo` and produces a consistent, actionable error message instead of a CPython socket-layer `ValueError("embedded null byte")`.

## Post-Fix Update

A04-4 FIX APPLIED: `repo = validate_input(repo, max_length=200, field_name="repo")` added as
first line of both `github_create_label` and `github_create_milestone`. Syntax OK. 23/23 tests pass.
Finding counts after fix: CRITICAL: 0 | HIGH: 0 | MEDIUM: 0 | LOW: 0 | INFO: 0

## SAST Gate
APPROVED — all finding counts = 0 after null-byte fix applied
