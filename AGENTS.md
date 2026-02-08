# AGENTS.md

This file defines repo-specific guidance for AI coding tools and copilots.

## Primary Goal

Help developers adapt this template to any full-stack product with minimal edits to core platform components.

## Core vs Extension Boundaries

Treat these as platform core and avoid changing them unless explicitly requested:
- `app/main.py` middleware and API bootstrapping
- `app/oauth2.py` auth token lifecycle
- `app/oauth_external.py` OAuth provider lifecycle
- `app/errors.py` RFC 7807 error contract
- `app/rate_limit.py`, `app/redis_client.py` runtime protection controls
- `app/observability.py` telemetry hooks

Prefer adding product-specific behavior in extension paths:
- `app/domains/<domain_name>/...`
- `app/domains/<domain_name>/router.py` with `router = APIRouter(...)`
- `tests/...` domain-focused tests

Routers under `app/domains/*/router.py` are auto-discovered and mounted under `/api/v1`.

## Required Implementation Pattern

When building new product features:
1. Add new API routes in a domain router package.
2. Add/extend domain data models and Alembic migrations if persistence changes.
3. Keep auth, rate limiting, and error document behavior consistent with core.
4. Preserve environment-driven configuration (no hardcoded secrets).
5. Add tests that validate expected behavior, not just current implementation.

## Quality Gate

Before concluding work, run:
- `make lint`
- `make typecheck`
- `make audit-security`
- `make test`

Coverage for `app/` must remain at 100%.

## Scaffolding Shortcut

For new domains, use:
- `make scaffold-domain NAME=orders`

## Documentation Requirements

When behavior or setup changes, update:
- `README.md`
- `ARCHITECTURE.md`
- `AI_CHANGE_CHECKLIST.md`
