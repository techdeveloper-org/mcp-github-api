# Hallucination Detection Report
Agent: hallucination-detector | Phase: C-1 | Date: 2026-05-30

---

## github_create_label
NLI Score: 1.00
FactScore: 1.00

### Findings

[INFO] Claim: "Accepts repo (owner/repo string), name (max 50 chars), color (6 hex without #), description (optional str, default '')" | Status: MATCH | Score: 1.00
  Evidence: Lines 567–571 — `def github_create_label(repo: str, name: str, color: str, description: str = "")`

[INFO] Claim: "Strips leading '#' from color before validation via color.lstrip('#')" | Status: MATCH | Score: 1.00
  Evidence: Line 594 — `color = color.lstrip("#")`

[INFO] Claim: "Validates color: exactly 6 hex characters — raise ValueError('Color must be 6 hex characters without #') if invalid" | Status: MATCH | Score: 1.00
  Evidence: Lines 595–596 — `if len(color) != 6 or not all(c in "0123456789abcdefABCDEF" for c in color): raise ValueError("Color must be 6 hex characters without #")`

[INFO] Claim: "Validates name: non-empty and max 50 chars — raise ValueError('Label name must be 1-50 characters') if violated" | Status: MATCH | Score: 1.00
  Evidence: Lines 591–592 — `if not name or len(name) > 50: raise ValueError("Label name must be 1-50 characters")`

[INFO] Claim: "Creates label via PyGithub: gh_repo.create_label(name=name, color=color, description=description)" | Status: MATCH | Score: 1.00
  Evidence: Line 602 — `label = gh_repo.create_label(name=name, color=color, description=description)`

[INFO] Claim: "Accesses repo via: GitHubApiClient.instance().get_or_raise().get_repo(repo)" | Status: MATCH | Score: 1.00
  Evidence: Lines 598–599 — `client = GitHubApiClient.instance().get_or_raise()` / `gh_repo = client.get_repo(repo)`

[INFO] Claim: "On GithubException status=422: calls gh_repo.get_label(name) and returns existing with already_exists=True" | Status: MATCH | Score: 1.00
  Evidence: Lines 611–619 — `if e.status == 422: existing = gh_repo.get_label(name)` returns dict with `already_exists: True`

[INFO] Claim: "On GithubException status=404: raises ValueError(f'Repository {repo} not found or no access')" | Status: MATCH | Score: 1.00
  Evidence: Lines 620–621 — `if e.status == 404: raise ValueError(f"Repository {repo} not found or no access")`

[INFO] Claim: "On GithubException status=403: raises ValueError(f'Token lacks write permission on {repo}')" | Status: MATCH | Score: 1.00
  Evidence: Lines 622–623 — `if e.status == 403: raise ValueError(f"Token lacks write permission on {repo}")`

[INFO] Claim: "On other GithubException: re-raises as-is" | Status: MATCH | Score: 1.00
  Evidence: Line 624 — bare `raise` after all conditional status checks

[INFO] Claim: "Response keys: name, color, description (uses 'or '''), url, already_exists" | Status: MATCH | Score: 1.00
  Evidence: Lines 603–609 (success path) and 613–619 (422 path) — both paths return exactly these 5 keys with `or ""`  guard on description

[INFO] Claim: "already_exists present in ALL return paths (both True and False)" | Status: MATCH | Score: 1.00
  Evidence: Line 608 `"already_exists": False` (success) and line 618 `"already_exists": True` (422)

[INFO] Claim: "Decorator order: @mcp.tool() outer, @mcp_tool_handler inner" | Status: MATCH | Score: 1.00
  Evidence: Line 565 `@mcp.tool()`, Line 566 `@mcp_tool_handler` — correct outer/inner order

[INFO] Claim: "No extra invented fields beyond spec schema (name, color, description, url, already_exists)" | Status: MATCH | Score: 1.00
  Evidence: Both return dicts contain exactly 5 keys matching the spec; no additions

### Verdict: PASS

---

## github_create_milestone
NLI Score: 1.00
FactScore: 1.00

### Findings

[INFO] Claim: "Accepts: repo (owner/repo), title (non-empty), description (optional, default ''), due_on (optional str, default ''), state (default 'open')" | Status: MATCH | Score: 1.00
  Evidence: Lines 629–634 — `def github_create_milestone(repo: str, title: str, description: str = "", due_on: str = "", state: str = "open")`

[INFO] Claim: "Validates title non-empty: raise ValueError('Milestone title must not be empty')" | Status: MATCH | Score: 1.00
  Evidence: Lines 660–661 — `if not title: raise ValueError("Milestone title must not be empty")`

[INFO] Claim: "Validates state in ('open', 'closed'): raise ValueError('state must be \'open\' or \'closed\'')" | Status: MATCH | Score: 1.00
  Evidence: Lines 663–664 — `if state not in ("open", "closed"): raise ValueError("state must be 'open' or 'closed'")`

[INFO] Claim: "Parses due_on: tries '%Y-%m-%dT%H:%M:%SZ' first, then '%Y-%m-%d' — raises ValueError if both fail" | Status: MATCH | Score: 1.00
  Evidence: Lines 668–675 — `for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):` loop with try/except; raises `ValueError("due_on must be YYYY-MM-DD or ISO 8601 format")` after loop if `due_date is None`

[INFO] Claim: "If due_on is empty string, skips parsing (due_date remains None)" | Status: MATCH | Score: 1.00
  Evidence: Line 667 — `if due_on:` guard prevents entering the parsing block when due_on is ""

[INFO] Claim: "Uses datetime.strptime internally (from datetime import datetime inside function)" | Status: MATCH | Score: 1.00
  Evidence: Line 658 — `from datetime import datetime` is placed inside the function body before any usage

[INFO] Claim: "Accesses repo via: GitHubApiClient.instance().get_or_raise().get_repo(repo)" | Status: MATCH | Score: 1.00
  Evidence: Lines 677–678 — `client = GitHubApiClient.instance().get_or_raise()` / `gh_repo = client.get_repo(repo)`

[INFO] Claim: "Builds kwargs dict, adds due_on key only if due_date is not None" | Status: MATCH | Score: 1.00
  Evidence: Lines 680–682 — base kwargs built without due_on; `if due_date: kwargs["due_on"] = due_date` conditional addition

[INFO] Claim: "Calls gh_repo.create_milestone(**kwargs)" | Status: MATCH | Score: 1.00
  Evidence: Line 685 — `ms = gh_repo.create_milestone(**kwargs)`

[INFO] Claim: "On GithubException status=422: iterates gh_repo.get_milestones(state='all'), finds by title match, returns with already_exists=True" | Status: MATCH | Score: 1.00
  Evidence: Lines 697–709 — `if e.status == 422: for existing in gh_repo.get_milestones(state="all"): if existing.title == title:` returns dict with `already_exists: True`

[INFO] Claim: "On GithubException status=404: raises ValueError(f'Repository {repo} not found or no access')" | Status: MATCH | Score: 1.00
  Evidence: Lines 710–711 — `if e.status == 404: raise ValueError(f"Repository {repo} not found or no access")`

[INFO] Claim: "Response keys: number, title, description (uses 'or '''), due_on (ms.due_on.isoformat() if not None else None), state, open_issues, html_url, already_exists" | Status: MATCH | Score: 1.00
  Evidence: Lines 686–695 (success path) and 700–709 (422 path) — both return exactly 8 keys; due_on uses `ms.due_on.isoformat() if ms.due_on else None`; description uses `or ""`

[INFO] Claim: "already_exists present in ALL return paths (both True and False)" | Status: MATCH | Score: 1.00
  Evidence: Line 694 `"already_exists": False` (success) and line 708 `"already_exists": True` (422)

[INFO] Claim: "get_milestones(state='all') used in milestone 422 path" | Status: MATCH | Score: 1.00
  Evidence: Line 698 — `for existing in gh_repo.get_milestones(state="all")`

[INFO] Claim: "kwargs pattern used for conditional due_on" | Status: MATCH | Score: 1.00
  Evidence: Lines 680–682 — dict-based kwargs with conditional insertion before unpacking on line 685

[INFO] Claim: "Decorator order: @mcp.tool() outer, @mcp_tool_handler inner" | Status: MATCH | Score: 1.00
  Evidence: Line 627 `@mcp.tool()`, Line 628 `@mcp_tool_handler` — correct outer/inner order

[INFO] Claim: "No extra invented fields beyond spec schema (number, title, description, due_on, state, open_issues, html_url, already_exists)" | Status: MATCH | Score: 1.00
  Evidence: Both return dicts contain exactly 8 keys matching the spec; no additions

### Verdict: PASS

---

## Summary
OVERALL NLI: 1.00
OVERALL FactScore: 1.00
PHASE C GATE: APPROVED
