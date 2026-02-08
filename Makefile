PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PIP := $(BIN)/pip
PYTEST := $(BIN)/pytest
RUFF := $(BIN)/ruff
MYPY := $(BIN)/mypy
PRE_COMMIT := $(BIN)/pre-commit
PIP_AUDIT := $(BIN)/pip-audit
BANDIT := $(BIN)/bandit
UV ?= uv
APP_MODULE ?= app.main:app
APP_HOST ?= 0.0.0.0
APP_PORT ?= 8000

DATABASE_HOSTNAME ?= localhost
DATABASE_PORT ?= 5432
DATABASE_PASSWORD ?= password123
DATABASE_NAME ?= fastapi
DATABASE_USERNAME ?= postgres
SECRET_KEY ?= test-secret-key
ALGORITHM ?= HS256
ACCESS_TOKEN_EXPIRE_MINUTES ?= 30

TEST_ENV = DATABASE_HOSTNAME=$(DATABASE_HOSTNAME) DATABASE_PORT=$(DATABASE_PORT) DATABASE_PASSWORD=$(DATABASE_PASSWORD) DATABASE_NAME=$(DATABASE_NAME) DATABASE_USERNAME=$(DATABASE_USERNAME) SECRET_KEY=$(SECRET_KEY) ALGORITHM=$(ALGORITHM) ACCESS_TOKEN_EXPIRE_MINUTES=$(ACCESS_TOKEN_EXPIRE_MINUTES)

.PHONY: setup lock lint format typecheck test test-fast test-unit test-integration test-e2e test-security test-contract test-property audit-security dev scaffold-domain check ci precommit-install precommit-run

setup:
	@if command -v $(UV) >/dev/null 2>&1; then \
		$(UV) sync --group dev; \
	else \
		$(PYTHON) -m venv $(VENV); \
		$(PIP) install --upgrade pip; \
		$(PIP) install -r requirements-dev.txt; \
	fi

lock:
	$(UV) lock

lint:
	$(RUFF) check app tests

format:
	$(RUFF) format app tests

typecheck:
	$(MYPY) app

test-unit:
	$(TEST_ENV) $(PYTEST) -q -m unit

test-integration:
	$(TEST_ENV) $(PYTEST) -q -m integration

test-e2e:
	$(TEST_ENV) $(PYTEST) -q -m e2e

test-security:
	$(TEST_ENV) $(PYTEST) -q -m security

test-contract:
	$(TEST_ENV) $(PYTEST) -q -m contract

test-property:
	$(TEST_ENV) $(PYTEST) -q -m property

test:
	$(TEST_ENV) $(PYTEST) -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=100

test-fast:
	$(TEST_ENV) $(PYTEST) -q -m "unit or contract or security"

audit-security:
	docker run --rm -v "$(PWD):/workspace" -w /workspace python:3.14-slim \
		sh -lc "pip install --no-cache-dir pip-audit >/dev/null && pip-audit -r requirements.txt"
	$(BANDIT) -q -r app worker -s B105,B106

dev:
	$(BIN)/uvicorn $(APP_MODULE) --host $(APP_HOST) --port $(APP_PORT) --reload

scaffold-domain:
	@if [ -z "$(NAME)" ]; then \
		echo "Usage: make scaffold-domain NAME=orders"; \
		exit 1; \
	fi
	./scripts/scaffold_domain.sh "$(NAME)"

check: lint typecheck audit-security test

ci: lint typecheck test

precommit-install:
	$(PRE_COMMIT) install

precommit-run:
	$(PRE_COMMIT) run --all-files
