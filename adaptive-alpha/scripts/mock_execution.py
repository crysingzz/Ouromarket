"""Run paper controls against a disposable test account, never the deployed registry."""

import argparse
import json
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from adaptive_alpha.api.app import create_app
from adaptive_alpha.config import Settings
from adaptive_alpha.domain import HiddenFeedback, Hypothesis, OrderIntent, StrategySpec


class NoEvaluation:
    def evaluate(self, experiment_id: str, spec: StrategySpec) -> HiddenFeedback:
        raise RuntimeError("This execution-only mock must never submit research evaluations")


def run_mock() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, condition: bool, detail: Any) -> None:
        checks.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})
        if not condition:
            raise RuntimeError(f"Mock check failed: {name}")

    with TemporaryDirectory(prefix="alpha-mock-execution-") as directory:
        temporary = Path(directory)
        operator, research, evaluator = (secrets.token_urlsafe(48) for _ in range(3))
        settings = Settings(
            database_url=f"sqlite:///{temporary}/account.db",
            evaluator_database_url=f"sqlite:///{temporary}/unused-hidden.db",
            operator_token=SecretStr(operator),
            research_token=SecretStr(research),
            evaluator_token=SecretStr(evaluator),
            secrets_dir=temporary / "no-mounted-secrets",
        )
        with TestClient(create_app(settings, NoEvaluation())) as client:
            client.headers["Authorization"] = f"Bearer {operator}"
            agent_headers = {"Authorization": f"Bearer {research}"}
            hypothesis = Hypothesis(
                statement="MOCK execution fixture; not an investment hypothesis",
                economic_rationale="No economic claim: isolated execution contract test",
                supporting_evidence=(),
                contradictory_evidence=(),
                expected_regime="Synthetic test fixture",
                expected_failure_modes=("Risk rejection", "Stale quotes", "Broker mismatch"),
                proposed_test="Buy, retry, reject, halt, resume and close synthetic paper position",
            )
            client.post(
                "/api/hypotheses", json=hypothesis.model_dump(mode="json")
            ).raise_for_status()
            strategy = StrategySpec(
                name="MOCK execution control fixture (not evaluated)",
                hypothesis_id=hypothesis.id,
                thesis="Pre-admitted fixture only in a disposable mock database",
            )
            client.post("/api/strategies", json=strategy.model_dump(mode="json")).raise_for_status()
            path = f"/api/strategies/{strategy.id}/paper"
            denied = client.post(path, json={})
            check("unvalidated_admission_blocked", denied.status_code == 409, denied.json())

            # Test setup only, in a fresh temporary SQLite database. No live service,
            # evaluator result, limit or persistent strategy is changed by this fixture.
            store = client.app.state.store
            with store.transaction() as conn:
                store.set_state(
                    conn,
                    f"strategy:{strategy.id}",
                    {
                        "status": "VALIDATED",
                        "capital_eligible": False,
                        "mock_fixture": True,
                        "validation_source": "test-setup-not-research-evaluation",
                    },
                )
                store.audit(
                    conn,
                    "mock.fixture_loaded",
                    "test-harness",
                    {
                        "strategy_id": strategy.id,
                        "not_evaluated": True,
                    },
                )
            denied = client.post(path, json={}, headers=agent_headers)
            check("agent_admission_blocked", denied.status_code == 403, denied.json())
            client.post(path, json={}).raise_for_status()
            initial = client.get("/api/portfolio").json()
            intent = OrderIntent(strategy_id=strategy.id, instrument="SPY", side="BUY", quantity=10)
            buy = client.post("/api/orders", json=intent.model_dump()).json()
            check(
                "buy_filled_after_risk",
                buy["status"] == "FILLED" and buy["decision"]["status"] == "APPROVE",
                {"price": buy.get("fill_price"), "quantity": 10, "costs": buy.get("costs")},
            )
            repeated = client.post("/api/orders", json=intent.model_dump()).json()
            fills = client.get("/api/fills").json()
            check(
                "identical_retry_fills_once",
                repeated == buy and len(fills) == 1,
                {"fills": len(fills)},
            )
            conflict = client.post("/api/orders", json={**intent.model_dump(), "quantity": 11})
            check("changed_retry_rejected", conflict.status_code == 409, conflict.json())

            oversized = intent.model_copy(
                update={"order_intent_id": "oversized", "quantity": 100000}
            )
            rejected = client.post("/api/orders", json=oversized.model_dump()).json()
            check(
                "oversized_order_rejected",
                rejected["decision"]["status"] == "REJECT",
                [
                    rule["rule"]
                    for rule in rejected["decision"]["checks"]
                    if rule["status"] == "FAIL"
                ],
            )
            outside = intent.model_copy(
                update={"order_intent_id": "outside-universe", "instrument": "QQQ"}
            )
            rejected_scope = client.post("/api/orders", json=outside.model_dump())
            check(
                "instrument_scope_enforced",
                rejected_scope.status_code == 409,
                rejected_scope.json(),
            )

            client.post("/api/risk/halt", json={"reason": "Mock emergency stop"}).raise_for_status()
            halted = client.post(
                "/api/orders", json={**intent.model_dump(), "order_intent_id": "while-halted"}
            ).json()
            check(
                "kill_switch_blocks_orders",
                halted["decision"]["status"] == "HALT",
                halted["status"],
            )
            agent_resume = client.post(
                "/api/risk/resume",
                json={"reason": "Mock unauthorized resume"},
                headers=agent_headers,
            )
            check(
                "agent_cannot_resume",
                agent_resume.status_code == 403 and client.get("/api/risk/status").json()["halted"],
                agent_resume.json(),
            )
            client.post(
                "/api/risk/resume", json={"reason": "Mock operator recovery"}
            ).raise_for_status()
            sell = client.post(
                "/api/orders",
                json={**intent.model_dump(), "order_intent_id": "close-position", "side": "SELL"},
            ).json()
            check(
                "position_closed",
                sell["status"] == "FILLED",
                {"price": sell.get("fill_price"), "costs": sell.get("costs")},
            )

            with store.transaction() as conn:
                quotes = store.state(conn, "quotes")
                quotes["timestamp"] = "2000-01-01T00:00:00+00:00"
                store.set_state(conn, "quotes", quotes)
            stale = client.post(
                "/api/orders", json={**intent.model_dump(), "order_intent_id": "stale-quote"}
            ).json()
            check(
                "stale_quotes_halt",
                stale["decision"]["status"] == "HALT",
                [rule["rule"] for rule in stale["decision"]["checks"] if rule["status"] == "FAIL"],
            )
            client.post("/api/market/demo-refresh", json={}).raise_for_status()
            client.post(
                "/api/risk/resume", json={"reason": "Mock quote restored"}
            ).raise_for_status()

            with store.transaction() as conn:
                original_broker = store.state(conn, "broker")
                store.set_state(
                    conn, "broker", {**original_broker, "cash": original_broker["cash"] - 1}
                )
            mismatch = client.post(
                "/api/orders", json={**intent.model_dump(), "order_intent_id": "mismatch"}
            ).json()
            check(
                "broker_mismatch_halts",
                mismatch["decision"]["status"] == "HALT",
                mismatch["status"],
            )
            resume = client.post(
                "/api/risk/resume", json={"reason": "Mock mismatch recovery attempt"}
            )
            check("unreconciled_resume_blocked", resume.status_code == 409, resume.json())
            with store.transaction() as conn:
                store.set_state(conn, "broker", original_broker)
            client.post(
                "/api/risk/resume", json={"reason": "Mock reconciliation restored"}
            ).raise_for_status()
            final = client.get("/api/portfolio").json()
            fills = client.get("/api/fills").json()
            audit = client.get("/api/audit").json()
            cost = sum(fill["costs"] for fill in fills)
            check(
                "account_and_costs_reconciled",
                len(fills) == 2
                and final["positions"].get("SPY") == 0
                and final["reconciled"]
                and abs(initial["nav"] - final["nav"] - cost) < 0.00001,
                {
                    "initial_nav": initial["nav"],
                    "final_nav": final["nav"],
                    "costs": cost,
                    "fills": len(fills),
                },
            )
            check("audit_chain_verified", audit["verified"], {"events": len(audit["events"])})
            return {
                "mode": "isolated-mock-account",
                "admission": "explicit test fixture; not an evaluator PASS",
                "checks": checks,
                "initial_portfolio": initial,
                "final_portfolio": final,
                "orders": client.get("/api/orders").json(),
                "fills": fills,
                "audit": audit,
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_mock()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                "checks_passed": len(result["checks"]),
                "initial_nav": result["initial_portfolio"]["nav"],
                "final_nav": result["final_portfolio"]["nav"],
                "positions": result["final_portfolio"]["positions"],
                "report": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
