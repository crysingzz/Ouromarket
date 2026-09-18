#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv run python scripts/bootstrap.py
mkdir -p .state
export ALPHA_EVALUATOR_URL=http://127.0.0.1:8001
uv run python -c "from adaptive_alpha.config import Settings; from adaptive_alpha.store import Store; Store(Settings().database_url).initialize()"
uv run uvicorn adaptive_alpha.evaluation.service:create_evaluator --factory --host 127.0.0.1 --port 8001 --no-access-log &
evaluator_pid=$!
uv run python -m adaptive_alpha.research.worker &
worker_pid=$!
trap 'kill "$evaluator_pid" "$worker_pid" 2>/dev/null || true' EXIT INT TERM
uv run uvicorn adaptive_alpha.api.app:create_app --factory --host 127.0.0.1 --port 8787 --no-access-log
