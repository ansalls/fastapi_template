PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PIP := $(BIN)/pip
PYTEST := $(BIN)/pytest
RUFF := $(BIN)/ruff
MYPY := $(BIN)/mypy
PRE_COMMIT := $(BIN)/pre-commit
UV ?= uv

DATABASE_HOSTNAME ?= localhost
DATABASE_PORT ?= 5432
DATABASE_PASSWORD ?= password123
DATABASE_NAME ?= fastapi
DATABASE_USERNAME ?= postgres
SECRET_KEY ?= test-secret-key
ALGORITHM ?= HS256
ACCESS_TOKEN_EXPIRE_MINUTES ?= 30

TEST_ENV = DATABASE_HOSTNAME=$(DATABASE_HOSTNAME) DATABASE_PORT=$(DATABASE_PORT) DATABASE_PASSWORD=$(DATABASE_PASSWORD) DATABASE_NAME=$(DATABASE_NAME) DATABASE_USERNAME=$(DATABASE_USERNAME) SECRET_KEY=$(SECRET_KEY) ALGORITHM=$(ALGORITHM) ACCESS_TOKEN_EXPIRE_MINUTES=$(ACCESS_TOKEN_EXPIRE_MINUTES)

.PHONY: setup lock lint format typecheck test test-unit test-integration test-e2e test-security test-contract test-property ci precommit-install precommit-run

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

ci: lint typecheck test

precommit-install:
	$(PRE_COMMIT) install

precommit-run:
	$(PRE_COMMIT) run --all-files
