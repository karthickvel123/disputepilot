.PHONY: test lint run eval

test:
	uv run pytest

lint:
	uv run ruff check .

run:
	uv run uvicorn disputepilot.web:app --reload

eval:
	uv run python -m disputepilot.evals.runner
