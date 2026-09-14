"""Immutable search scope and extractive citation anchors for research departments."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator
from sqlalchemy.engine import Connection

from adaptive_alpha.domain import Contract, digest, now
from adaptive_alpha.research.contracts import Evidence
from adaptive_alpha.store import Store

Short = Annotated[str, Field(min_length=1, max_length=100)]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Source = Literal["openalex", "arxiv", "semantic_scholar", "injected"]
Health = Literal["available", "no_results", "unavailable", "test"]
Department = Literal["replication", "novel"]


class EvidenceBinding(Contract):
    evidence_id: Short
    content_hash: Hash
    provider: str = Field(min_length=1, max_length=80)
    external_id: str = Field(min_length=1, max_length=500)
    content_level: Literal["metadata", "abstract", "full_text"]


class EvidencePassage(Contract):
    id: Hash
    evidence_id: Short
    evidence_hash: Hash
    field: Literal["title", "abstract", "full_text"]
    start: int = Field(ge=0, le=100_000)
    end: int = Field(gt=0, le=100_000)
    text: str = Field(min_length=1, max_length=800)

    @model_validator(mode="after")
    def offsets_and_identity_match(self) -> EvidencePassage:
        if self.end - self.start != len(self.text):
            raise ValueError("EVIDENCE_PASSAGE_OFFSETS_INVALID")
        expected = digest(
            {
                "evidence_id": self.evidence_id,
                "evidence_hash": self.evidence_hash,
                "field": self.field,
                "start": self.start,
                "end": self.end,
                "text": self.text,
            }
        )
        if self.id != expected:
            raise ValueError("EVIDENCE_PASSAGE_IDENTITY_INVALID")
        return self


class ResearchEvidencePacket(Contract):
    id: str = Field(pattern=r"^evidence-packet-[a-f0-9]{64}$")
    campaign_id: Short
    department: Department
    query: str = Field(min_length=3, max_length=300)
    requested_sources: tuple[Source, ...] = Field(min_length=1, max_length=4)
    source_health: dict[Source, Health]
    evidence: tuple[EvidenceBinding, ...] = Field(min_length=1, max_length=24)
    passages: tuple[EvidencePassage, ...] = Field(min_length=1, max_length=48)
    status: Literal[
        "REPLICATION_EVIDENCE_INCOMPLETE",
        "REPLICATION_EVIDENCE_AVAILABLE",
        "NOVELTY_SEARCH_SCOPED",
    ]
    gaps: tuple[str, ...] = Field(max_length=12)
    search_digest: Hash
    created_at: str
    authority: Literal["evidence-only"] = "evidence-only"
    capital_eligible: Literal[False] = False

    def identity_payload(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "department": self.department,
            "query": self.query,
            "requested_sources": self.requested_sources,
            "source_health": self.source_health,
            "evidence": [item.model_dump(mode="json") for item in self.evidence],
            "passages": [item.model_dump(mode="json") for item in self.passages],
            "status": self.status,
            "gaps": self.gaps,
            "authority": self.authority,
            "capital_eligible": self.capital_eligible,
        }

    @model_validator(mode="after")
    def bindings_match(self) -> ResearchEvidencePacket:
        if (
            len(set(self.requested_sources)) != len(self.requested_sources)
            or set(self.source_health) != set(self.requested_sources)
            or len({item.evidence_id for item in self.evidence}) != len(self.evidence)
            or len({item.id for item in self.passages}) != len(self.passages)
        ):
            raise ValueError("EVIDENCE_PACKET_BINDING_INVALID")
        bindings = {item.evidence_id: item.content_hash for item in self.evidence}
        if any(bindings.get(item.evidence_id) != item.evidence_hash for item in self.passages):
            raise ValueError("EVIDENCE_PACKET_PASSAGE_UNBOUND")
        expected = digest(self.identity_payload())
        if self.search_digest != expected or self.id != "evidence-packet-" + expected:
            raise ValueError("EVIDENCE_PACKET_IDENTITY_INVALID")
        return self


def _passages(query: str, item: Evidence) -> list[EvidencePassage]:
    terms = set(re.findall(r"[^\W_]{3,}", query.casefold()))
    candidates: list[tuple[int, str, int, int, str]] = []
    fields = {"title": item.title, "abstract": item.abstract}
    if item.full_text:
        fields["full_text"] = item.full_text
    for field, content in fields.items():
        for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", content):
            raw = match.group()
            left = len(raw) - len(raw.lstrip())
            text = raw.strip()[:800]
            if not text:
                continue
            start = match.start() + left
            end = start + len(text)
            score = len(terms & set(re.findall(r"[^\W_]{3,}", text.casefold())))
            candidates.append((score, field, start, end, text))
    candidates.sort(key=lambda value: (-value[0], value[1] != "abstract", value[2]))
    result = []
    for _, field, start, end, text in candidates[:2]:
        payload = {
            "evidence_id": item.id,
            "evidence_hash": item.content_hash,
            "field": field,
            "start": start,
            "end": end,
            "text": text,
        }
        result.append(EvidencePassage.model_validate({"id": digest(payload), **payload}))
    return result


def build_evidence_packet(
    campaign_id: str,
    department: Department,
    query: str,
    requested_sources: tuple[Source, ...],
    source_health: dict[Source, Health],
    evidence: list[Evidence],
) -> ResearchEvidencePacket:
    if set(source_health) != set(requested_sources):
        raise ValueError("EVIDENCE_SOURCE_HEALTH_MISMATCH")
    items = [Evidence.model_validate(item.model_dump(mode="json")) for item in evidence]
    if len({item.id for item in items}) != len(items):
        raise ValueError("EVIDENCE_ID_DUPLICATE")
    bindings = tuple(
        EvidenceBinding(
            evidence_id=item.id,
            content_hash=item.content_hash,
            provider=item.provider,
            external_id=item.external_id,
            content_level=item.content_level,
        )
        for item in items
    )
    passages = tuple(passage for item in items for passage in _passages(query, item))
    if not passages:
        raise ValueError("CITABLE_EVIDENCE_TEXT_REQUIRED")
    unavailable = tuple(
        f"SOURCE_UNAVAILABLE:{source}"
        for source in requested_sources
        if source_health[source] == "unavailable"
    )
    if department == "replication":
        full_text = any(item.content_level == "full_text" for item in items)
        status = (
            "REPLICATION_EVIDENCE_AVAILABLE" if full_text else "REPLICATION_EVIDENCE_INCOMPLETE"
        )
        gaps = (
            unavailable
            + (() if full_text else ("FULL_TEXT_NOT_RETRIEVED",))
            + ("FORMULAS_TABLES_AND_PARAMETERS_NOT_VERIFIED",)
        )
    else:
        status = "NOVELTY_SEARCH_SCOPED"
        gaps = unavailable + (
            "SCIENTIFIC_NOVELTY_UNVERIFIED",
            "SEARCH_SCOPE_LIMITED_TO_REQUESTED_SOURCES",
        )
    payload: dict[str, Any] = {
        "campaign_id": campaign_id,
        "department": department,
        "query": query,
        "requested_sources": requested_sources,
        "source_health": source_health,
        "evidence": [item.model_dump(mode="json") for item in bindings],
        "passages": [item.model_dump(mode="json") for item in passages],
        "status": status,
        "gaps": gaps,
        "authority": "evidence-only",
        "capital_eligible": False,
    }
    identity = digest(payload)
    return ResearchEvidencePacket(
        id="evidence-packet-" + identity,
        search_digest=identity,
        created_at=now(),
        **payload,
    )


def verify_evidence_packet(
    conn: Connection, store: Store, packet_id: str
) -> ResearchEvidencePacket:
    packet = ResearchEvidencePacket.model_validate(store.get(conn, packet_id, "evidence-packet"))
    records: dict[str, Evidence] = {}
    for binding in packet.evidence:
        record = Evidence.model_validate(store.get(conn, binding.evidence_id, "evidence"))
        if (
            record.content_hash != binding.content_hash
            or record.provider != binding.provider
            or record.external_id != binding.external_id
            or record.content_level != binding.content_level
        ):
            raise ValueError("EVIDENCE_PACKET_SOURCE_MISMATCH")
        records[record.id] = record
    for passage in packet.passages:
        record = records[passage.evidence_id]
        content = getattr(record, passage.field)
        if not isinstance(content, str) or content[passage.start : passage.end] != passage.text:
            raise ValueError("EVIDENCE_PACKET_PASSAGE_MISMATCH")
    return packet
