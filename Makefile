.PHONY: test lint run eval sim

test:
	uv run pytest

lint:
	uv run ruff check .

run:
	uv run uvicorn disputepilot.web:app --reload

eval:
	uv run python -m disputepilot.evals.runner

sim:
	uv run python -m disputepilot.sim.generate --n 150 --out data/cases
	uv run python -m disputepilot.sim.generate --messy --n 100 --seed 7 --out data/cases_messy
