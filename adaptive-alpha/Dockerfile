FROM ghcr.io/astral-sh/uv:0.11.15@sha256:e590846f4776907b254ac0f44b5b380347af5d90d668138ca7938d1b0c2f98d3 AS uv
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,id=adaptive-alpha-uv-cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS runtime
RUN groupadd --gid 10001 alpha && useradd --uid 10001 --gid alpha --no-create-home alpha \
    && mkdir -p /app /state /provider-vault /artifacts && chown alpha:alpha /state /provider-vault /artifacts
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ENV ALPHA_CONTAINER_BASE_IMAGE="python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"
ARG BUILD_COMMIT=development
ARG BUILD_LOCK_HASH=development
ENV ALPHA_BUILD_COMMIT=$BUILD_COMMIT ALPHA_BUILD_LOCK_HASH=$BUILD_LOCK_HASH
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "adaptive_alpha.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
