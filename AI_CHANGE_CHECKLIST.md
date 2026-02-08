# AI Change Checklist

Use this checklist before merging AI-assisted changes.

- Scope:
  - Confirm the change request and success criteria are explicit.
  - Confirm whether change is backward-compatible or breaking.

- Data and Contracts:
  - Update `app/schemas.py` if API contracts changed.
  - Add/update Alembic migrations if schema changed.
  - Validate auth/ownership behavior for protected endpoints.

- Code Quality:
  - `make lint`
  - `make typecheck`
  - `make test`

- Tests:
  - Add unit tests for pure logic branches.
  - Add/adjust integration tests for API + DB behavior.
  - Add/adjust e2e test for user-visible workflow changes.

- Docs:
  - Update `README.md` for setup/runtime changes.
  - Update `ARCHITECTURE.md` for structural changes.
  - Record significant tradeoffs in the PR or relevant architecture docs.

- Ops:
  - Verify container and CI config still match runtime assumptions.
  - Ensure secrets/config behavior remains environment-driven.
