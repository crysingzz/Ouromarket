"""Passage-bound research claims and deterministic economic-mechanism identity."""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from adaptive_alpha.domain import Contract, digest

Short = Annotated[str, Field(min_length=1, max_length=100)]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ClaimText = Annotated[str, Field(min_length=8, max_length=1000)]
MechanismText = Annotated[str, Field(min_length=8, max_length=1000)]
MechanismFamily = Literal[
    "trend_continuation",
    "mean_reversion",
    "breakout",
    "volatility_regime",
    "liquidity",
    "carry",
    "relative_value",
    "event",
    "other",
]
MechanismInput = Literal["price", "return", "volume", "volatility", "fundamental", "event"]


class EvidenceClaim(Contract):
    statement: ClaimText
    relation: Literal["supports", "contradicts"]
    evidence_id: Short
    passage_id: Hash


class MechanismDescriptor(Contract):
    family: MechanismFamily
    premise: MechanismText
    inputs: tuple[MechanismInput, ...] = Field(min_length=1, max_length=6)
    formation_horizon_bars: int = Field(ge=1, le=5000)
    holding_horizon_bars: int = Field(ge=1, le=5000)
    direction: Literal["long_only"] = "long_only"

    @model_validator(mode="after")
    def inputs_are_distinct(self) -> MechanismDescriptor:
        if len(set(self.inputs)) != len(self.inputs):
            raise ValueError("MECHANISM_INPUT_DUPLICATE")
        return self


def normalized_words(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[^\W_]+", normalized))


def mechanism_identity(descriptor: MechanismDescriptor | dict[str, Any]) -> dict[str, Any]:
    mechanism = MechanismDescriptor.model_validate(descriptor)
    inputs = tuple(sorted(set(mechanism.inputs)))
    family_payload = {
        "family": mechanism.family,
        "inputs": inputs,
        "direction": mechanism.direction,
    }
    exact_payload = {
        **family_payload,
        "premise": normalized_words(mechanism.premise),
        "formation_horizon_bars": mechanism.formation_horizon_bars,
        "holding_horizon_bars": mechanism.holding_horizon_bars,
    }
    return {
        "mechanism_fingerprint": digest(exact_payload),
        "mechanism_family_fingerprint": digest(family_payload),
        "mechanism_family": mechanism.family,
        "mechanism_descriptor": mechanism.model_dump(mode="json"),
    }


def claim_record(
    work_order_id: str, spec_hash: str, claim: EvidenceClaim | dict[str, Any]
) -> dict[str, Any]:
    item = EvidenceClaim.model_validate(claim)
    payload = {
        "work_order_id": work_order_id,
        "spec_hash": spec_hash,
        **item.model_dump(mode="json"),
        "anchor_verified": True,
        "semantic_status": "researcher_asserted",
        "verified": False,
        "authority": "evidence-only",
        "capital_eligible": False,
    }
    return {"id": "claim-" + digest(payload), **payload}


def mechanism_duplicate_reason(department: str, diagnostic: dict[str, Any]) -> str | None:
    if department == "novel" and diagnostic.get("external_mechanism_matches"):
        return "DUPLICATE_MECHANISM"
    return None
