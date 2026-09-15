"""Run inside the worker container: real OpenAlex + controlled generator + real E1.

This tests integration and reproduction without consuming OpenAI tokens.
"""

import argparse
import json
from typing import Any

import polars as pl

from adaptive_alpha.config import Settings
from adaptive_alpha.data import synthetic_daily
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.research.contracts import (
    Bar,
    CampaignRequest,
    Candidate,
    DatasetImport,
    Evidence,
)
from adaptive_alpha.research.datasets import import_dataset
from adaptive_alpha.research.reproduction import reproduce
from adaptive_alpha.store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline-literature",
        action="store_true",
        help="Use explicitly labelled evidence fixtures for repeatable CI",
    )
    args = parser.parse_args()
    config = Settings()
    store = Store(config.database_url, manage_schema=config.manage_schema)
    store.initialize()
    frame = synthetic_daily(42).filter(pl.col("symbol") == "SPY")
    dataset = DatasetImport(
        name="Integration mock · synthetic SPY",
        symbol="SPY",
        provenance="Synthetic integration fixture; no market claims",
        adjustment="synthetic",
        bars=[
            Bar(
                time=r["event_time"].isoformat(),
                available_at=r["available_time"].isoformat(),
                close=r["close"],
                volume=0,
            )
            for r in frame.to_dicts()
        ],
    )
    manifest = import_dataset(store, dataset, "integration-test")
    pipeline = Campaigns(store, config)
    campaign = pipeline.create(
        CampaignRequest(
            objective="Integration mock: test literature-to-program lifecycle",
            query="equity momentum transaction costs",
            dataset_id=manifest["id"],
            model="controlled-fixture-no-llm",
            generations=3,
            token_budget=90000,
        ),
        "integration-test",
        defer=True,
    )
    # Own only this campaign. Do not claim or interfere with user research jobs.
    import time

    from adaptive_alpha.domain import new_id

    lease = new_id()
    with store.transaction() as conn:
        state = store.state(conn, "campaign:" + campaign["id"])
        state.update(status="RUNNING", lease=lease, lease_until=time.time() + 630)
        store.set_state(conn, "campaign:" + campaign["id"], state)

    def generate(
        model: str, context: dict[str, Any], budget: int
    ) -> tuple[Candidate, dict[str, Any]]:
        window = 15 + context["generation"] * 5
        source = f"def signal(history):\n    if len(history) < {window}:\n        return 0\n    return 0.1 if history[-1] > sum(history[-{window}:])/{window} else 0\n"
        return Candidate(
            name=f"Controlled G{context['generation']}",
            hypothesis="Trend persistence may survive trading costs",
            rationale="Controlled generator validates integration; no AI discovery is claimed",
            evidence_ids=[context["evidence"][0]["id"]],
            contradictions=["Synthetic data cannot confirm the paper"],
            failure_modes=["Whipsaw and transaction costs"],
            source=source,
        ), {"provider": "controlled-fixture", "input_tokens": 0, "output_tokens": 0}

    search = None
    if args.offline_literature:
        from adaptive_alpha.domain import digest, now

        def offline_search(query: str) -> list[Evidence]:
            return [
                Evidence(
                    provider="fixture",
                    external_id="ci-evidence",
                    title="Controlled CI evidence; not a scientific publication",
                    abstract="Controlled test of the research lifecycle",
                    url="",
                    published="fixture",
                    references=[],
                    retrieved_at=now(),
                    content_hash=digest("ci-evidence"),
                )
            ]

        search = offline_search
    result = pipeline.run(campaign, lease, generate=generate, search=search)
    with store.transaction() as conn:
        bundle = {
            kind: [
                r
                for r in store.list_records(conn, kind, 10000)
                if r.get("campaign_id") == campaign["id"]
            ]
            for kind in (
                "candidate",
                "candidate-result",
                "autonomous-attempt",
                "campaign-diagnostics",
            )
        }
        bundle["dataset"] = store.get(conn, manifest["id"], "dataset")
        audit = store.verify_audit(conn)
    checks = reproduce(bundle)
    print(
        json.dumps(
            {
                "campaign_id": campaign["id"],
                "status": result["status"],
                "attempts": result["attempts"],
                "reproduction": checks,
                "audit_verified": audit,
                "provider": "controlled-fixture; no OpenAI request",
                "literature": "controlled fixture" if args.offline_literature else "real OpenAlex",
                "evaluation": "real isolated evaluator",
            },
            indent=2,
        )
    )
    if (
        result["status"] != "COMPLETED"
        or len(checks) != 3
        or not all(c["exact"] for c in checks)
        or not audit
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
