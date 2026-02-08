# Decisions Log

This file tracks meaningful technical decisions for template evolution.

## 2026-02-08

1. Enforce 100% app coverage (line + branch) in CI.
Reason:
Template quality should be verifiable and stable for downstream projects.

2. Add three test lanes (`unit`, `integration`, `e2e`) via pytest markers.
Reason:
Clear test intent improves developer speed and CI diagnostics.

3. Keep migrations as schema authority (no model import-time `create_all`).
Reason:
Predictable schema evolution and safer production deployment workflows.

4. API versioning model:
Use path versioning (`/api/v1`) and keep unversioned routes defaulting to latest.
Reason:
Provides explicit contract stability while preserving a low-friction default path.

5. Error format standard:
Adopt RFC 7807 Problem Details responses for API errors.
Reason:
Consistent machine-readable error envelopes simplify clients and observability.

6. Auth lifecycle:
Use access + rotating refresh tokens with DB-backed refresh revocation.
Reason:
Supports secure session continuity and explicit token invalidation.

7. Rate limiting backend:
Use Redis-backed limits with user-id keying and IP fallback.
Reason:
Distributed, deterministic throttling is needed for production-like behavior.

8. Observability baseline:
Enable Prometheus metrics, OpenTelemetry tracing, and Sentry integration hooks.
Reason:
Template should be ready for operational visibility from day one.

9. Background jobs:
Use ARQ + Redis with an outbox model scaffold.
Reason:
Provides a practical reliability pattern without heavy orchestration overhead.

10. Deployment baseline:
Ship container-first artifacts with Compose + Kubernetes baseline manifests.
Reason:
Makes the template immediately deployable across common environments.

11. Dependency-management model:
Adopt `uv` as the primary dependency workflow (with pip fallback).
Reason:
Improves lock/sync speed and modern Python DX while preserving compatibility.

12. Modularization approach:
Keep optional packs enabled by default, configurable via feature flags.
Reason:
Best template onboarding experience while allowing selective hardening/trim-down.
