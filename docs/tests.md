# Tests layout

Canonical test locations:
- backend/tests: unit and service-level tests for the API/backend

Tests outside these folders are not collected by default.

## How to run

- Unit tests only:
  scripts/test.ps1 -scope unit

- Integration tests only:
  scripts/test.ps1 -scope integration

- All tests:
  scripts/test.ps1 -scope all

Pytest also works from the repo root with the new pytest.ini.

## Environment guards

- Tests expect the repo `.venv`. Set `DISABLE_ENV_GUARD=1` to bypass (not recommended).
- Heavy caption providers are skipped unless `CAPTION_TEST_ENABLE_HEAVY=1` or `CAPTION_EXTERNAL_DIR` is set.

## Development helpers

- Windows helpers are under `scripts/` (for example, `scripts/test.ps1` and `scripts/test_health.bat`).
