# FastAPI Template

Production-oriented FastAPI starter with:
- PostgreSQL persistence and Alembic migrations
- JWT auth with access + rotating refresh tokens
- OAuth login for Google, Microsoft, Apple, Facebook, and GitHub
- Refresh-token revocation tracking
- RFC 7807 Problem Details error responses
- API versioning via explicit path (`/api/v1`)
- Redis-backed rate limiting
- Outbox model + ARQ worker with scheduled dispatch/retry hardening
- Observability hooks (Prometheus metrics, OpenTelemetry, Sentry)
- Security hardening middleware (trusted hosts, security headers, CSP, no-store auth responses)
- Minimal built-in browser GUI at `/`

## Prerequisites

- Python 3.14+ recommended
- PostgreSQL 15+ recommended
- Redis 7+ recommended

## Dependency Management

This template is configured for `uv`-based workflows.

```bash
make setup
```

`make setup` uses `uv sync --group dev` when `uv` is installed and falls back to `pip` + `requirements-dev.txt` otherwise.

## Local Setup

1. Copy environment variables:

```bash
cp .env.example .env
```

2. Update `.env` values (DB, Redis, secrets, optional observability settings).
Recommended production variables:
- `ENVIRONMENT=production`
- `SECRET_KEY`
- `TOKEN_ISSUER`
- `TOKEN_AUDIENCE`
- `REDIS_URL`
- `SENTRY_DSN`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `RATE_LIMIT_FAIL_OPEN` (typically `false`)
- `TRUST_PROXY_HEADERS`
- `TRUSTED_HOSTS`
- `SECURITY_HSTS_ENABLED` (typically `true`)
- `SECURITY_HTTPS_REDIRECT` (typically `true`)
- `OUTBOX_RETRY_MAX_ATTEMPTS`
- `OUTBOX_RETRY_BACKOFF_SECONDS`
- OAuth provider credentials (`OAUTH_*_CLIENT_ID`, `OAUTH_*_CLIENT_SECRET`)
- `OAUTH_PUBLIC_BASE_URL` when running behind a reverse proxy
3. Create databases:
- App DB: `fastapi` (or your configured name)
- Test DB: `<DATABASE_NAME>_test`
4. Run migrations:

```bash
alembic upgrade head
```

5. Start the API:

```bash
uvicorn app.main:app --reload
```

## API Versioning

- Versioned routes: `/api/v1/...`
- Unversioned `/api/...` aliases are intentionally not exposed.
- Responses include `X-API-Version`.
- If defaulted, responses include `X-API-Version-Defaulted: true`.

## Auth Lifecycle

- `POST /api/v1/login` returns:
  - `access_token`
  - `refresh_token`
  - `token_type`
- Auth responses include `Cache-Control: no-store` and `Pragma: no-cache`.
- JWTs include `iss` and `aud` claims and are validated on decode.
- `POST /api/v1/auth/refresh` rotates refresh tokens and returns a new token pair.
- `POST /api/v1/auth/logout` revokes a refresh token.
- OAuth endpoints:
  - `GET /api/v1/auth/oauth/providers`
  - `GET /api/v1/auth/oauth/{provider}/start`
  - `POST /api/v1/auth/oauth/{provider}/link/start` (authenticated account linking)
  - `GET|POST /api/v1/auth/oauth/{provider}/callback`

## Runtime Endpoints

- GUI: `http://127.0.0.1:8000/`
- Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Liveness: `GET /health`
- Readiness: `GET /ready`
- Metrics: `GET /metrics`

## Developer Workflow

```bash
make lint
make typecheck
make audit-security
make test
```

Install hooks:

```bash
make precommit-install
```

## Tests

```bash
make test
```

Tests include unit, integration, security, contract, property, and e2e lanes, with enforced 100% line+branch coverage for `app/`.

If your local test DB container is published on a non-default port, set it explicitly:

```bash
DATABASE_PORT=55432 make test
```

## Docker / Deployment Baseline

Dev stack (API + worker + Postgres + Redis):

```bash
docker compose -f docker-compose-dev.yml up --build
```

Prod compose baseline:

```bash
docker compose -f docker-compose-prod.yml up -d
```

Kubernetes baseline manifests are in:
- `deploy/k8s/api-deployment.yaml`
- `deploy/k8s/api-service.yaml`
- `deploy/k8s/worker-deployment.yaml`
- `deploy/k8s/redis-deployment.yaml`
- `deploy/k8s/configmap.example.yaml`
- `deploy/k8s/secret.example.yaml`

## Notes

- Schema evolution is migration-driven (`alembic`), not import side effects.
- Architectural notes: `ARCHITECTURE.md`
- AI change checklist: `AI_CHANGE_CHECKLIST.md`
