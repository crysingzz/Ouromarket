import json

import httpx
import numpy as np
import pytest

from adaptive_alpha.brokers.alpaca import AlpacaPaper
from adaptive_alpha.brokers.outbox import PaperOutbox
from adaptive_alpha.config import Settings
from adaptive_alpha.research.portfolio import allocate
from adaptive_alpha.store import Store


def order_intent():
    return {
        "client_order_id": "cancel-test",
        "symbol": "SPY",
        "side": "buy",
        "qty": "5",
        "type": "market",
        "time_in_force": "day",
    }


def test_cancel_queued_order_never_contacts_broker(settings: Settings) -> None:
    store = Store(settings.database_url)
    store.initialize()

    def unexpected(request):
        pytest.fail("Unsent cancellation must not contact broker")

    with httpx.Client(transport=httpx.MockTransport(unexpected)) as client:
        outbox = PaperOutbox(store, AlpacaPaper("key", "secret", client))
        identity = outbox.enqueue(order_intent(), "operator")
        assert outbox.cancel(identity)["status"] == "CANCELLED"
        assert outbox.deliver(identity, lambda *_: True)["status"] == "CANCELLED"


def test_cancel_reconciles_fill_that_races_with_acknowledgement(settings: Settings) -> None:
    store = Store(settings.database_url)
    store.initialize()
    observed = {
        **order_intent(),
        "qty": "5.000",
        "id": "broker-id",
        "status": "new",
        "filled_qty": "0",
    }
    calls = []

    def respond(request):
        calls.append(request.method)
        assert request.method != "POST"
        if request.method == "DELETE":
            observed.update(status="filled", filled_qty="5")
            return httpx.Response(204)
        return httpx.Response(200, json=observed)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        outbox = PaperOutbox(store, AlpacaPaper("key", "secret", client))
        identity = outbox.enqueue(order_intent(), "operator")
        with store.transaction() as conn:
            store.set_state(
                conn, "external-order:" + identity, {"status": "UNKNOWN", "filled_qty": "0"}
            )
        assert outbox.cancel(identity)["status"] == "FILLED"
        assert calls == ["GET", "DELETE", "GET"]


@pytest.mark.parametrize(
    "changes",
    [{"status": "unexpected"}, {"symbol": "QQQ"}, {"status": "filled", "filled_qty": "2"}],
)
def test_invalid_broker_observation_halts_without_resubmission(settings: Settings, changes) -> None:
    store = Store(settings.database_url)
    store.initialize()

    def respond(request):
        assert request.method == "GET"
        return httpx.Response(
            200, json={**order_intent(), "id": "b", "status": "new", "filled_qty": "0", **changes}
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        outbox = PaperOutbox(store, AlpacaPaper("key", "secret", client))
        identity = outbox.enqueue(order_intent(), "operator")
        with store.transaction() as conn:
            store.set_state(
                conn, "external-order:" + identity, {"status": "UNKNOWN", "filled_qty": "0"}
            )
        assert outbox.deliver(identity, lambda *_: True)["status"] == "UNKNOWN"
        with store.transaction() as conn:
            assert store.state(conn, "kill")["halted"]


def test_allocation_constrains_correlated_population() -> None:
    vector = (np.sin(np.arange(200)) * 0.001).tolist()
    results = [{"id": str(i), "status": "PASS", "public": {"returns": vector}} for i in range(4)]
    outcome = allocate(results)
    assert len(outcome["clusters"]) == 1
    assert sum(outcome["weights"].values()) <= 0.60000001
    assert max(outcome["weights"].values()) <= 0.2
    assert outcome["capital_eligible"] is False


def test_external_paper_unknown_response_recovers_without_second_order(settings: Settings) -> None:
    store = Store(settings.database_url)
    store.initialize()
    with store.transaction() as conn:
        store.set_state(conn, "kill", {"halted": False})
    broker_order = None
    submissions = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal broker_order, submissions
        assert request.url.host == "paper-api.alpaca.markets"
        if request.url.path == "/v2/account":
            return httpx.Response(200, json={"status": "ACTIVE"})
        if request.url.path == "/v2/positions":
            return httpx.Response(200, json=[])
        if request.method == "POST":
            submissions += 1
            broker_order = {
                **json.loads(request.content),
                "id": "broker1",
                "status": "partially_filled",
                "filled_qty": "2",
            }
            raise httpx.ReadTimeout("Response lost after accepted submission")
        return httpx.Response(200, json=broker_order) if broker_order else httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        broker = AlpacaPaper("paper-key", "paper-secret", client)
        outbox = PaperOutbox(store, broker)
        intent = {
            "client_order_id": "test-order",
            "symbol": "SPY",
            "side": "buy",
            "qty": "5",
            "type": "market",
            "time_in_force": "day",
        }
        outbox.enqueue(intent, "operator")
        assert outbox.deliver("test-order", lambda *_: True)["status"] == "UNKNOWN"
        assert outbox.deliver("test-order", lambda *_: True)["status"] == "PARTIAL"
        assert submissions == 1
        assert broker_order is not None
        broker_order.update(status="filled", filled_qty="5")
        assert outbox.deliver("test-order", lambda *_: True)["status"] == "FILLED"
        assert submissions == 1
        with store.transaction() as conn:
            assert store.state(conn, "kill")["halted"]
            assert store.verify_audit(conn)
