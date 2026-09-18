"""Durable external paper delivery. Unknown submissions are reconciled, never replayed blindly.

The callback delivery API is a reference/test seam. Production paper execution
uses SignedPaperExecution; approval-bound intents cannot use callback delivery.
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from sqlalchemy.engine import Connection

from adaptive_alpha.brokers.alpaca import TERMINAL, AlpacaPaper, validate_order
from adaptive_alpha.domain import digest, now
from adaptive_alpha.store import Store


class PaperOutbox:
    def __init__(self, store: Store, broker: AlpacaPaper):
        self.store, self.broker = store, broker

    @staticmethod
    def validate_intent(intent: dict[str, Any]) -> None:
        if set(intent) != {"client_order_id", "symbol", "side", "qty", "type", "time_in_force"}:
            raise ValueError("EXACT_ORDER_CONTRACT_REQUIRED")
        identity = intent["client_order_id"]
        if not isinstance(identity, str) or not 1 <= len(identity) <= 80:
            raise ValueError("CLIENT_ID_INVALID")
        if (
            intent["side"] not in {"buy", "sell"}
            or intent["type"] != "market"
            or intent["time_in_force"] != "day"
        ):
            raise ValueError("PAPER_MARKET_DAY_REQUIRED")
        quantity = Decimal(str(intent["qty"]))
        if (
            not quantity.is_finite()
            or quantity <= 0
            or quantity != quantity.to_integral_value()
            or quantity > 1_000_000
        ):
            raise ValueError("INTEGER_QUANTITY_REQUIRED")

    def enqueue(self, intent: dict[str, Any], actor: str) -> str:
        self.validate_intent(intent)
        with self.store.transaction() as conn:
            return self._enqueue(conn, intent, actor)

    def _enqueue(
        self,
        conn: Connection,
        intent: dict[str, Any],
        actor: str,
        approval_id: str | None = None,
    ) -> str:
        identity = str(intent["client_order_id"])
        try:
            existing = self.store.get(conn, "external-intent-" + identity, "external-intent")
            if (
                existing["fingerprint"] != digest(intent)
                or existing.get("approval_id") != approval_id
            ):
                raise ValueError("IDEMPOTENCY_CONFLICT")
            return identity
        except KeyError:
            self.store.append(
                conn,
                "external-intent",
                {
                    "id": identity,
                    "intent": intent,
                    "fingerprint": digest(intent),
                    "actor": actor,
                    "approval_id": approval_id,
                },
                "external-intent-" + identity,
            )
            self.store.set_state(
                conn, "external-order:" + identity, {"status": "QUEUED", "filled_qty": "0"}
            )
            self.store.audit(conn, "external.paper_queued", actor, {"id": identity})
        return identity

    def deliver(
        self,
        identity: str,
        risk_check: Callable[[dict[str, Any], dict[str, Any], list[dict[str, Any]]], bool],
    ) -> dict[str, Any]:
        """Reference/test-only callback entry point; never authorizes signed intents."""
        return self._deliver(identity, risk_check)

    def _deliver(
        self,
        identity: str,
        risk_check: Callable[[dict[str, Any], dict[str, Any], list[dict[str, Any]]], bool],
        reserve: Callable[[Connection, dict[str, Any]], None] | None = None,
        submit: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self.store.transaction() as conn:
            record = self.store.get(conn, "external-intent-" + identity, "external-intent")
            if record.get("approval_id") and reserve is None:
                raise ValueError("SIGNED_PAPER_APPROVAL_REQUIRED")
            state = self.store.state(conn, "external-order:" + identity)
            if state["status"] in {"FILLED", "CANCELLED", "REJECTED"}:
                return state
            if reserve is not None and state["status"] == "SENDING":
                # A concurrent worker may own the transport. Recovery is explicit.
                return state
            # SENDING/UNKNOWN cannot be blindly sent again after an ambiguous failure.
            recover_only = state["status"] in {"SENDING", "UNKNOWN", "SUBMITTED", "PARTIAL"}
            if not recover_only:
                if reserve is not None:
                    reserve(conn, record)
                state["status"] = "SENDING"
                self.store.set_state(conn, "external-order:" + identity, state)
        try:
            if recover_only:
                order = self.broker.by_client_id(identity)
                if order is None:
                    raise ValueError("UNKNOWN_BROKER_OUTCOME_REQUIRES_RECONCILIATION")
            else:
                account, positions = self.broker.account(), self.broker.positions()
                if not risk_check(record["intent"], account, positions):
                    with self.store.transaction() as conn:
                        state.update(status="REJECTED", reason="INDEPENDENT_RISK_REJECTED")
                        self.store.set_state(conn, "external-order:" + identity, state)
                        self.store.audit(conn, "external.paper_rejected", "risk", {"id": identity})
                    return state
                # Second kill-switch check immediately before broker transport.
                with self.store.transaction() as conn:
                    if self.store.state(conn, "external-order:" + identity).get("cancel_requested"):
                        state.update(status="CANCELLED", cancel_requested=True)
                        self.store.set_state(conn, "external-order:" + identity, state)
                        self.store.audit(
                            conn, "external.paper_cancelled_unsent", "operator", {"id": identity}
                        )
                        return state
                    if self.store.state(conn, "kill", {"halted": True}).get("halted", True):
                        raise ValueError("EMERGENCY_STOP")
                order = (submit or self.broker.submit)(record["intent"])
            validate_order(order, record["intent"])
            with self.store.transaction() as conn:
                cancel_requested = self.store.state(conn, "external-order:" + identity).get(
                    "cancel_requested", False
                )
            if cancel_requested and order["status"] not in TERMINAL:
                self.broker.cancel(str(order["id"]))
                observed = self.broker.by_client_id(identity)
                if observed is None:
                    raise ValueError("UNKNOWN_CANCEL_OUTCOME")
                validate_order(observed, record["intent"])
                order = observed
            filled = Decimal(str(order.get("filled_qty", "0")))
            if (
                not filled.is_finite()
                or filled < 0
                or filled > Decimal(str(record["intent"]["qty"]))
                or (order["status"] == "filled" and filled != Decimal(str(record["intent"]["qty"])))
            ):
                raise ValueError("INVALID_BROKER_FILL")
            status = str(order.get("status", "unknown"))
            phase = (
                "FILLED"
                if status == "filled"
                else "REJECTED"
                if status == "rejected"
                else "CANCELLED"
                if status in TERMINAL
                else "PARTIAL"
                if filled
                else "SUBMITTED"
            )
            with self.store.transaction() as conn:
                previous = self.store.state(conn, "external-order:" + identity)
                if previous["status"] in {"FILLED", "CANCELLED", "REJECTED"}:
                    return previous
                if filled < Decimal(previous["filled_qty"]):
                    raise ValueError("BROKER_FILL_REGRESSION")
                state = {
                    "status": phase,
                    "filled_qty": str(filled),
                    "broker_id": str(order["id"]),
                    "broker_status": status,
                    "updated_at": now(),
                    "cancel_requested": previous.get("cancel_requested", False),
                }
                if digest(previous) != digest(state):
                    self.store.append(conn, "external-order-event", {"id": identity, **state})
                self.store.set_state(conn, "external-order:" + identity, state)
                self.store.audit(
                    conn, "external.paper_observed", "broker", {"id": identity, **state}
                )
            return state
        except Exception:
            with self.store.transaction() as conn:
                state = self.store.state(conn, "external-order:" + identity)
                if state["status"] in {"FILLED", "CANCELLED", "REJECTED"}:
                    return state
                state.update(status="UNKNOWN", reason="BROKER_DELIVERY_OR_RECONCILIATION_FAILED")
                self.store.set_state(conn, "external-order:" + identity, state)
                self.store.set_state(
                    conn,
                    "kill",
                    {
                        "halted": True,
                        "reason": "External paper order requires reconciliation",
                        "updated_at": now(),
                    },
                )
                self.store.audit(conn, "external.paper_unknown", "broker", {"id": identity})
            return state

    def cancel(
        self,
        identity: str,
        *,
        reserve: Callable[[Connection, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        with self.store.transaction() as conn:
            self.store.get(conn, "external-intent-" + identity, "external-intent")
            state = self.store.state(conn, "external-order:" + identity)
            if state["status"] in {"FILLED", "CANCELLED", "REJECTED"}:
                return state
            state["cancel_requested"] = True
            if state["status"] == "QUEUED":
                state["status"] = "CANCELLED"
            self.store.set_state(conn, "external-order:" + identity, state)
            self.store.audit(conn, "external.paper_cancel_requested", "operator", {"id": identity})
            if state["status"] == "CANCELLED":
                return state
        # Cancel acknowledgement is not proof that an in-flight fill did not occur.
        return self._deliver(identity, lambda *_: False, reserve)
