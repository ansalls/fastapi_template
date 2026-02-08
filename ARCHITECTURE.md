# Architecture Overview

## Purpose

This repository is a FastAPI-first full-stack starter template. It provides:
- REST API endpoints for users, auth, posts, and votes
- PostgreSQL persistence through SQLAlchemy
- Alembic migrations
- JWT authentication and authorization dependencies
- A minimal browser UI served from the API process

## Runtime Components

- API app: `app/main.py`
- Routers:
  - `app/routers/auth.py`
  - `app/routers/user.py`
  - `app/routers/post.py`
  - `app/routers/vote.py`
- Auth/JWT service: `app/oauth2.py`
- Settings: `app/config.py`
- Database/session: `app/database.py`
- ORM models: `app/models.py`
- API schemas: `app/schemas.py`
- Frontend assets: `app/frontend/`

## Data Flow

1. Request enters FastAPI app.
2. Router-level dependency injection resolves DB session and user context.
3. Request payloads are validated by Pydantic schemas.
4. ORM operations are executed with SQLAlchemy.
5. Response models enforce API output contracts.

## Persistence and Migrations

- SQLAlchemy models define runtime ORM mappings.
- Alembic migration scripts are the source of truth for schema evolution.
- Tests create/drop schema per test session in the dedicated test database.

## Testing Strategy

- `unit` marker: isolated behavior tests, no required external service.
- `integration` marker: API-level tests against a real PostgreSQL test DB.
- `e2e` marker: live Uvicorn process and full request flow validation.

Coverage goal is enforced at 100% for `app/` (including branch coverage).
