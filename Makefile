.PHONY: test lint run run-sim eval sim smoke

test:
	uv run pytest

lint:
	uv run ruff check .

run:
	uv run uvicorn disputepilot.web:app --reload

run-sim:
	DATA_MODE=sim uv run uvicorn disputepilot.web:app --reload

smoke:
	uv run python scripts/smoke_razorpay.py

eval:
	uv run python -m disputepilot.evals.runner

sim:
	uv run python -m disputepilot.sim.generate --n 150 --out data/cases
	uv run python -m disputepilot.sim.generate --messy --n 100 --seed 7 --out data/cases_messy

build-frontend:
	cd frontend && npm run build

dev-frontend:
	cd frontend && npm run dev

