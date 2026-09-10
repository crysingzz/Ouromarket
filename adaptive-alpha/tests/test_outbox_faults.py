"""Deterministic interleavings for external paper delivery and cancellation."""

import json

import httpx
import pytest
from test_portfolio_broker import order_intent

from adaptive_alpha.brokers.alpaca import AlpacaPaper
from adaptive_alpha.brokers.outbox import PaperOutbox
from adaptive_alpha.store import Store


@pytest.mark.parametrize(
    "update",
    [
        {"extra": 1},
        {"client_order_id": ""},
        {"side": "hold"},
        {"qty": "0"},
        {"qty": "0.5"},
        {"qty": "NaN"},
    ],
)
def test_outbox_rejects_invalid_contract_before_persistence(settings, update):
    store = Store(settings.database_url)
    store.initialize()
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: pytest.fail("No network expected"))
    ) as client:
        outbox = PaperOutbox(store, AlpacaPaper("key", "secret", client))
        with pytest.raises(ValueError):
            outbox.enqueue({**order_intent(), **update}, "operator")
    with store.transaction() as conn:
        assert store.list_records(conn, "external-intent") == []


def test_outbox_enqueue_idempotency_conflict(settings):
    store = Store(settings.database_url)
    store.initialize()
    with httpx.Client() as client:
        outbox = PaperOutbox(store, AlpacaPaper("key", "secret", client))
        identity = outbox.enqueue(order_intent(), "operator")
        assert outbox.enqueue(order_intent(), "operator") == identity
        with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
            outbox.enqueue({**order_intent(), "qty": "6"}, "operator")
        assert outbox.cancel(identity) == outbox.cancel(identity)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("risk_reject", "REJECTED"),
        ("halt", "UNKNOWN"),
        ("cancel_during_risk", "CANCELLED"),
        ("approved", "SUBMITTED"),
    ],
)
def test_initial_submission_requires_fresh_independent_approval(settings, mode, expected):
    store = Store(settings.database_url)
    store.initialize()
    with store.transaction() as conn:
        store.set_state(conn, "kill", {"halted": mode == "halt"})
    submissions = []

    def respond(request):
        if request.url.path == "/v2/account":
            return httpx.Response(200, json={"status": "ACTIVE"})
        if request.url.path == "/v2/positions":
            return httpx.Response(200, json=[])
        if request.method == "GET":
            return httpx.Response(404)
        submissions.append(request)
        return httpx.Response(
            200,
            json={
                **json.loads(request.content),
                "id": "broker-id",
                "filled_qty": "0",
                "status": "new",
            },
        )

    def risk(intent, account, positions):
        assert account["status"] == "ACTIVE" and positions == []
        if mode == "cancel_during_risk":
            with store.transaction() as conn:
                state = store.state(conn, "external-order:" + intent["client_order_id"])
                state["cancel_requested"] = True
                store.set_state(conn, "external-order:" + intent["client_order_id"], state)
        return mode != "risk_reject"

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        outbox = PaperOutbox(store, AlpacaPaper("key", "secret", client))
        identity = outbox.enqueue(order_intent(), "operator")
        assert outbox.deliver(identity, risk)["status"] == expected
    assert len(submissions) == int(mode == "approved")


@pytest.mark.parametrize(
    "mode", ["missing", "cancel_missing", "regression", "concurrent_terminal", "concurrent_error"]
)
def test_reconciliation_never_resends_or_regresses_terminal_state(settings, mode):
    store = Store(settings.database_url)
    store.initialize()
    intent = order_intent()
    observations = [0]

    def respond(request):
        assert request.method != "POST"
        if request.method == "DELETE":
            return httpx.Response(204)
        observations[0] += 1
        if mode == "missing" or mode == "cancel_missing" and observations[0] > 1:
            return httpx.Response(404)
        if mode.startswith("concurrent"):
            with store.transaction() as conn:
                store.set_state(
                    conn,
                    "external-order:" + intent["client_order_id"],
                    {"status": "FILLED", "filled_qty": "5"},
                )
            if mode == "concurrent_error":
                raise httpx.ReadTimeout("Older observer lost its response")
        return httpx.Response(
            200, json={**intent, "id": "b", "status": "partially_filled", "filled_qty": "1"}
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        outbox = PaperOutbox(store, AlpacaPaper("key", "secret", client))
        identity = outbox.enqueue(intent, "operator")
        with store.transaction() as conn:
            store.set_state(
                conn,
                "external-order:" + identity,
                {"status": "UNKNOWN", "filled_qty": "2" if mode == "regression" else "0"},
            )
        outcome = (
            outbox.cancel(identity)
            if mode == "cancel_missing"
            else outbox.deliver(identity, lambda *_: pytest.fail("Recovery must not send"))
        )
        assert outcome["status"] == ("FILLED" if mode.startswith("concurrent") else "UNKNOWN")
        with store.transaction() as conn:
            assert store.verify_audit(conn)
            if outcome["status"] == "UNKNOWN":
                assert store.state(conn, "kill")["halted"]
