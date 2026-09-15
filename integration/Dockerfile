FROM ghcr.io/astral-sh/uv:0.12.1@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded AS uv
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/ouroboros
COPY ouroboros-runtime/pyproject.toml ouroboros-runtime/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY ouroboros-runtime/ ./
RUN uv sync --locked --no-dev --no-editable \
    && git init -b runtime-snapshot \
    && git add . \
    && git -c user.name=Ouromarket -c user.email=runtime@localhost commit -qm 'Pinned upstream source snapshot' \
    && groupadd --gid 10002 engineer \
    && useradd --uid 10002 --gid engineer --no-create-home engineer \
    && mkdir -p /state /workspaces /home/engineer \
    && chown engineer:engineer /state /workspaces /home/engineer \
    && ln -s /state /home/engineer/Ouroboros \
    && git config --system --add safe.directory /opt/ouroboros
COPY integration/runtime_gateway.py integration/launch.py integration/upstream.json /integration/
ENV PATH="/opt/ouroboros/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HOME=/home/engineer OUROBOROS_APP_ROOT=/state \
    OUROBOROS_REPO_DIR=/opt/ouroboros OUROBOROS_DATA_DIR=/state/data \
    OUROBOROS_SETTINGS_PATH=/state/data/settings.json \
    OUROBOROS_SERVER_HOST=0.0.0.0 OUROBOROS_SERVER_PORT=8765
LABEL org.ouromarket.upstream.commit="b9bcc2da71e0bd51b6f5f906890b3b80265defed"
USER 10002:10002
EXPOSE 8765
ENTRYPOINT ["python", "/integration/launch.py"]
