.PHONY: check lint typecheck test

check: lint typecheck test

lint:
	python -m ruff check .
	python -m ruff format --check .

typecheck:
	python -m mypy

test:
	python -m pytest -q
