# Enhancement Queue

## Group A: Decision-Required

These require explicit product/architecture choices before implementation.

- API versioning strategy (`/api/v1`, deprecation policy)
- Error response standard (RFC 7807 shape vs custom envelope)
- Auth lifecycle (refresh tokens, revocation, session model)
- Rate limiting policy (limits, storage backend, key strategy)
- Observability stack (OpenTelemetry exporter, metrics backend, error tracker)
- Background jobs and reliability pattern (Celery/RQ/Arq, outbox pattern)
- Deployment target baseline (ECS/K8s/Fly/Render/etc.)
- Dependency-management model (`uv` vs `pip-tools` vs Poetry)
- Template modularization plan (core + optional packs)

## Group B: No-Decision Required

These are safe baseline improvements for developer workflow and quality gates.

- [x] Add task runner with standard commands (`Makefile`)
- [x] Add lint/format/type tooling baseline (`ruff`, `mypy`)
- [x] Add pre-commit configuration with quick local checks
- [x] Add explicit test taxonomy markers (`unit`, `integration`, `e2e`)
- [x] Add architecture and AI change-checklist docs
- [x] Update CI to run lint/type/test lanes and keep 100% coverage gate
