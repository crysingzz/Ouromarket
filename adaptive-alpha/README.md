# Adaptive Alpha

Python laboratory for reproducible strategy research, isolated Ouroboros engineering and independently controlled paper execution.

Python 3.12 and dependencies are managed with uv. Run `uv sync --locked`, `uv run ruff check src`, `uv run ruff format --check src` and `uv run pyrefly check` from this directory.

This initial commit establishes the quality toolchain. Application code, tests, Docker and OpenSpec follow as validated commits. Credentials, local datasets and runtime state must never be committed.
