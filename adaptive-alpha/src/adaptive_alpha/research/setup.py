"""Operator-only local provider vault. Keys never appear in responses or audit payloads."""

import json
import os
from pathlib import Path
from typing import Any

import httpx
from pydantic import Field, SecretStr

from adaptive_alpha.domain import Contract, new_id
from adaptive_alpha.research.literature import bounded_json


class ProviderSetup(Contract):
    api_key: SecretStr | None = None
    model: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9._:-]*$")


def load_provider(directory: Path) -> dict[str, str]:
    path = directory / "openai.json"
    if not path.is_file():
        return {}
    result = json.loads(path.read_text())
    return {"api_key": str(result.get("api_key", "")), "model": str(result.get("model", ""))}


def configure_provider(
    directory: Path, request: ProviderSetup, client: httpx.Client | None = None
) -> dict[str, Any]:
    previous = load_provider(directory)
    key = (
        request.api_key.get_secret_value().strip()
        if request.api_key
        else previous.get("api_key", "")
    )
    if not 20 <= len(key) <= 500 or any(c.isspace() for c in key):
        raise ValueError("OPENAI_KEY_REQUIRED")
    headers = {"Authorization": "Bearer " + key}
    try:
        if client:
            result = bounded_json(
                client, "GET", "https://api.openai.com/v1/models", headers=headers
            )
        else:
            with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as connection:
                result = bounded_json(
                    connection, "GET", "https://api.openai.com/v1/models", headers=headers
                )
    except httpx.HTTPError as exc:
        raise ValueError("OPENAI_CONNECTION_FAILED_CHECK_KEY_AND_NETWORK") from exc
    models = sorted(
        str(m["id"])
        for m in result.get("data", [])
        if isinstance(m, dict)
        and str(m.get("id", "")).startswith("gpt-")
        and not any(
            x in str(m["id"]) for x in ("image", "audio", "realtime", "transcribe", "search")
        )
    )
    model = request.model or previous.get("model", "")
    if model and model not in models:
        raise ValueError("MODEL_NOT_AVAILABLE_FOR_THIS_KEY")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = directory / (".pending-" + new_id())
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump({"api_key": key, "model": model}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, directory / "openai.json")
    finally:
        temporary.unlink(missing_ok=True)
    return {"configured": True, "model": model, "models": models, "connection_verified": True}
