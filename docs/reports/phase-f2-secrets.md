# Secrets Detection Report
Agent: secrets-detection-specialist | Phase: F.2-2 | Date: 2026-05-30

## Scan Scope

| File | Lines Scanned |
|------|--------------|
| server.py | 814 |
| base/clients.py | 561 |
| requirements.txt | 3 |
| .env | Not present (CLEAN) |
| .gitignore | Present — reviewed |
| README.md | Reviewed (lines 100-110) |
| .env.example | Present — reviewed |

New functions scanned: `github_create_label` (lines 566-637), `github_create_milestone` (lines 640-740).

---

## Scan Results

### 1. Hardcoded Tokens

**Scan patterns:** `ghp_`, `github_pat_`, `ghs_`, `[a-zA-Z0-9]{40}`

| # | Severity | File | Line | Pattern Matched | Value | Status |
|---|----------|------|------|-----------------|-------|--------|
| 1.1 | INFO | README.md | 106 | `"ghp_your_token_here"` | Placeholder literal in JSON config example | CLEAN — placeholder only, not a real token |
| 1.2 | INFO | docs/orchestration_prompt.md | 1237 | `"ghp_"` reference | Documentation string, no token value | CLEAN — documentation text |
| 1.3 | — | All .py files | — | No matches | Pattern not found in any Python source | CLEAN |
| 1.4 | — | All .py files | — | `[a-zA-Z0-9]{40}` | No 40-char token-shaped strings found | CLEAN |

**Verdict: No hardcoded GitHub tokens found in executable code.**

---

### 2. Hardcoded Credentials

**Scan patterns:** `password/secret/key/token/api_key = "..."`, `TOKEN = "..."`, `PASSWORD = "..."`, `SECRET = "..."`

| # | Severity | File | Line | Pattern | Status |
|---|----------|------|------|---------|--------|
| 2.1 | — | All .py files | — | No assignment of credential-named variable to string literal found | CLEAN |
| 2.2 | — | server.py | — | `GITHUB_TOKEN` only referenced via `os.getenv("GITHUB_TOKEN")` in base/clients.py | CLEAN |
| 2.3 | INFO | .env.example | 2 | `GITHUB_TOKEN=your_value_here` | Placeholder — not a real credential | CLEAN |

**Verdict: No hardcoded credentials found anywhere in the codebase.**

---

### 3. Token in Error Messages (New Functions)

**Scan scope:** `github_create_label` (server.py lines 566-637), `github_create_milestone` (server.py lines 640-740)

| # | Severity | File | Line | Pattern | Content | Status |
|---|----------|------|------|---------|---------|--------|
| 3.1 | INFO | server.py | 636 | f-string with "Token" | `raise ValueError(f"Token lacks write permission on {repo}")` | CLEAN — uses word "Token" as human text; interpolates only `{repo}` (caller-supplied repo name, not a credential) |
| 3.2 | INFO | server.py | 739 | f-string with "Token" | `raise ValueError(f"Token lacks write permission on {repo}")` | CLEAN — same pattern in `github_create_milestone`; no credential value exposed |
| 3.3 | — | server.py | all | No f-string containing the actual token variable or its value | — | CLEAN |
| 3.4 | — | base/clients.py | 334-335 | RuntimeError error message | `"No GitHub token. Set GITHUB_TOKEN env var or login with: gh auth login"` | CLEAN — no token value in message; instructs user to set env var |
| 3.5 | INFO | base/clients.py | 98 | `self._error = str(e)` in LazyClient | Error stored internally; only surfaced in `health_check()` output. The exception messages from `GitHubApiClient._initialize()` never include a token value (they are `RuntimeError("No GitHub token...")` or `RuntimeError("PyGithub not installed...")`). | CLEAN |

**Verdict: Error messages in new functions use word "Token" only as a human-readable noun; no token value is interpolated or echoed back.**

---

### 4. Token in Return Dicts (New Functions)

**Scan scope:** All `return {...}` statements in `github_create_label` and `github_create_milestone`

**`github_create_label` return shapes (lines 613-619, 624-630):**
```
{ name, color, description, url, already_exists }
```

**`github_create_milestone` return shapes (lines 710-719, 726-735):**
```
{ number, title, description, due_on, state, open_issues, html_url, already_exists }
```

| # | Severity | File | Lines | Finding | Status |
|---|----------|------|-------|---------|--------|
| 4.1 | — | server.py | 613-619 | `github_create_label` success return: no token-related key present | CLEAN |
| 4.2 | — | server.py | 624-630 | `github_create_label` idempotent return: no token-related key present | CLEAN |
| 4.3 | — | server.py | 710-719 | `github_create_milestone` success return: no token-related key present | CLEAN |
| 4.4 | — | server.py | 726-735 | `github_create_milestone` idempotent return: no token-related key present | CLEAN |

**Verdict: Return dicts contain only label/milestone API fields. No credential or token key/value pair in any return path.**

---

### 5. .env File Status

| Item | Result |
|------|--------|
| `.env` present at project root | No — file does not exist |
| `.env.example` present | Yes — contains only safe placeholder values (`your_value_here`) |
| Real token value in any env file | None found |

**Verdict: No `.env` file committed. `.env.example` present with non-sensitive placeholder values only.**

---

### 6. .gitignore Coverage

`.gitignore` contents reviewed (lines 1-20):

| Pattern | Coverage |
|---------|----------|
| `.env` | Explicitly listed on line 5 — COVERED |
| `.env.*` | Listed on line 6 (covers `.env.local`, `.env.production`, etc.) — COVERED |
| `!.env.example` | Negation exempts `.env.example` from the ignore rule — CORRECT (example file intentionally tracked) |

**Verdict: `.gitignore` correctly covers `.env` and all variant filenames. Accidental commit of a real `.env` file is blocked at the git level.**

---

### 7. Dependency Credential Risk

`requirements.txt` contents:
```
mcp>=1.0.0
fastmcp>=0.1.0
PyGithub
```

| Package | Known Credential-Harvesting Risk | Notes |
|---------|----------------------------------|-------|
| `mcp>=1.0.0` | None known | Official Anthropic MCP SDK |
| `fastmcp>=0.1.0` | None known | FastMCP wrapper over official SDK |
| `PyGithub` | None known | Well-established GitHub API library (>10M downloads); uses passed token for API auth only, does not exfiltrate |

**No packages in `requirements.txt` have known credential-harvesting, typosquatting, or malicious exfiltration behavior.**

Note: `base/clients.py` also imports `qdrant_client` and `sentence_transformers` conditionally (only for `QdrantManager` and `EmbeddingManager` which are not used in this server's tools). These packages carry no credential-harvesting risk.

---

## Additional Observations

### Token Resolution Pattern (base/clients.py lines 341-365)

The `GitHubApiClient._resolve_token()` method uses a secure two-source pattern:
1. `os.getenv("GITHUB_TOKEN")` — reads from environment, never from disk
2. `gh auth token` subprocess — reads from gh CLI secure keyring storage

The token is passed directly to `Github(token)` constructor and is never logged, printed, returned to callers, or stored in any attribute of the singleton beyond the opaque `Github` object itself.

### `get_or_raise()` Safety (base/clients.py line 118-121)

The error message raised by `get_or_raise()` is `"{ClassName} not available: {self._error}"`. The stored `_error` for `GitHubApiClient` will be either "PyGithub not installed..." or "No GitHub token..." — neither of which includes the token value itself.

---

## Finding Counts

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 0 |
| INFO | 5 (all CLEAN — placeholder in README, documentation mentions, safe error wording) |

---

## Secrets Gate
APPROVED (CRITICAL=0, HIGH=0, MEDIUM=0, LOW=0)
