.PHONY: setup test lint typecheck check up down spec
setup:
	uv sync --locked
	uv run python scripts/bootstrap.py
lint:
	uv run ruff check src tests scripts ../integration
	uv run ruff format --check src tests scripts ../integration
typecheck:
	uv run pyrefly check
	uv run pyrefly check ../integration/runtime_gateway.py
	uv run mypy src ../integration/runtime_gateway.py
test:
	uv run pytest --cov=adaptive_alpha --cov-report=term-missing --cov-report=html:.state/coverage-html --cov-report=xml:.state/coverage.xml
check: lint typecheck test spec
up:
	uv run python scripts/bootstrap.py
	ALPHA_BUILD_COMMIT=$$(git rev-parse HEAD) ALPHA_BUILD_LOCK_HASH=$$(shasum -a 256 uv.lock | cut -d ' ' -f 1) docker compose up --build -d
down:
	docker compose down
spec:
	OPENSPEC_TELEMETRY=0 npm exec --yes --package=@fission-ai/openspec@1.12.0 -- openspec validate --all --strict --no-interactive
