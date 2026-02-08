# FastAPI Template

Production-oriented FastAPI starter with:
- PostgreSQL persistence
- JWT-based user authentication
- Alembic migrations
- FastAPI route layer (users, auth, posts, votes)
- Basic built-in browser GUI at `/`

## Project Layout

```
app/
  config.py              # settings + env loading
  database.py            # SQLAlchemy engine/session
  models.py              # ORM models
  schemas.py             # Pydantic request/response models
  oauth2.py              # JWT create/verify + current user dependency
  routers/               # API route modules
  frontend/              # basic browser UI
alembic/                 # migrations
tests/                   # pytest suite
```

## Prerequisites

- Python 3.14+ recommended
- PostgreSQL 15+ recommended

## Local Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements-dev.txt
```

3. Copy environment variables:

```bash
cp .env.example .env
```

4. Update `.env` values for your database and secrets.
5. Create the database:
- App DB: `fastapi` (or your configured name)
- Test DB: `<DATABASE_NAME>_test`

6. Run migrations:

```bash
alembic upgrade head
```

7. Start the app:

```bash
uvicorn app.main:app --reload
```

## Developer Workflow

The template includes a `Makefile` for common workflows:

```bash
make lint
make typecheck
make test
```

Install pre-commit hooks:

```bash
make precommit-install
```

## What To Open

- GUI: `http://127.0.0.1:8000/`
- Swagger docs: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Running Tests

```bash
make test
```

Tests include unit, integration, and end-to-end coverage. They expect a reachable PostgreSQL instance using the configured env values and will use `<DATABASE_NAME>_test` plus an isolated temporary e2e database.

Run a specific lane:

```bash
make test-unit
make test-integration
make test-e2e
make test-security
make test-contract
make test-property
```

## Docker

Dev compose:

```bash
docker compose -f docker-compose-dev.yml up --build
```

Prod compose:

```bash
docker compose -f docker-compose-prod.yml up -d
```

## Notes

- Password hashing currently uses `passlib` + `bcrypt` with a compatibility pin.
- ORM table creation is migration-driven (`alembic`), not import side effects.
- Architectural notes: `ARCHITECTURE.md`
- Decision log: `DECISIONS.md`
- AI change checklist: `AI_CHANGE_CHECKLIST.md`
- Enhancement backlog: `ENHANCEMENT_QUEUE.md`
