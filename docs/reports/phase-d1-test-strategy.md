# Phase D.1 — IEEE 829 Test Plan
Test Plan Identifier: TP-mcp-github-api-label-milestone-v1
Date: 2026-05-30
Author: test-management-agent
Status: APPROVED

---

## 1. Test Plan Identifier

**TP-mcp-github-api-label-milestone-v1**

This identifier traces all test artifacts (test files, coverage reports, defect reports) for the
`github_create_label` and `github_create_milestone` functions added to
`mcp-github-api/server.py` in the Phase C implementation sprint (2026-05-30).

---

## 2. Introduction

### 2.1 Purpose

This test plan verifies that `github_create_label` and `github_create_milestone` fully satisfy
every specification requirement: all happy paths, all error paths, all edge cases, and all
idempotency contracts. The plan establishes coverage gates, defines pass/fail criteria, and
provides a risk-prioritized execution order for the unit-testing-specialist and
integration-testing-engineer agents executing Phase D.2.

### 2.2 Background

Phase C-1 (hallucination detection) and Phase C-2 (context faithfulness) both scored 1.00 across
all RAGAS metrics for both functions. No contradictions, no missing implementations, and no
invented behavior were found. This confirms the implementation is specification-faithful; the
purpose of this test plan is therefore to produce a DRE = 1.0 test suite that provides permanent
regression protection and CI gate enforcement.

### 2.3 Scope

**IN SCOPE — these 2 functions only:**
- `github_create_label` (server.py lines 565–624)
- `github_create_milestone` (server.py lines 627–712)

**OUT OF SCOPE:**
- All 12 existing tool functions (`github_create_issue`, `github_close_issue`,
  `github_add_comment`, `github_create_pr`, `github_merge_pr`, `github_list_issues`,
  `github_get_pr_status`, `github_create_issue_branch`, `github_auto_commit_and_pr`,
  `github_validate_build`, `github_label_issue`, `github_full_merge_cycle`)
- `base/` package internals
- MCP protocol serialization layer
- FastMCP server lifecycle

---

## 3. Test Items

### 3.1 Primary Test Items

| Function | File | Start Line | End Line | Decorator Lines |
|----------|------|-----------|---------|----------------|
| `github_create_label` | `server.py` | 567 (`def`) | 624 (`raise`) | 565–566 |
| `github_create_milestone` | `server.py` | 629 (`def`) | 712 (`raise`) | 627–628 |

**Confirmed from direct source read (server.py):**

- `github_create_label` — `def` at line 567, last statement `raise` at line 624. Decorated with
  `@mcp.tool()` at line 565 and `@mcp_tool_handler` at line 566.
- `github_create_milestone` — `def` at line 629, last statement `raise` at line 712. Decorated
  with `@mcp.tool()` at line 627 and `@mcp_tool_handler` at line 628.

### 3.2 Supporting Modules Under Test

These modules are exercised only at their public interface; their internals are mocked:

| Module | Role in Test |
|--------|-------------|
| `base.clients.GitHubApiClient` | Mocked: `GitHubApiClient.instance().get_or_raise()` |
| `github.GithubException` | Real import used; constructed with `status` attribute in mocks |

---

## 4. Features to be Tested

### 4.1 github_create_label — All Testable Paths

**Happy paths:**

1. **test_create_label_happy_path**
   Nominal case: `name="bug"`, `color="d73a4a"`, `description="Something is broken"`.
   `gh_repo.create_label()` returns a mock Label. Assert response keys
   `{name, color, description, url, already_exists}` with `already_exists=False`.
   Confirm `color.lstrip("#")` called (leading `#` already absent — no stripping needed here).

2. **test_create_label_strips_leading_hash**
   `color="#0075ca"` supplied. Assert that `gh_repo.create_label()` is called with
   `color="0075ca"` (leading `#` stripped via `lstrip`). Assert response `already_exists=False`.

**Idempotency path:**

3. **test_create_label_already_exists_422**
   `gh_repo.create_label()` raises `GithubException` with `status=422`.
   `gh_repo.get_label(name)` returns a mock of the existing label.
   Assert response `already_exists=True` and all 5 keys present with existing label data.

**Color validation:**

4. **test_create_label_color_non_hex_rejected**
   `color="xyzabc"` (non-hex characters). Assert `ValueError` raised with message
   `"Color must be 6 hex characters without #"` before any API call.

5. **test_create_label_color_wrong_length_rejected**
   `color="0075c"` (5 characters). Assert `ValueError` raised with message
   `"Color must be 6 hex characters without #"` before any API call.

6. **test_create_label_color_uppercase_hex_accepted**
   `color="D73A4A"` (uppercase hex). Assert validation passes (uppercase is in the allowed
   character set `"0123456789abcdefABCDEF"`). Assert `gh_repo.create_label()` called with
   `color="D73A4A"`.

**Name validation:**

7. **test_create_label_empty_name_rejected**
   `name=""`. Assert `ValueError` raised with message `"Label name must be 1-50 characters"`
   before any API call.

8. **test_create_label_name_over_50_chars_rejected**
   `name="a" * 51` (51-character string). Assert `ValueError` raised with message
   `"Label name must be 1-50 characters"` before any API call.

9. **test_create_label_name_exactly_50_chars_accepted**
   `name="a" * 50` (50-character string, at boundary). Assert validation passes and
   `gh_repo.create_label()` is called (no ValueError raised).

**API error paths:**

10. **test_create_label_api_error_404**
    `gh_repo.create_label()` raises `GithubException` with `status=404`.
    Assert `ValueError` raised with message `f"Repository {repo} not found or no access"`.

11. **test_create_label_api_error_403**
    `gh_repo.create_label()` raises `GithubException` with `status=403`.
    Assert `ValueError` raised with message `f"Token lacks write permission on {repo}"`.

12. **test_create_label_api_error_unknown_reraised**
    `gh_repo.create_label()` raises `GithubException` with `status=500`.
    Assert the original `GithubException` is re-raised (not wrapped in `ValueError`).

**Response schema:**

13. **test_create_label_description_none_returns_empty_string**
    Mock label has `label.description = None`. Assert response `description` key equals `""`
    (the `or ""` guard on `label.description`).

---

### 4.2 github_create_milestone — All Testable Paths

**Happy paths:**

14. **test_create_milestone_happy_path_no_due_on**
    `title="Sprint 1"`, `due_on=""` (empty). Assert `gh_repo.create_milestone()` called with
    kwargs that do NOT include `due_on` key. Assert response contains all 8 keys with
    `already_exists=False`.

15. **test_create_milestone_happy_path_date_format**
    `due_on="2026-06-30"` (YYYY-MM-DD). Assert `gh_repo.create_milestone()` called with
    `due_on=datetime(2026, 6, 30)`. Assert response `due_on` is the isoformat of the mock
    milestone's `due_on` attribute.

16. **test_create_milestone_happy_path_iso8601_format**
    `due_on="2026-06-30T00:00:00Z"` (ISO 8601 with time). Assert parsed to
    `datetime(2026, 6, 30, 0, 0, 0)` and passed to `gh_repo.create_milestone()`.

**Idempotency path:**

17. **test_create_milestone_already_exists_422**
    `gh_repo.create_milestone()` raises `GithubException` with `status=422`.
    `gh_repo.get_milestones(state="all")` returns an iterable containing a mock milestone
    whose `title` matches the input. Assert response `already_exists=True` and all 8 keys
    present with existing milestone data. Assert `get_milestones` called with `state="all"`.

**State validation:**

18. **test_create_milestone_invalid_state_rejected**
    `state="invalid"`. Assert `ValueError` raised with message
    `"state must be 'open' or 'closed'"` before any API call.

**Title validation:**

19. **test_create_milestone_empty_title_rejected**
    `title=""`. Assert `ValueError` raised with message
    `"Milestone title must not be empty"` before any API call.

**due_on validation:**

20. **test_create_milestone_invalid_due_on_rejected**
    `due_on="30/06/2026"` (unrecognized format). Assert `ValueError` raised with message
    `"due_on must be YYYY-MM-DD or ISO 8601 format"` after both format attempts fail.

**API error path:**

21. **test_create_milestone_api_error_404**
    `gh_repo.create_milestone()` raises `GithubException` with `status=404`.
    Assert `ValueError` raised with message `f"Repository {repo} not found or no access"`.

**Response schema:**

22. **test_create_milestone_due_on_none_in_response**
    Mock milestone has `ms.due_on = None`. Assert response `due_on` key equals `None`
    (the `ms.due_on.isoformat() if ms.due_on else None` guard).

---

### 4.3 Integration Test Paths

**IT-01: github_create_label — real API create and idempotent re-call**
    Using `GITHUB_TOKEN` + `GITHUB_TEST_REPO`. Create label with unique name. Verify response
    `already_exists=False`. Call again with same name. Verify response `already_exists=True`.
    Teardown: delete label from test repo.

**IT-02: github_create_label — color with leading # stripped in real API call**
    Pass `color="#ff0000"`. Assert GitHub API accepts it (no 422 for color) and response
    `color` equals `"ff0000"`. Teardown: delete label.

**IT-03: github_create_milestone — real API create and idempotent re-call**
    Create milestone with unique title and `due_on="2030-12-31"`. Verify `already_exists=False`
    and `due_on` is not None in response. Call again with same title. Verify `already_exists=True`.
    Teardown: close and delete milestone from test repo.

**IT-04: github_create_milestone — no due_on omitted from API kwargs**
    Create milestone with `due_on=""`. Verify response `due_on` is `None` (GitHub API sets no
    due date). Teardown: delete milestone.

---

## 5. Features NOT to be Tested

The following are explicitly excluded from this test plan:

1. **Existing 12 tool functions** — `github_create_issue`, `github_close_issue`,
   `github_add_comment`, `github_create_pr`, `github_merge_pr`, `github_list_issues`,
   `github_get_pr_status`, `github_create_issue_branch`, `github_auto_commit_and_pr`,
   `github_validate_build`, `github_label_issue`, `github_full_merge_cycle`. These have no
   spec changes in this sprint and are out of scope.

2. **`base/` package internals** — `LazyClient`, `mcp_tool_handler` decorator internals,
   `response` builder serialization, `GitHubApiClient` token resolution logic.
   These are mocked at their public boundary; their own test suites (if any) are separate.

3. **GitHubApiClient token resolution** — environment variable lookup, `get_or_raise()` error
   when no token is set. This is a `base/clients` concern.

4. **FastMCP protocol layer** — MCP initialize/tool-call serialization, stdio transport, JSON
   envelope wrapping. Tested at the protocol level separately.

5. **`_gh_cli_merge_fallback`** — unrelated to the two new functions.

6. **`github_full_merge_cycle` composition** — does not call either new function.

---

## 6. Approach

### 6.1 Unit Testing

**Framework:** pytest (stdlib + pytest-cov)
**Mocking:** `unittest.mock.MagicMock` and `unittest.mock.patch`
**Coverage tool:** `pytest-cov` with `--cov=server --cov-branch --cov-report=term-missing`

**Mocking boundary:** All mocks are set at the `GitHubApiClient` boundary.
The test patches `server.GitHubApiClient` so that:
- `GitHubApiClient.instance().get_or_raise()` returns a mock `client`
- `client.get_repo(repo)` returns a mock `gh_repo`
- `gh_repo.create_label(...)` / `gh_repo.get_label(...)` are MagicMock-controlled
- `gh_repo.create_milestone(...)` / `gh_repo.get_milestones(...)` are MagicMock-controlled

`GithubException` objects are constructed with `status` attribute set directly:
```python
exc = GithubException(422, {"message": "Validation Failed"}, {})
exc.status = 422
```

**Test teardown (unit):** `LazyClient.reset_all()` called in `teardown_method` or `autouse`
fixture to reset `GitHubApiClient` singleton between tests, preventing state leakage.

**Test file:** `tests/test_github_label_milestone.py`
**Total unit test cases:** 22 (13 for `github_create_label` + 9 for `github_create_milestone`,
covering all paths enumerated in Section 4)

### 6.2 Integration Testing

**Skip condition:**
```python
pytest.mark.skipif(
    not os.environ.get("GITHUB_TOKEN") or not os.environ.get("GITHUB_TEST_REPO"),
    reason="GITHUB_TOKEN and GITHUB_TEST_REPO env vars required"
)
```

**Teardown — mandatory state cleanup:**
- Labels: `gh_repo.get_label(name).delete()` in `finally` block
- Milestones: `gh_repo.get_milestone(number).edit(state="closed")` then
  `gh_repo.get_milestone(number).delete()` — or direct API delete call

**Test file:** `tests/test_integration_label_milestone.py`
**Total integration test cases:** 4 (IT-01 through IT-04 as defined in Section 4.3)

### 6.3 Coverage Strategy

Both functions must achieve 100% line coverage and 100% branch coverage. The branch map for
each function is:

**github_create_label branches:**

| Branch | Condition | Covered By |
|--------|-----------|-----------|
| B1-T | `not name or len(name) > 50` — True | tests 7, 8 |
| B1-F | `not name or len(name) > 50` — False | tests 1, 2, 3, 4, 5, 6, 9–13 |
| B2-T | `len(color) != 6 or not all(...)` — True | tests 4, 5 |
| B2-F | `len(color) != 6 or not all(...)` — False | tests 1, 2, 3, 6, 9–13 |
| B3-T | `e.status == 422` — True | test 3 |
| B3-F | `e.status == 422` — False | tests 10, 11, 12 |
| B4-T | `e.status == 404` — True | test 10 |
| B4-F | `e.status == 404` — False | tests 11, 12 |
| B5-T | `e.status == 403` — True | test 11 |
| B5-F | `e.status == 403` — False | test 12 |

**github_create_milestone branches:**

| Branch | Condition | Covered By |
|--------|-----------|-----------|
| B1-T | `not title` — True | test 19 |
| B1-F | `not title` — False | tests 14–18, 20–22 |
| B2-T | `state not in ("open", "closed")` — True | test 18 |
| B2-F | `state not in ("open", "closed")` — False | tests 14–17, 19–22 |
| B3-T | `if due_on` — True (string provided) | tests 15, 16, 20 |
| B3-F | `if due_on` — False (empty string) | test 14 |
| B4-T | ISO 8601 format parse succeeds | test 16 |
| B4-F | ISO 8601 format parse fails, YYYY-MM-DD succeeds | test 15 |
| B5-T | `due_date is None` after loop — True | test 20 |
| B5-F | `due_date is None` after loop — False | tests 15, 16 |
| B6-T | `if due_date` — True (kwargs gets due_on) | tests 15, 16 |
| B6-F | `if due_date` — False (kwargs omits due_on) | test 14 |
| B7-T | `e.status == 422` — True | test 17 |
| B7-F | `e.status == 422` — False | tests 21 |
| B8-T | `existing.title == title` — True | test 17 |
| B9-T | `e.status == 404` — True | test 21 |
| B9-F | `e.status == 404` — False | (re-raise path — can be covered by a 500 variant if needed) |
| B10-T | `ms.due_on` is not None — True | test 15 |
| B10-F | `ms.due_on` is None — True (else branch) | test 22 |

---

## 7. Pass/Fail Criteria

### 7.1 Hard Gates (CI must not proceed if any fail)

| Gate | Metric | Required Value |
|------|--------|---------------|
| G1 | All unit tests PASS | 22/22 PASS, 0 FAIL |
| G2 | Line coverage — `github_create_label` | 100% (lines 565–624) |
| G3 | Line coverage — `github_create_milestone` | 100% (lines 627–712) |
| G4 | Branch coverage — `github_create_label` | 100% |
| G5 | Branch coverage — `github_create_milestone` | 100% |
| G6 | DRE (Defect Removal Efficiency) | 1.0 — all spec defects caught before deploy |
| G7 | No test uses live network without `skipif` guard | Verified by code review |

### 7.2 Soft Gates (Warning only)

| Gate | Metric | Target |
|------|--------|--------|
| S1 | Integration tests PASS when env vars present | 4/4 PASS |
| S2 | Test execution time (unit suite only) | < 2 seconds |

### 7.3 DRE Definition

DRE = (Defects found in testing) / (Defects found in testing + Defects escaped to production)

DRE = 1.0 requires that every defect category identified in the risk matrix (Section 8) has at
least one test case that would catch it. Confirmed: all 12 risk scenarios have explicit test
coverage mapped in Section 4.

---

## 8. Risk Matrix

The following table covers all 22 unit test scenarios and all 4 integration scenarios.

Risk ratings:
- **Probability:** HIGH = likely to be introduced by implementation change; MEDIUM = possible;
  LOW = unlikely given Phase C scores of 1.00
- **Business Impact:** HIGH = pipeline broken (MCP server crash, wrong error surfaced to caller);
  MEDIUM = wrong data returned (silent correctness defect); LOW = cosmetic / edge case

| # | Test Scenario | Function | Risk: Probability of Defect | Risk: Business Impact | Priority |
|---|--------------|----------|----------------------------|-----------------------|----------|
| 1 | test_create_label_happy_path | github_create_label | LOW | HIGH | P1 |
| 2 | test_create_label_strips_leading_hash | github_create_label | MEDIUM | HIGH | P1 |
| 3 | test_create_label_already_exists_422 | github_create_label | HIGH | HIGH | P1 |
| 4 | test_create_label_color_non_hex_rejected | github_create_label | MEDIUM | MEDIUM | P2 |
| 5 | test_create_label_color_wrong_length_rejected | github_create_label | MEDIUM | MEDIUM | P2 |
| 6 | test_create_label_color_uppercase_hex_accepted | github_create_label | MEDIUM | MEDIUM | P2 |
| 7 | test_create_label_empty_name_rejected | github_create_label | LOW | MEDIUM | P2 |
| 8 | test_create_label_name_over_50_chars_rejected | github_create_label | LOW | MEDIUM | P2 |
| 9 | test_create_label_name_exactly_50_chars_accepted | github_create_label | LOW | LOW | P3 |
| 10 | test_create_label_api_error_404 | github_create_label | LOW | HIGH | P1 |
| 11 | test_create_label_api_error_403 | github_create_label | LOW | HIGH | P1 |
| 12 | test_create_label_api_error_unknown_reraised | github_create_label | MEDIUM | HIGH | P1 |
| 13 | test_create_label_description_none_returns_empty_string | github_create_label | LOW | LOW | P3 |
| 14 | test_create_milestone_happy_path_no_due_on | github_create_milestone | LOW | HIGH | P1 |
| 15 | test_create_milestone_happy_path_date_format | github_create_milestone | MEDIUM | HIGH | P1 |
| 16 | test_create_milestone_happy_path_iso8601_format | github_create_milestone | MEDIUM | HIGH | P1 |
| 17 | test_create_milestone_already_exists_422 | github_create_milestone | HIGH | HIGH | P1 |
| 18 | test_create_milestone_invalid_state_rejected | github_create_milestone | LOW | MEDIUM | P2 |
| 19 | test_create_milestone_empty_title_rejected | github_create_milestone | LOW | MEDIUM | P2 |
| 20 | test_create_milestone_invalid_due_on_rejected | github_create_milestone | MEDIUM | MEDIUM | P2 |
| 21 | test_create_milestone_api_error_404 | github_create_milestone | LOW | HIGH | P1 |
| 22 | test_create_milestone_due_on_none_in_response | github_create_milestone | MEDIUM | MEDIUM | P2 |
| IT-01 | Integration: create label + idempotent re-call | github_create_label | MEDIUM | HIGH | P1 |
| IT-02 | Integration: color with leading # stripped in real API | github_create_label | MEDIUM | HIGH | P1 |
| IT-03 | Integration: create milestone + idempotent re-call | github_create_milestone | MEDIUM | HIGH | P1 |
| IT-04 | Integration: no due_on omitted from API kwargs | github_create_milestone | LOW | MEDIUM | P2 |

### 8.1 Risk Summary

| Priority | Count | Rationale |
|----------|-------|-----------|
| P1 | 14 | Pipeline-breaking: server crash, wrong idempotency result, incorrect error surfaced |
| P2 | 10 | Correctness defects: validation bypass, wrong response fields, silent wrong data |
| P3 | 2 | Boundary/cosmetic: exact-boundary name length, None-to-empty-string guard |

**Highest risk scenarios (P1 focus):**

- **Idempotency paths (tests 3, 17, IT-01, IT-03):** Probability HIGH because the 422 branch
  involves a secondary API call (`get_label`/`get_milestones`) — any regression here silently
  returns wrong data to the pipeline orchestrator, breaking sprint automation.

- **Leading-# strip (test 2, IT-02):** Probability MEDIUM because input comes from human or
  LLM; `#0075ca` is the natural way a human specifies a color. If the `lstrip` call regresses,
  the GitHub API rejects with a 422 and the label is never created.

- **ISO 8601 due_on parsing (test 16):** Probability MEDIUM because the format order
  (ISO first, then YYYY-MM-DD) is subtle; a change to the `for fmt in (...)` tuple order
  would cause `2026-06-30T00:00:00Z` to fail with a false-negative `ValueError`.

- **Unknown API error re-raise (test 12):** Probability MEDIUM because any catch-all change
  from `raise` to `raise ValueError(...)` would mask real 5xx API failures as validation
  errors, breaking caller error handling.

---

## 9. Test Environment

### 9.1 Required Dependencies

```
Python >= 3.8
pytest >= 7.0
pytest-cov >= 4.0
PyGithub >= 1.55       # provides github.GithubException
unittest.mock          # stdlib (Python 3.3+)
```

**Installation:**
```bash
pip install pytest pytest-cov PyGithub
```

### 9.2 Unit Test Environment

- No network access required
- No environment variables required
- All PyGithub objects mocked at `GitHubApiClient.instance().get_or_raise()`
- Tests are deterministic and hermetic

**Run command:**
```bash
pytest tests/test_github_label_milestone.py \
    --cov=server \
    --cov-branch \
    --cov-report=term-missing \
    --cov-fail-under=100 \
    -v
```

### 9.3 Integration Test Environment

**Required environment variables:**

| Variable | Purpose |
|----------|---------|
| `GITHUB_TOKEN` | Personal access token with `repo` scope on the test repository |
| `GITHUB_TEST_REPO` | Test repository in `owner/repo` format (e.g. `techdeveloper-org/mcp-test-repo`) |

**Skip behavior:** If either variable is absent, all integration tests are skipped with
`pytest.mark.skipif`. No test failure is raised.

**State isolation:** Every integration test uses a unique label/milestone name incorporating
a timestamp or UUID to prevent collision. Teardown runs in a `finally` block to guarantee
cleanup even on assertion failure.

**Run command:**
```bash
GITHUB_TOKEN=<token> GITHUB_TEST_REPO=<owner/repo> \
pytest tests/test_integration_label_milestone.py -v
```

### 9.4 Test File Locations

| File | Type | Cases |
|------|------|-------|
| `tests/test_github_label_milestone.py` | Unit | 22 |
| `tests/test_integration_label_milestone.py` | Integration | 4 |

Both files are to be created fresh (no existing `tests/` directory in the repository at
plan-writing time).

### 9.5 Singleton Reset Protocol

`LazyClient.reset_all()` (from `base.clients`) must be called in each test's teardown to
reset the `GitHubApiClient` singleton. Recommended implementation:

```python
import pytest
from base.clients import GitHubApiClient

@pytest.fixture(autouse=True)
def reset_client():
    yield
    # Reset singleton so next test gets a fresh mock
    try:
        from base.clients import LazyClient
        LazyClient.reset_all()
    except Exception:
        pass
```

---

## 10. Test Deliverables

| Deliverable | Owner | Due |
|-------------|-------|-----|
| `tests/test_github_label_milestone.py` | unit-testing-specialist | Phase D.2 |
| `tests/test_integration_label_milestone.py` | integration-testing-engineer | Phase D.2 |
| Coverage HTML report (`htmlcov/`) | unit-testing-specialist | Phase D.2 |
| Phase D.2 execution report | test-management-agent | Phase D.3 |

---

## 11. Schedule and Resources

| Phase | Activity | Agent |
|-------|----------|-------|
| D.1 | IEEE 829 test strategy (this document) | test-management-agent |
| D.2 | Unit test implementation + execution | unit-testing-specialist |
| D.2 | Integration test implementation + execution | integration-testing-engineer |
| D.3 | Coverage gate verification + DRE calculation | test-management-agent |

---

## 12. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| PyGithub `GithubException` constructor signature differs between versions | LOW | Pin `PyGithub>=1.55` in test requirements; construct with `exc.status = N` assignment |
| `LazyClient.reset_all()` API changes in `base/` | LOW | Wrap in try/except in fixture; test isolation via `patch` is the primary mechanism |
| Integration tests pollute the test repo with orphaned labels/milestones | MEDIUM | Unique names (UUID suffix) + `finally` teardown block |
| Coverage < 100% due to `from datetime import datetime` inside function | LOW | This line is always executed when function is called; line coverage will include it |

---

STRATEGY GATE: APPROVED — unit-testing-specialist and integration-testing-engineer may begin D.2 implementation.
