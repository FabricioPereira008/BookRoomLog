---
name: ensure-test-coverage
description: >-
  Verifies and enforces automated test coverage whenever a new feature, endpoint,
  service, or UI component is created or modified. Use this skill after developing or
  refactoring any code to ensure that tests are written and all pytest tests pass.
---

# Ensure Test Coverage Workflow (BookRoomLog)

This skill provides a systematic protocol to guarantee that any new feature, route, business logic, or frontend component is covered by automated tests before work is marked complete.

## Workflow Sequence

Whenever you implement a new feature or change existing behavior:

### Step 1: Identify Changed Components & Needs
Determine the scope of the new feature:
- **Backend Service (`backend/app/services/`)**: Needs tests in the matching `backend/tests/test_*.py` (e.g. `test_books_api.py`, `test_rereads.py`, `test_stats.py`, `test_lookup.py`) validating inputs, edge cases, error conditions, and database persistence.
- **Backend Endpoint (`backend/app/api/v1/endpoints/`)**: Needs API integration tests (fixture `client` in `backend/tests/conftest.py`) validating HTTP status codes (e.g., `200`, `201`, `404`, `422`), request payload validation, and responses.
- **Frontend API Client (`frontend_desktop/api_client/client.py`)**: Needs tests in `frontend_desktop/tests/test_api_client.py` mocking the HTTP calls with `responses`.
- **Frontend UI / Components (`frontend_desktop/views/`)**: Needs tests in `frontend_desktop/tests/` (e.g. `test_main_window.py`, `test_book_dialog.py`, `test_other_views.py`). Use the `backend` fixture (real API on an in-memory DB behind `api_client`) and `sync_async` (runs `run_async` synchronously).

---

### Step 2: Check Existing Coverage
Run the automated coverage check helper:

```bash
./venv/bin/python .claude/skills/ensure-test-coverage/scripts/check_coverage.py
```
Or directly via pytest:
```bash
./venv/bin/pytest --cov=backend/app --cov=frontend_desktop/api_client --cov-report=term-missing
```

Review the `Missing` column in the report to spot unexercised code paths.

---

### Step 3: Implement Missing Tests
If the new feature lacks test coverage, immediately write tests covering:
1. **Happy Path**: Standard successful execution with expected outputs.
2. **Edge Cases / Error Cases**: Invalid IDs, empty collections, malformed inputs, or missing fields.
3. **State Integrity**: Verifying that database models or UI widgets are updated cleanly in-place without side effects.

---

### Step 4: Verification & Gatekeeping
Re-run the entire test suite:

```bash
./venv/bin/pytest -v
```

Ensure:
- ✅ 100% of tests pass.
- ✅ Execution is fast (< 2 seconds total).
- ✅ Pre-commit hook (`.git/hooks/pre-commit`) will not be blocked.
