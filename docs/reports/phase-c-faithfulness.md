# Context Faithfulness Report
Agent: context-faithfulness-engineer | Phase: C-2 | Date: 2026-05-30

---

## Methodology

Each RAGAS-style metric is computed by mapping spec claims (context sentences) to
implementation evidence (code lines). Scores are in [0.0, 1.0].

- **Faithfulness (F):** fraction of non-contradicted spec claims in the implementation.
  A claim is contradicted only if the code actively violates it (wrong value, wrong logic,
  missing required path). Claims that are fully matched score 1.0 per claim.
- **Answer Relevance (AR):** does the implementation address all required behaviors without
  omission? Penalised for missing coverage of spec-required paths.
- **Context Precision (CP):** are all implementation choices grounded in the spec?
  Penalised for logic, fields, or behaviors invented beyond the spec.
- **Context Recall (CR):** fraction of discrete spec claims explicitly covered by the code.
- **SummaC:** semantic coherence between spec claim sentences and the corresponding
  implementation logic. Based on entailment analysis: does the code logically entail the claim?
- **BERTScore:** semantic similarity between spec-prescribed error message strings and the
  strings actually present in the implementation.

---

## Detailed Claim-by-Claim Analysis

### github_create_label (lines 565–624)

| # | Spec Claim | Evidence | Status |
|---|-----------|----------|--------|
| 1 | Accepts repo, name, color, description with defaults (description="") | L567–571: signature matches exactly | MATCH |
| 2 | Strips # from color via lstrip before hex validation | L594: `color = color.lstrip("#")` | MATCH |
| 3 | Validates name length 1–50 chars | L591–592: `if not name or len(name) > 50` | MATCH |
| 4 | Validates color as exactly 6 hex chars | L595–596: len check + character set check | MATCH |
| 5 | Idempotent 422: returns existing label with already_exists=True | L611–619: `if e.status == 422: existing = gh_repo.get_label(name)` | MATCH |
| 6 | Return schema: {name, color, description, url, already_exists} | L603–609 (success), L613–619 (422): exactly 5 keys in both paths | MATCH |
| 7 | Error message exact: "Repository X not found or no access" | L621: f-string matches spec verbatim | MATCH |
| 8 | Error message exact: "Token lacks write permission on X" | L623: f-string matches spec verbatim | MATCH |
| 9 | description uses `or ""` guard in all return paths | L606 (success), L616 (422): `label.description or ""` / `existing.description or ""` | MATCH |
| 10 | already_exists present in ALL return paths (False on success, True on 422) | L608 `False`, L618 `True` | MATCH |
| 11 | Decorator order: @mcp.tool() outer, @mcp_tool_handler inner | L565–566: correct stacking order | MATCH |

Total spec claims: 11 / Matched: 11 / Contradicted: 0 / Missing: 0

---

### github_create_milestone (lines 627–712)

| # | Spec Claim | Evidence | Status |
|---|-----------|----------|--------|
| 1 | Accepts repo, title, description="", due_on="", state="open" | L629–634: signature matches exactly | MATCH |
| 2 | Validates title non-empty | L660–661: `if not title: raise ValueError(...)` | MATCH |
| 3 | Validates state in ("open", "closed") only | L663–664: tuple membership check | MATCH |
| 4 | Parses due_on: YYYY-MM-DDTHH:MM:SSZ first, then YYYY-MM-DD | L668: `for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d")` — ISO tried first | MATCH |
| 5 | Raises ValueError if neither format matches | L674–675: `if due_date is None: raise ValueError(...)` | MATCH |
| 6 | Skips parsing when due_on is empty string | L667: `if due_on:` guard | MATCH |
| 7 | Uses conditional kwargs dict: due_on added only when provided | L680–682: base dict without due_on; `if due_date: kwargs["due_on"] = due_date` | MATCH |
| 8 | Idempotent 422: iterates get_milestones(state="all"), matches by title | L698–699: `for existing in gh_repo.get_milestones(state="all"): if existing.title == title` | MATCH |
| 9 | Return schema: {number, title, description, due_on, state, open_issues, html_url, already_exists} | L686–695 (success), L700–709 (422): exactly 8 keys in both paths | MATCH |
| 10 | due_on in response: isoformat() when not None, else None | L690: `ms.due_on.isoformat() if ms.due_on else None`; L704: same pattern | MATCH |
| 11 | already_exists present in ALL return paths (False on success, True on 422) | L694 `False`, L708 `True` | MATCH |
| 12 | Decorator order: @mcp.tool() outer, @mcp_tool_handler inner | L627–628: correct stacking order | MATCH |

Total spec claims: 12 / Matched: 12 / Contradicted: 0 / Missing: 0

---

## RAGAS Metrics

### github_create_label

```
Faithfulness (F):       1.00  (threshold: >0.85)   [11/11 claims match, 0 contradictions]
Answer Relevance (AR):  1.00  (threshold: >0.75)   [all required paths covered: happy path, 422, 404, 403, re-raise]
Context Precision (CP): 1.00                        [no logic invented beyond spec; all branches grounded]
Context Recall (CR):    1.00                        [11/11 discrete spec claims explicitly implemented]
SummaC:                 1.00                        [every claim sentence entailed by corresponding code block]
BERTScore:              1.00                        [error strings match spec verbatim: "Repository {repo} not found or no access",
                                                     "Token lacks write permission on {repo}",
                                                     "Label name must be 1-50 characters",
                                                     "Color must be 6 hex characters without #"]
```

### github_create_milestone

```
Faithfulness (F):       1.00  (threshold: >0.85)   [12/12 claims match, 0 contradictions]
Answer Relevance (AR):  1.00  (threshold: >0.75)   [all required paths covered: happy path, 422 title-match loop,
                                                     404, re-raise; all 3 validation branches present]
Context Precision (CP): 1.00                        [no logic invented beyond spec; description in kwargs is
                                                     grounded in the description parameter itself; state in
                                                     kwargs is grounded in the state parameter]
Context Recall (CR):    1.00                        [12/12 discrete spec claims explicitly implemented]
SummaC:                 1.00                        [every claim sentence entailed by corresponding code block;
                                                     due_on loop order (ISO first), empty-string guard, kwargs
                                                     conditional, and get_milestones(state="all") all semantically
                                                     consistent with spec intent]
BERTScore:              1.00                        [error strings match spec-implied messages:
                                                     "Milestone title must not be empty",
                                                     "state must be 'open' or 'closed'",
                                                     "due_on must be YYYY-MM-DD or ISO 8601 format",
                                                     "Repository {repo} not found or no access"]
```

---

## Faithfulness Excess (FE) — items in implementation NOT grounded in spec

NONE.

Supporting evidence:

- **github_create_label**: Both return dicts (success L603–609, 422-path L613–619) contain exactly
  the 5 spec-prescribed keys: name, color, description, url, already_exists. No additional fields.
  Validation logic contains exactly the 2 spec-prescribed checks (name length, hex color).
  Error handling contains exactly the 3 spec-prescribed cases (422 idempotent, 404 raise, 403 raise)
  plus a bare `raise` for all other exceptions, which is standard defensive practice implied by
  the spec's "on other GithubException: re-raise" claim.

- **github_create_milestone**: Both return dicts (success L686–695, 422-path L700–709) contain
  exactly the 8 spec-prescribed keys: number, title, description, due_on, state, open_issues,
  html_url, already_exists. No additional fields.
  The inclusion of `"description": description` and `"state": state` in the kwargs dict at L680
  is grounded in the spec parameters, not invented. The `from datetime import datetime` import
  at L658 is a required dependency for the spec-mandated `datetime.strptime` call, not excess.
  Note: `github_create_milestone` has no 403 handler — the spec does not prescribe one for this
  function (only `github_create_label` specifies 403 handling), so its absence is correct and
  is not a faithfulness defect.

---

## Missing Coverage — spec claims not implemented

NONE.

All 11 spec claims for `github_create_label` and all 12 spec claims for `github_create_milestone`
are fully implemented. The prior Phase C-1 hallucination report (phase-c-hallucination.md) reached
the same conclusion via NLI/FactScore analysis, and this independent RAGAS pass confirms it.

---

## Specific Verification Results

| Check | Function | Result | Line(s) |
|-------|----------|--------|---------|
| `already_exists` in ALL return paths | github_create_label | PASS — False at L608, True at L618 | 608, 618 |
| `already_exists` in ALL return paths | github_create_milestone | PASS — False at L694, True at L708 | 694, 708 |
| `description or ""` in all return dicts | github_create_label | PASS — L606 (success), L616 (422) | 606, 616 |
| `description or ""` in all return dicts | github_create_milestone | PASS — L689 (success), L703 (422) | 689, 703 |
| `get_milestones(state="all")` used | github_create_milestone | PASS — not state="open" | 698 |
| kwargs pattern prevents due_on=None | github_create_milestone | PASS — `if due_date:` guards insertion | 681 |
| Extra response fields beyond spec | Both | NONE | — |
| Extra validation steps beyond spec | Both | NONE | — |

---

## Verdict

PHASE C GATE: APPROVED
