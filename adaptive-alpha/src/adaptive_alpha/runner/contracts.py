"""Bounded JSON-only native tool contract, distinct from capital admission."""

from typing import Any

from pydantic import Field, model_validator

from adaptive_alpha.domain import Contract, canonical, digest

PROTOCOL = "native-tool-v1"


class ToolRequest(Contract):
    source: str = Field(min_length=10, max_length=16384)
    payload: dict[str, Any] = Field(default_factory=dict)
    seconds: int = Field(default=5, ge=1, le=30)
    output_bytes: int = Field(default=16384, ge=1024, le=65536)

    @model_validator(mode="after")
    def bounded(self) -> "ToolRequest":
        if len(canonical(self.model_dump()).encode()) > 60000:
            raise ValueError("TOOL_INPUT_TOO_LARGE")
        return self

    @property
    def fingerprint(self) -> str:
        return digest(self.model_dump(mode="json"))
