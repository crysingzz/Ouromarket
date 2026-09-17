"""Autonomous research requests, separate from the immutable demo-v1 protocol."""

from typing import Literal

from pydantic import Field, model_validator

from adaptive_alpha.domain import Contract, new_id

FullTextPolicy = Literal["abstract-only", "available-arxiv-html"]


class CampaignRequest(Contract):
    objective: str = Field(min_length=8, max_length=2000)
    query: str = Field(min_length=3, max_length=300)
    dataset_id: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9._:-]+$")
    generations: int = Field(default=2, ge=1, le=10)
    token_budget: int = Field(default=40_000, ge=4000, le=100_000)
    engineer: Literal["ouroboros"] = "ouroboros"
    department: Literal["replication", "novel"] = "replication"
    max_seconds: int = Field(default=600, ge=30, le=1800)
    workflow: Literal["static", "adaptive"] = "adaptive"
    agent_revision_id: str | None = None
    propose_agent_revision: bool = False
    sources: list[Literal["openalex", "arxiv", "semantic_scholar"]] = Field(
        default=["openalex"], min_length=1, max_length=3
    )
    full_text_policy: FullTextPolicy = "abstract-only"


class Candidate(Contract):
    name: str = Field(min_length=1, max_length=100)
    hypothesis: str = Field(min_length=8, max_length=3000)
    rationale: str = Field(min_length=8, max_length=3000)
    evidence_ids: list[str] = Field(max_length=20)
    contradictions: list[str] = Field(max_length=10)
    failure_modes: list[str] = Field(min_length=1, max_length=10)
    source: str = Field(min_length=20, max_length=16_384)


class Bar(Contract):
    time: str
    available_at: str
    close: float = Field(gt=0, le=1e9)
    volume: float = Field(ge=0, le=1e15)


class DatasetImport(Contract):
    name: str = Field(min_length=1, max_length=100)
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.]{0,9}$")
    provenance: str = Field(min_length=5, max_length=2000)
    adjustment: Literal["raw", "split", "total_return", "synthetic"]
    point_in_time_verified: bool = False
    bars: list[Bar] = Field(min_length=300, max_length=5000)


class AdjustmentPolicy(Contract):
    name: str = Field(min_length=3, max_length=100)
    version: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")
    adjusted_series: Literal["split", "total_return"]
    description: str = Field(min_length=8, max_length=1000)


class PITObservation(Contract):
    event_time: str
    published_at: str
    received_at: str
    source_sequence: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9._:-]+$")
    revision: int = Field(ge=1, le=100)
    corrects_source_sequence: str | None = Field(
        default=None, max_length=100, pattern=r"^[a-zA-Z0-9._:-]+$"
    )
    raw_close: float = Field(gt=0, le=1e9)
    adjusted_close: float = Field(gt=0, le=1e9)
    volume: float = Field(ge=0, le=1e15)


class PITDatasetImport(Contract):
    name: str = Field(min_length=1, max_length=100)
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.]{0,9}$")
    provider: str = Field(min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    provider_dataset_id: str = Field(min_length=1, max_length=200)
    license_url: str = Field(max_length=1000, pattern=r"^https://")
    usage_rights: Literal["research"]
    calendar: Literal["XNYS"]
    timezone: Literal["America/New_York"]
    frequency: Literal["1d"] = "1d"
    adjustment_policy: AdjustmentPolicy
    observations: list[PITObservation] = Field(min_length=300, max_length=6000)


class Evidence(Contract):
    id: str = Field(default_factory=new_id)
    provider: str
    external_id: str
    title: str = Field(max_length=2000)
    abstract: str = Field(max_length=16_000)
    url: str
    published: str
    references: list[str]
    retrieved_at: str
    content_hash: str
    content_level: Literal["metadata", "abstract", "full_text"] = "abstract"
    full_text: str | None = Field(default=None, max_length=100_000)
    full_text_source_url: str | None = Field(default=None, max_length=1000)
    license_url: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def content_claim_matches(self) -> "Evidence":
        if self.content_level == "full_text" and not self.full_text:
            raise ValueError("FULL_TEXT_CONTENT_REQUIRED")
        if self.content_level == "full_text" and not self.full_text_source_url:
            raise ValueError("FULL_TEXT_PROVENANCE_REQUIRED")
        if self.content_level != "full_text" and self.full_text is not None:
            raise ValueError("FULL_TEXT_LEVEL_REQUIRED")
        if self.content_level != "full_text" and self.full_text_source_url is not None:
            raise ValueError("FULL_TEXT_PROVENANCE_LEVEL_REQUIRED")
        return self


class ProgramEvaluation(Contract):
    experiment_id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=20, max_length=16_384)
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.]{0,9}$")
