"""Explicit research roles. Similarity is a diagnostic, not a claim of scientific novelty."""

import ast
import re
from typing import Any

from adaptive_alpha.domain import digest
from adaptive_alpha.research.contracts import Candidate, DatasetImport, Evidence
from adaptive_alpha.research.portfolio import market_features


class LiteratureAgent:
    def summarize(self, evidence: list[Evidence]) -> dict[str, Any]:
        return {
            "role": "literature",
            "documents": [
                {"id": e.id, "title": e.title, "abstract": e.abstract[:2000]} for e in evidence
            ],
            "limitations": ["Metadata and abstracts only; full-text replication not established"],
            "source_hashes": [e.content_hash for e in evidence],
        }


class MarketAgent:
    def analyze(self, dataset: DatasetImport) -> dict[str, Any]:
        # Only predeclared initial research period is used for context. Later
        # fold outcomes are public diagnostics, independently from hidden E1.
        training = dataset.model_copy(update={"bars": dataset.bars[: len(dataset.bars) // 2]})
        return {
            "role": "market",
            **market_features(training),
            "symbol": dataset.symbol,
            "frequency": "daily",
            "adjustment": dataset.adjustment,
        }


class NoveltyAgent:
    def compare(self, candidate: Candidate, previous: list[dict[str, Any]]) -> dict[str, Any]:
        tokens = set(re.findall(r"\w+", candidate.hypothesis.lower()))
        similarity = []
        for other in previous:
            other_tokens = set(re.findall(r"\w+", str(other.get("hypothesis", "")).lower()))
            similarity.append(len(tokens & other_tokens) / max(1, len(tokens | other_tokens)))
        try:
            structural_hash = digest(
                ast.dump(ast.parse(candidate.source), include_attributes=False)
            )
        except SyntaxError:
            structural_hash = None
        return {
            "role": "novelty",
            "lexical_similarity": max(similarity, default=0.0),
            "program_ast_hash": structural_hash,
            "scientific_novelty": "unverified",
            "contradictions": candidate.contradictions,
        }


class CriticAgent:
    def analyze(self, public: dict[str, Any]) -> dict[str, Any]:
        failed = [name for name, passed in public["gates"].items() if not passed]
        return {
            "role": "critic",
            "failed_public_gates": failed,
            "counter_tests": [
                "Triple transaction costs",
                "Require stability across chronological folds",
                "Compare against unchanged baseline",
            ],
            "public_oos": public["public_oos"],
            "recommendation": "Propose a different falsifiable mechanism"
            if failed
            else "Seek contradictory evidence and stress the mechanism",
        }
