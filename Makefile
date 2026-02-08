PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PIP := $(BIN)/pip
PYTEST := $(BIN)/pytest
RUFF := $(BIN)/ruff
MYPY := $(BIN)/mypy
PRE_COMMIT := $(BIN)/pre-commit

DATABASE_HOSTNAME ?= localhost
DATABASE_PORT ?= 5432
DATABASE_PASSWORD ?= password123
DATABASE_NAME ?= fastapi
DATABASE_USERNAME ?= postgres
SECRET_KEY ?= test-secret-key
ALGORITHM ?= HS256
ACCESS_TOKEN_EXPIRE_MINUTES ?= 30

TEST_ENV = DATABASE_HOSTNAME=$(DATABASE_HOSTNAME) DATABASE_PORT=$(DATABASE_PORT) DATABASE_PASSWORD=$(DATABASE_PASSWORD) DATABASE_NAME=$(DATABASE_NAME) DATABASE_USERNAME=$(DATABASE_USERNAME) SECRET_KEY=$(SECRET_KEY) ALGORITHM=$(ALGORITHM) ACCESS_TOKEN_EXPIRE_MINUTES=$(ACCESS_TOKEN_EXPIRE_MINUTES)

.PHONY: setup lint format typecheck test test-unit test-integration test-e2e ci precommit-install precommit-run

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

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

test:
	$(TEST_ENV) $(PYTEST) -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=100

ci: lint typecheck test

precommit-install:
	$(PRE_COMMIT) install

precommit-run:
	$(PRE_COMMIT) run --all-files
