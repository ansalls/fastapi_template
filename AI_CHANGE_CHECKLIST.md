# AI Change Checklist

Use this checklist for any AI-assisted change in this template.

## 1) Clarify Scope First

- Confirm user-visible outcome in one sentence.
- Confirm if the change is:
  - additive (preferred)
  - backward-compatible update
  - breaking change
- Identify which layer changes:
  - API contract
  - database schema
  - auth/security
  - background job flow
  - frontend UX

## 2) Respect Template Architecture

- Keep platform core stable unless explicitly requested:
  - auth, OAuth, error contracts, security middleware, rate limiting, observability.
- Add product features in extension paths:
  - `app/domains/<domain>/...`
- Prefer composition over rewriting shared infrastructure.

## 3) Data and Contract Safety

- Update Pydantic schemas when API payloads/responses change.
- Add Alembic migration for any schema changes.
- Validate auth and ownership behavior for protected routes.
- Preserve RFC 7807 error format.

## 4) Security and Production Guardrails

- No hardcoded secrets, keys, tokens, or environment-specific endpoints.
- Keep environment-driven configuration in `app/config.py` and `.env`.
- Preserve no-store behavior on auth responses.
- Preserve trusted-host, CSP, and rate-limit behavior unless intentionally changed.
- Run `make audit-security` after dependency changes.

## 5) Testing Requirements

- Add unit tests for new logic branches.
- Add/adjust integration tests for API + DB behavior.
- Add/adjust security tests for auth/protection rules.
- Add e2e coverage when user workflows change.
- Keep `app/` coverage at 100%.

## 6) Developer Experience Requirements

- Prefer new commands/scripts over manual multistep workflows.
- Add or update Make targets for recurring workflows.
- Keep onboarding path clear and minimal.
- If introducing a new pattern, provide a scaffold or concrete example.

## 7) Documentation and AI Readiness

- Update `README.md` for setup/run/customization impact.
- Update `ARCHITECTURE.md` for structural or flow changes.
- Update `AGENTS.md` when AI implementation guidance changes.
- Include clear migration notes for any breaking changes.

## 8) Final Validation Gate

Run all of:
- `make lint`
- `make typecheck`
- `make audit-security`
- `make test`

Do not conclude work until all pass, or explicitly report blockers.
