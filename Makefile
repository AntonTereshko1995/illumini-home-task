PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: dev run run-v2 test

dev:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -e ".[dev]"
	$(BIN)/pre-commit install

run:
	$(BIN)/python -m v1.workers.job_matcher.handler

run-v2:
	$(BIN)/python -m v2.workers.job_matcher.handler

test:
	$(BIN)/python -m pytest -q
