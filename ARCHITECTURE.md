# Architecture Overview

## Purpose

This repository is a FastAPI-first full-stack starter template focused on:

- secure auth foundations (access + refresh lifecycle)
- production-oriented API behavior (versioning, error contracts, throttling)
- operational readiness (health/readiness, metrics, tracing, error reporting)
- extensibility for async/background workflows (outbox + worker scaffold)

## Infrastructure Communication Diagram

```mermaid
flowchart LR
  subgraph Clients["Clients"]
    Browser["Browser SPA / GUI"]
    APIClient["API Client / CLI"]
  end

  subgraph Edge["Edge Layer"]
    Ingress["Ingress / Reverse Proxy"]
  end

  subgraph App["Application Layer"]
    API["FastAPI API (Uvicorn)"]
    Worker["ARQ Worker (worker.run_worker)"]
  end

  subgraph Data["Stateful Services"]
    Postgres["PostgreSQL"]
    Redis["Redis"]
  end

  subgraph External["External Services"]
    OAuthProviders["OAuth Providers (Google, Microsoft, Apple, Facebook, GitHub)"]
    Prometheus["Prometheus Scraper"]
    OTELCollector["OTLP Collector"]
    Sentry["Sentry"]
  end

  Browser -->|"HTTPS 80/443 | / + /api/v1/*"| Ingress
  APIClient -->|"HTTPS 80/443 | /api/v1/*"| Ingress
  Ingress -->|"HTTP 8000"| API

  API -->|"SQL (psycopg/SQLAlchemy) 5432"| Postgres
  API -->|"Redis EVAL/INCR/PING 6379 (rate limiting/readiness)"| Redis

  API -->|"OAuth start redirect (302/307)"| Browser
  Browser -->|"Consent/authenticate"| OAuthProviders
  OAuthProviders -->|"Callback -> /api/v1/auth/oauth/{provider}/callback"| API
  API -->|"Token + profile exchange (HTTPS)"| OAuthProviders

  Worker -->|"SELECT/UPDATE outbox_events (SQL) 5432"| Postgres
  Worker -->|"enqueue_job + process_outbox_event (ARQ) 6379"| Redis

  Prometheus -->|"GET /metrics"| API
  API -->|"OTLP traces (optional)"| OTELCollector
  API -->|"Error events (optional)"| Sentry
```

## Detailed Communication Flows

### 1) Register, Login, and Refresh

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant API as FastAPI API
  participant Redis as Redis (Rate Limit)
  participant PG as PostgreSQL

  User->>API: POST /api/v1/users
  API->>Redis: EVAL auth_register rate-limit policy
  Redis-->>API: allow/deny + window metadata
  API->>PG: INSERT user + INSERT outbox_events(user.created) in same transaction
  PG-->>API: commit
  API-->>User: 201 Created

  User->>API: POST /api/v1/login
  API->>Redis: EVAL auth_login rate-limit policy
  Redis-->>API: allow/deny + window metadata
  API->>PG: SELECT user by email
  API->>PG: INSERT refresh_tokens session record
  PG-->>API: commit
  API-->>User: access_token + refresh_token

  User->>API: POST /api/v1/auth/refresh
  API->>Redis: EVAL auth_login rate-limit policy
  API->>PG: rotate refresh token (revoke old + insert new)
  PG-->>API: commit
  API-->>User: rotated access_token + refresh_token
```

### 2) OAuth Login and OAuth Account Linking

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant API as FastAPI API
  participant Provider as OAuth Provider
  participant PG as PostgreSQL

  User->>API: GET /api/v1/auth/oauth/{provider}/start
  API-->>User: Redirect with PKCE code_challenge + signed state

  User->>Provider: authenticate + consent
  Provider-->>API: callback with code + state
  API->>Provider: POST token endpoint (code + code_verifier)
  Provider-->>API: access_token / id_token
  API->>Provider: GET user profile/email
  Provider-->>API: subject + email + verification claims

  alt standard login/signup mode
    API->>PG: upsert users/oauth_accounts + insert refresh_tokens
    API-->>User: token pair or frontend redirect
  else link mode (existing local user)
    API->>PG: validate current user + upsert oauth_accounts link
    API-->>User: link success response or frontend redirect
  end
```

### 3) Write Path and Async Outbox Worker Flow

```mermaid
sequenceDiagram
  autonumber
  participant API as FastAPI API
  participant PG as PostgreSQL
  participant Worker as ARQ Worker
  participant Redis as Redis (ARQ Queue)

  API->>PG: Write domain row + INSERT outbox_events(status=pending) in one transaction
  PG-->>API: commit success

  Worker->>PG: SELECT pending outbox_events (batch)
  Worker->>Redis: enqueue process_outbox_event(event_id)
  Worker->>PG: UPDATE event status=queued
  PG-->>Worker: commit

  Redis-->>Worker: deliver process_outbox_event job
  Worker->>PG: load outbox event by id
  alt processing succeeds
    Worker->>PG: mark status=completed, processed_at=now
  else processing fails
    Worker->>PG: set retry or terminal failed, increment attempts
  end
```

### 4) Readiness, Metrics, Traces, and Error Signals

```mermaid
sequenceDiagram
  autonumber
  participant Probe as Orchestrator Probe
  participant API as FastAPI API
  participant PG as PostgreSQL
  participant Redis as Redis
  participant Prom as Prometheus
  participant OTEL as OTLP Collector
  participant Sentry as Sentry

  Probe->>API: GET /health
  API-->>Probe: 200 (liveness)

  Probe->>API: GET /ready
  API->>PG: SELECT 1
  opt REDIS_HEALTH_REQUIRED=true
    API->>Redis: PING
  end
  API-->>Probe: 200 or 503 with dependency checks

  Prom->>API: GET /metrics
  API-->>Prom: Prometheus exposition payload

  API-->>OTEL: trace spans (if OTEL endpoint configured)
  API-->>Sentry: error events (if SENTRY_DSN configured)
```

## Communication Matrix

| From | To | Protocol | Primary Purpose |
| --- | --- | --- | --- |
| Client | API | HTTPS | Versioned REST API calls (`/api/v1/*`) and frontend delivery |
| API | PostgreSQL | TCP 5432 (SQL via psycopg/SQLAlchemy) | Core persistence, auth sessions, OAuth links, outbox events |
| API | Redis | TCP 6379 (Redis commands + Lua) | Rate limiting counters, optional readiness check |
| API | OAuth providers | HTTPS | OAuth authorization code exchange and identity/profile fetch |
| Worker | PostgreSQL | TCP 5432 (SQL) | Outbox polling and completion/retry state updates |
| Worker | Redis | TCP 6379 (ARQ) | Job enqueue/dequeue and scheduler coordination |
| Prometheus | API | HTTP GET `/metrics` | Metrics scraping |
| API | OTLP collector | HTTP/gRPC (OTLP) | Trace export (optional) |
| API | Sentry | HTTPS | Error event export (optional) |

## Runtime Components

- API app: `app/main.py`
- Routers:
  - `app/routers/auth.py`
  - `app/routers/user.py`
  - `app/routers/post.py`
  - `app/routers/vote.py`
  - `app/domains/*/router.py` (auto-discovered domain routers)
- Auth/JWT services: `app/oauth2.py`
- OAuth provider orchestration: `app/oauth_external.py`
- Error contracts (RFC 7807): `app/errors.py`
- Rate limiting: `app/rate_limit.py` + `app/redis_client.py`
- Health/readiness checks: `app/health.py`
- Observability hooks: `app/observability.py`
- Outbox helpers: `app/outbox.py`
- ORM models: `app/models.py`
- Frontend assets: `app/frontend/`

Worker scaffold:

- ARQ worker settings + handlers: `worker/arq_worker.py`

## API Surface and Versioning

- Versioned path baseline: `/api/v1/*`
- No unversioned `/api/*` aliases are exposed.
- Response headers:
  - `X-API-Version`
  - `X-API-Version-Defaulted` when version was inferred
- Domain extension routers are mounted under the same `/api/v1/*` prefix.

## Authentication and Session Flow

1. `POST /api/v1/login` validates credentials.
2. API returns:
   - short-lived access token
   - long-lived refresh token
   - `token_type` (`bearer`)
3. Refresh token metadata is persisted in `refresh_tokens`.
4. `POST /api/v1/auth/refresh` rotates refresh tokens and revokes the previous one.
5. `POST /api/v1/auth/logout` revokes refresh token session state.
6. JWT decode enforces issuer/audience claims and token-type constraints.
7. Auth endpoints return no-store cache headers to reduce token persistence in intermediaries.
8. OAuth login is supported via:
   - `GET /api/v1/auth/oauth/providers`
   - `GET /api/v1/auth/oauth/{provider}/start`
   - `POST /api/v1/auth/oauth/{provider}/link/start` (link provider to existing account)
   - `GET|POST /api/v1/auth/oauth/{provider}/callback`

## Error Contract

- HTTP, validation, and unhandled errors are returned as RFC 7807 Problem Details (`application/problem+json`).
- Standard fields include:
  - `type`
  - `title`
  - `status`
  - `detail`
  - `instance`
  - `error_code`

## Rate Limiting

- Redis-backed fixed-window counters using Lua for atomicity.
- Key strategy:
  - authenticated requests: `user:{id}`
  - unauthenticated fallback: `ip:{client}`
- `X-Forwarded-For` is only trusted when `TRUST_PROXY_HEADERS=true`.
- Policies are route-class specific (login/register/read/write).

## Persistence and Reliability Pattern

- Alembic migrations are source of truth for schema evolution.
- New tables:
  - `refresh_tokens` for auth lifecycle state
  - `oauth_accounts` for provider-subject to local-user identity mapping
  - `outbox_events` for asynchronous event handoff
- Outbox events are created transactionally in write paths and dispatched by worker processes.
- Worker hardening includes scheduled dispatch cadence and retry/backoff controls.

## Observability and Ops

- `/health` for liveness
- `/ready` for dependency readiness (DB + optional Redis requirement)
- `/metrics` via Prometheus instrumentation
- OpenTelemetry tracing setup via OTLP endpoint setting
- Sentry initialization hook via DSN setting
- HTTP hardening middleware:
  - trusted host enforcement
  - optional HTTPS redirect
  - CSP and common browser security headers
  - no-store caching policy for auth routes

## Deployment Baseline

- Local/dev/prod Compose files include API, worker, Postgres, and Redis.
- Kubernetes baseline manifests provided under `deploy/k8s/`.

## Testing Strategy

- `unit`: isolated behavior without external dependencies
- `integration`: API-level and DB-integrated behavior
- `e2e`: live server process and full flow checks
- `security`: auth and cross-cutting security checks
- `contract`: OpenAPI/schema behavior
- `property`: property-based invariants

Coverage is enforced at 100% line + branch for all modules under `app/`.
