# Enhancement Queue

## Decision-Required Enhancements

Completed in this iteration:

- [x] API versioning strategy
  - Path versioning enabled at `/api/v1`
  - Latest-default aliases preserved for `/api/*` and legacy unversioned paths
- [x] Error response standard
  - RFC 7807 Problem Details for HTTP, validation, and unhandled errors
- [x] Auth lifecycle
  - Access + rotating refresh token flow
  - Refresh token revocation and replacement tracking
- [x] Rate limiting policy
  - Redis-backed fixed-window limits
  - User-id keying with IP fallback
- [x] Observability stack
  - Prometheus endpoint (`/metrics`)
  - OpenTelemetry tracing hook
  - Sentry hook
- [x] Background jobs and reliability
  - Outbox event model
  - ARQ worker scaffold and compose wiring
- [x] Deployment baseline
  - Expanded Compose topology (API + worker + Postgres + Redis)
  - Kubernetes baseline manifests
- [x] Dependency management
  - `uv`-first workflow via `pyproject.toml` and `make setup`
- [x] Template modularization
  - Optional feature packs behind config flags
  - Optionals enabled by default

## Baseline Enhancements (No Decision Needed)

- [x] Add task runner with standard commands (`Makefile`)
- [x] Add lint/format/type tooling baseline (`ruff`, `mypy`)
- [x] Add pre-commit configuration with quick local checks
- [x] Add explicit test taxonomy markers (`unit`, `integration`, `e2e`)
- [x] Add architecture and AI change-checklist docs
- [x] Update CI to run lint/type/test lanes and keep 100% coverage gate
