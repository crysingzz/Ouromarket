"""Signed PAPER permissions are bound to trusted state and consumed only once."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event

import httpx
import pytest

from adaptive_alpha.brokers.alpaca import AlpacaPaper
from adaptive_alpha.brokers.approval import PaperRiskContext, SignedPaperExecution
from adaptive_alpha.store import Store


@pytest.fixture
def execution(tmp_path):
    store = Store(f"sqlite:///{tmp_path}/paper.db")
    store.initialize()
    with store.transaction() as conn:
        store.set_state(conn, "kill", {"halted": False})
    clock = [datetime(2026, 9, 10, 12, tzinfo=UTC)]
    context = [
        PaperRiskContext(
            quotes={"timestamp": clock[0].isoformat(), "prices": {"SPY": 100.0}},
            returns={"SPY": [0.001, -0.001] * 60},
            strategy_positions={},
            high_watermark=100_000,
            day_start_nav=100_000,
            reconciled=True,
        )
    ]
    account = {
        "id": "paper-account",
        "status": "ACTIVE",
        "cash": "100000",
        "currency": "USD",
        "trading_blocked": False,
        "account_blocked": False,
    }
    positions = []
    orders, submissions = {}, []
    behavior = {"status": "filled", "timeout": False, "on_submit": None, "on_context": None}
    reads = [0]

    def load(_strategy):
        reads[0] += 1
        if behavior["on_context"]:
            behavior["on_context"](reads[0])
        return context[0]

    def respond(request):
        if request.url.path == "/v2/account":
            return httpx.Response(200, json=account)
        if request.url.path == "/v2/positions":
            return httpx.Response(200, json=positions)
        if request.method == "GET":
            order = orders.get(request.url.params["client_order_id"])
            return httpx.Response(200, json=order) if order else httpx.Response(404)
        if request.method == "DELETE":
            for order in orders.values():
                if order["id"] == request.url.path.rsplit("/", 1)[1]:
                    order.update(status="canceled", filled_qty="0")
            return httpx.Response(204)
        intent = json.loads(request.content)
        submissions.append(intent)
        if behavior["on_submit"]:
            behavior["on_submit"]()
        order = {
            **intent,
            "id": "broker-" + intent["client_order_id"],
            "status": behavior["status"],
            "filled_qty": intent["qty"] if behavior["status"] == "filled" else "0",
        }
        orders[intent["client_order_id"]] = order
        if behavior["timeout"]:
            raise httpx.ReadTimeout("Broker received request but response was lost")
        return httpx.Response(200, json=order)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        service = SignedPaperExecution(
            store,
            AlpacaPaper("k", "s", client),
            b"x" * 32,
            "paper-account",
            load,
            clock=lambda: clock[0],
        )
        yield {
            "service": service,
            "store": store,
            "clock": clock,
            "context": context,
            "account": account,
            "positions": positions,
            "orders": orders,
            "submissions": submissions,
            "behavior": behavior,
            "reads": reads,
        }


def intent(identity="candidate-1"):
    return {
        "client_order_id": identity,
        "symbol": "SPY",
        "side": "buy",
        "qty": "5",
        "type": "market",
        "time_in_force": "day",
    }


def test_signed_success_and_terminal_replay_never_send_twice(execution):
    service, store = execution["service"], execution["store"]
    token = service.prepare(intent(), "strategy", "operator")
    with pytest.raises(ValueError, match="SIGNED_PAPER_APPROVAL_REQUIRED"):
        service.outbox.deliver("candidate-1", lambda *_: True)
    assert service.deliver("candidate-1", token)["status"] == "FILLED"
    assert service.deliver("candidate-1", token)["status"] == "FILLED"
    assert service.reconcile("candidate-1", token)["status"] == "FILLED"
    assert len(execution["submissions"]) == 1
    with store.transaction() as conn:
        assert store.state(conn, "paper-approval:" + token["claims"]["id"])["status"] == "CONSUMED"
        assert not store.state(conn, "paper-account-reservation:paper-account")
        assert store.verify_audit(conn)


@pytest.mark.parametrize("mode", ["existing", "expired_lookup", "malformed_response"])
def test_permission_rechecked_after_idempotency_network_lookup(execution, monkeypatch, mode):
    service = execution["service"]
    token = service.prepare(intent(), "strategy", "operator")
    if mode == "existing":
        execution["orders"]["candidate-1"] = {
            **intent(),
            "id": "existing-order",
            "status": "filled",
            "filled_qty": "5",
        }
    elif mode == "expired_lookup":

        def lookup(_):
            execution["clock"][0] += timedelta(seconds=31)
            return None

        monkeypatch.setattr(service.broker, "by_client_id", lookup)
    else:
        original = service.broker.request
        monkeypatch.setattr(
            service.broker,
            "request",
            lambda method, path, **kwargs: (
                [] if method == "POST" else original(method, path, **kwargs)
            ),
        )
    result = service.deliver("candidate-1", token)
    assert result["status"] == ("FILLED" if mode == "existing" else "UNKNOWN")
    assert execution["submissions"] == []


@pytest.mark.parametrize(
    "mode",
    [
        "signature",
        "identity",
        "expiry",
        "backwards",
        "quotes",
        "account",
        "policy",
        "used",
        "saved",
        "binding",
        "kill",
    ],
)
def test_approval_failures_cannot_reach_transport(execution, mode):
    service, store = execution["service"], execution["store"]
    token = service.prepare(intent(), "strategy", "operator")
    if mode == "signature":
        token["claims"]["intent_digest"] = "forged"
    elif mode == "identity":
        token["claims"]["account_id"] = "another-account"
        token["signature"] = service._signature(token["claims"])
    elif mode in {"expiry", "backwards"}:
        execution["clock"][0] += timedelta(seconds=30 if mode == "expiry" else -1)
    elif mode == "quotes":
        execution["context"][0].quotes["prices"]["SPY"] = 101
    elif mode == "account":
        execution["account"]["cash"] = "99999"
    elif mode in {"policy", "binding", "saved"}:
        token["claims"][
            {"policy": "policy_digest", "binding": "intent_digest", "saved": "issued_at"}[mode]
        ] = (
            "invalid"
            if mode != "saved"
            else (execution["clock"][0] - timedelta(seconds=1)).isoformat()
        )
        token["signature"] = service._signature(token["claims"])
    elif mode == "used":
        with store.transaction() as conn:
            store.set_state(conn, "paper-approval:" + token["claims"]["id"], {"status": "CONSUMED"})
    else:
        with store.transaction() as conn:
            store.set_state(conn, "kill", {"halted": True})
    with pytest.raises(ValueError):
        service.deliver("candidate-1", token)
    assert not execution["submissions"]
    with store.transaction() as conn:
        assert store.state(conn, "external-order:candidate-1")["status"] == "QUEUED"


@pytest.mark.parametrize(
    "mode",
    [
        "account",
        "cash",
        "position",
        "duplicates",
        "ownership",
        "missing_quote",
        "reconciliation",
        "risk",
    ],
)
def test_invalid_trusted_inputs_never_issue_permission(execution, mode):
    if mode == "account":
        execution["account"]["id"] = "wrong"
    elif mode == "cash":
        execution["account"]["cash"] = "NaN"
    elif mode == "position":
        execution["positions"].append({"symbol": "SPY", "qty": "0.5"})
    elif mode == "duplicates":
        execution["positions"].extend([{"symbol": "SPY", "qty": "1"}] * 2)
    elif mode == "ownership":
        execution["context"][0].strategy_positions["SPY"] = 1
    elif mode == "missing_quote":
        execution["context"][0].quotes["prices"].clear()
    elif mode == "reconciliation":
        execution["context"][0] = replace(execution["context"][0], reconciled=False)
    else:
        execution["context"][0].returns.clear()
    with pytest.raises(ValueError):
        execution["service"].prepare(intent(), "strategy", "operator")
    with execution["store"].transaction() as conn:
        assert not execution["store"].list_records(conn, "paper-risk-approval")
    assert not execution["submissions"]


def test_sale_uses_reconciled_strategy_ownership(execution):
    execution["positions"].append({"symbol": "SPY", "qty": "10"})
    execution["context"][0].strategy_positions["SPY"] = 10
    service = execution["service"]
    token = service.prepare({**intent(), "side": "sell"}, "strategy", "operator")
    assert service.deliver("candidate-1", token)["status"] == "FILLED"


@pytest.mark.parametrize("mode", ["changed", "expired", "halt", "cancel"])
def test_last_moment_checks_prevent_submission(execution, mode):
    service, store = execution["service"], execution["store"]
    token = service.prepare(intent(), "strategy", "operator")

    def update(read):
        if read != 3:
            return
        if mode == "changed":
            execution["context"][0].quotes["prices"]["SPY"] = 101
        elif mode == "expired":
            execution["clock"][0] += timedelta(seconds=30)
        elif mode == "halt":
            with store.transaction() as conn:
                store.set_state(conn, "kill", {"halted": True})
        else:
            service.cancel("candidate-1", token)

    execution["behavior"]["on_context"] = update
    assert service.deliver("candidate-1", token)["status"] == (
        "UNKNOWN" if mode == "halt" else "CANCELLED" if mode == "cancel" else "REJECTED"
    )
    assert not execution["submissions"]


def test_pending_order_serializes_other_approvals_and_concurrent_reuse(execution):
    service = execution["service"]
    first = service.prepare(intent(), "strategy", "operator")
    second = service.prepare(intent("candidate-2"), "strategy", "operator")
    entered, release = Event(), Event()

    def block():
        entered.set()
        assert release.wait(5)

    execution["behavior"]["on_submit"] = block
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = pool.submit(service.deliver, "candidate-1", first)
        assert entered.wait(5)
        try:
            assert service.deliver("candidate-1", first)["status"] == "SENDING"
            with pytest.raises(ValueError, match="PAPER_ACCOUNT_HAS_PENDING_ORDER"):
                service.deliver("candidate-2", second)
        finally:
            release.set()
        assert result.result()["status"] == "FILLED"
    assert len(execution["submissions"]) == 1


def test_unknown_keeps_reservation_until_actual_broker_reconciliation(execution):
    service, store = execution["service"], execution["store"]
    token = service.prepare(intent(), "strategy", "operator")
    execution["behavior"]["timeout"] = True
    assert service.deliver("candidate-1", token)["status"] == "UNKNOWN"
    with store.transaction() as conn:
        assert store.state(conn, "kill")["halted"]
        assert store.state(conn, "paper-account-reservation:paper-account")
    observed = execution["orders"].pop("candidate-1")
    assert service.reconcile("candidate-1", token)["status"] == "UNKNOWN"
    execution["orders"]["candidate-1"] = observed
    execution["clock"][0] += timedelta(hours=1)
    assert service.reconcile("candidate-1", token)["status"] == "FILLED"
    assert len(execution["submissions"]) == 1


def test_cancel_before_and_after_submission_and_worker_recovery(execution):
    service, store = execution["service"], execution["store"]
    token = service.prepare(intent(), "strategy", "operator")
    assert service.cancel("candidate-1", token)["status"] == "CANCELLED"
    second = service.prepare(intent("candidate-2"), "strategy", "operator")
    execution["behavior"]["status"] = "new"
    assert service.deliver("candidate-2", second)["status"] == "SUBMITTED"
    assert service.cancel("candidate-2", second)["status"] == "CANCELLED"
    third = service.prepare(intent("candidate-3"), "strategy", "operator")
    with store.transaction() as conn:
        store.set_state(
            conn, "external-order:candidate-3", {"status": "SENDING", "filled_qty": "0"}
        )
    assert service.reconcile("candidate-3", third)["status"] == "UNKNOWN"
    assert len(execution["submissions"]) == 1


def test_configuration_clock_and_unrelated_token(execution):
    service = execution["service"]
    with pytest.raises(ValueError, match="CONFIGURATION"):
        SignedPaperExecution(service.store, service.broker, b"short", "id", service.context)
    default = SignedPaperExecution(service.store, service.broker, b"x" * 32, "id", service.context)
    assert default.clock().tzinfo is UTC
    token = service.prepare(intent(), "strategy", "operator")
    with pytest.raises(ValueError, match="INVALID_PAPER_APPROVAL"):
        service.deliver("candidate-2", deepcopy(token))
    with pytest.raises(ValueError, match="INVALID_PAPER_APPROVAL"):
        service.deliver("candidate-1", {})
