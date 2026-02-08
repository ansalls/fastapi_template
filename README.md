# FastAPI Full-Stack Template

Production-ready starter for full-stack applications with:
- FastAPI API layer
- PostgreSQL + Alembic migrations
- JWT access/refresh auth lifecycle
- OAuth login + account linking (Google, Microsoft, Apple, Facebook, GitHub)
- Redis-backed rate limiting
- Outbox + worker pattern for async delivery
- Observability hooks (metrics, OpenTelemetry, Sentry)
- Baseline frontend for browser-level validation

## Template Goal

This template is designed so teams can build any product domain with minimal edits to core infrastructure.

Core platform responsibilities are already handled:
- auth/session lifecycle
- security middleware and error contracts
- rate limiting and readiness behavior
- background job reliability pattern
- observability wiring

Product-specific work should be added in extension areas, not by rewriting the core.

## Quickstart

```bash
cp .env.example .env
make setup
alembic upgrade head
make dev
```

Open:
- API docs: `http://127.0.0.1:8000/docs`
- GUI: `http://127.0.0.1:8000/`

## Core vs Extension Model

Keep these stable unless explicitly required:
- `app/main.py`
- `app/oauth2.py`
- `app/oauth_external.py`
- `app/errors.py`
- `app/rate_limit.py`
- `app/observability.py`

Build product behavior in:
- `app/domains/<domain_name>/...`
- `tests/...` for domain behavior

Routers in `app/domains/*/router.py` are auto-discovered and mounted under `/api/v1`.

## Add a New Domain (No Core Edits)

Scaffold a new domain package:

```bash
make scaffold-domain NAME=orders
```

This creates:
- `app/domains/orders/__init__.py`
- `app/domains/orders/router.py`

Then extend that domain with schemas/services/repositories and tests.

## Full-Stack Adaptation Playbook

For any use case (SaaS, marketplace, internal tool, consumer app):
1. Define domain packages (`orders`, `billing`, `catalog`, `admin`, etc.).
2. Add domain data models + Alembic migrations.
3. Keep auth and security behavior inherited from the platform core.
4. Add frontend pages/components against `/api/v1` domain routes.
5. Add outbox topics for integrations (email, webhooks, analytics, queues).
6. Validate with quality gates before shipping.

## Developer Experience Commands

```bash
make dev             # local API with reload
make test-fast       # fast local confidence loop
make lint
make typecheck
make audit-security
make test            # full suite + 100% app coverage gate
make check           # lint + typecheck + audit + full tests
```

## Environment and Security Baseline

Important production settings:
- `ENVIRONMENT=production`
- `SECRET_KEY` (high-entropy, 32+ chars)
- `TOKEN_ISSUER`
- `TOKEN_AUDIENCE`
- `TRUSTED_HOSTS`
- `TRUST_PROXY_HEADERS`
- `SECURITY_HSTS_ENABLED=true`
- `SECURITY_HTTPS_REDIRECT=true`
- `RATE_LIMIT_FAIL_OPEN=false`

OAuth callbacks:
- Configure provider credentials via `OAUTH_*`.
- Use `OAUTH_PUBLIC_BASE_URL` behind reverse proxies.
- Set `OAUTH_FRONTEND_CALLBACK_URL` to an allowed frontend origin/path.

## AI Tooling Readiness

This repo includes AI-oriented guardrails:
- `AGENTS.md`: repo-level AI implementation rules
- `AI_CHANGE_CHECKLIST.md`: required validation and documentation gate

Recommended AI workflow:
1. Keep core platform files stable.
2. Implement feature scope in `app/domains/<domain>`.
3. Add behavior-first tests.
4. Run `make check`.
5. Update docs when behavior changes.

## Docker and Deployment

Dev stack:

```bash
docker compose -f docker-compose-dev.yml up --build
```

Prod baseline:

```bash
docker compose -f docker-compose-prod.yml up -d
```

Kubernetes examples:
- `deploy/k8s/api-deployment.yaml`
- `deploy/k8s/worker-deployment.yaml`
- `deploy/k8s/configmap.example.yaml`
- `deploy/k8s/secret.example.yaml`

## Additional Docs

- Architecture: `ARCHITECTURE.md`
- AI checklist: `AI_CHANGE_CHECKLIST.md`
- AI agent instructions: `AGENTS.md`
