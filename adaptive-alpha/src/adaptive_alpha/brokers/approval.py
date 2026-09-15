"""Service-owned, single-use risk authorization for the fixed Alpaca PAPER adapter.

No HTTP request supplies prices, holdings, reconciliation flags, or approval
booleans. The configured context loader belongs to the independent risk service.
Live execution is deliberately not a mode of this service.
"""

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.engine import Connection

from adaptive_alpha.brokers.alpaca import PAPER_ORIGIN, AlpacaPaper, validate_order
from adaptive_alpha.brokers.outbox import PaperOutbox
from adaptive_alpha.domain import OrderIntent, canonical, digest, new_id
from adaptive_alpha.risk.engine import POLICY, assess, policy_dict
from adaptive_alpha.store import Store


@dataclass(frozen=True)
class PaperRiskContext:
    quotes: dict[str, Any]
    returns: dict[str, list[float]]
    strategy_positions: dict[str, int]
    high_watermark: float
    day_start_nav: float
    reconciled: bool


def _positive(value: Any) -> float:
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError("INVALID_BROKER_RISK_VALUE")
    return float(number)


class SignedPaperExecution:
    """Compose only with trusted server dependencies, never a request callback."""

    def __init__(
        self,
        store: Store,
        broker: AlpacaPaper,
        signing_key: bytes,
        account_id: str,
        context: Callable[[str], PaperRiskContext],
        *,
        clock: Callable[[], datetime] | None = None,
        ttl_seconds: int = 30,
    ):
        if len(signing_key) < 32 or not account_id or not 1 <= ttl_seconds <= 60:
            raise ValueError("INVALID_PAPER_SIGNING_CONFIGURATION")
        self.store, self.broker = store, broker
        self._key, self.account_id, self.context = signing_key, account_id, context
        self.clock = clock or (lambda: datetime.now(UTC))
        self.ttl_seconds = ttl_seconds
        self.outbox = PaperOutbox(store, broker)

    def _signature(self, claims: dict[str, Any]) -> str:
        return hmac.new(self._key, canonical(claims).encode(), hashlib.sha256).hexdigest()

    def _verify(self, token: dict[str, Any], identity: str) -> dict[str, Any]:
        claims = token.get("claims")
        signature = token.get("signature")
        if (
            not isinstance(claims, dict)
            or not isinstance(signature, str)
            or not hmac.compare_digest(self._signature(claims), signature)
            or claims.get("account_id") != self.account_id
            or claims.get("origin") != PAPER_ORIGIN
            or claims.get("client_order_id") != identity
        ):
            raise ValueError("INVALID_PAPER_APPROVAL")
        return claims

    def _snapshot(
        self,
        strategy_id: str,
        raw_account: dict[str, Any] | None = None,
        raw_positions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        account = self.broker.account() if raw_account is None else raw_account
        positions = self.broker.positions() if raw_positions is None else raw_positions
        if (
            account.get("id") != self.account_id
            or account.get("status") != "ACTIVE"
            or account.get("trading_blocked", True) is not False
            or account.get("account_blocked", True) is not False
            or account.get("currency") != "USD"
        ):
            raise ValueError("BROKER_ACCOUNT_NOT_ELIGIBLE")
        context = self.context(strategy_id)
        holdings: dict[str, int] = {}
        for position in positions:
            symbol = str(position["symbol"])
            quantity = Decimal(str(position["qty"]))
            if (
                symbol not in {"SPY", "QQQ", "IWM"}
                or symbol in holdings
                or not quantity.is_finite()
                or quantity < 0
                or quantity != quantity.to_integral_value()
            ):
                raise ValueError("UNSUPPORTED_BROKER_POSITION")
            holdings[symbol] = int(quantity)
        if any(
            not isinstance(qty, int) or qty < 0 or qty > holdings.get(symbol, 0)
            for symbol, qty in context.strategy_positions.items()
        ):
            raise ValueError("STRATEGY_HOLDINGS_NOT_RECONCILED")
        snapshot = {
            "account": {
                "cash": _positive(account["cash"]),
                "positions": holdings,
                "high_watermark": _positive(context.high_watermark),
                "day_start_nav": _positive(context.day_start_nav),
            },
            "quotes": context.quotes,
            "returns": context.returns,
            "strategy_positions": context.strategy_positions,
            "reconciled": context.reconciled,
        }
        # Freeze mutable provider dictionaries before hashing or making decisions.
        return dict(json.loads(canonical(snapshot)))

    def _decision(
        self,
        intent: dict[str, Any],
        strategy_id: str,
        snapshot: dict[str, Any],
        halted: bool,
    ) -> None:
        prices = snapshot["quotes"]["prices"]
        required = set(snapshot["account"]["positions"]) | {intent["symbol"]}
        if not required <= set(prices):
            raise ValueError("MISSING_TRUSTED_QUOTES")
        decision = assess(
            OrderIntent(
                strategy_id=strategy_id,
                instrument=intent["symbol"],
                side=intent["side"].upper(),
                quantity=int(Decimal(str(intent["qty"]))),
            ),
            snapshot["account"],
            snapshot["quotes"],
            snapshot["returns"],
            snapshot["strategy_positions"],
            halted=halted,
            reconciled=snapshot["reconciled"],
            clock=self.clock(),
        )
        if decision["status"] != "APPROVE":
            raise ValueError("INDEPENDENT_RISK_REJECTED")

    def prepare(
        self,
        intent: dict[str, Any],
        strategy_id: str,
        actor: str,
    ) -> dict[str, Any]:
        self.outbox.validate_intent(intent)
        snapshot = self._snapshot(strategy_id)
        with self.store.transaction() as conn:
            self._decision(
                intent,
                strategy_id,
                snapshot,
                self.store.state(conn, "kill", {"halted": True}).get("halted", True),
            )
            timestamp = self.clock()
            claims = {
                "id": new_id(),
                "client_order_id": intent["client_order_id"],
                "strategy_id": strategy_id,
                "intent_digest": digest(intent),
                "account_id": self.account_id,
                "origin": PAPER_ORIGIN,
                "policy_version": POLICY.version,
                "policy_digest": digest(policy_dict()),
                "snapshot_digest": digest(snapshot),
                "quote_digest": digest(snapshot["quotes"]),
                "issued_at": timestamp.isoformat(),
                "expires_at": (timestamp + timedelta(seconds=self.ttl_seconds)).isoformat(),
            }
            token = {"claims": claims, "signature": self._signature(claims)}
            self.outbox._enqueue(conn, intent, actor, claims["id"])
            self.store.append(conn, "paper-risk-approval", token, "paper-approval-" + claims["id"])
            self.store.set_state(conn, "paper-approval:" + claims["id"], {"status": "ISSUED"})
            self.store.audit(conn, "external.paper_approved", "risk", claims)
        return token

    def _reserve(
        self,
        conn: Connection,
        record: dict[str, Any],
        token: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> None:
        claims = self._verify(token, record["id"])
        if (
            record.get("approval_id") != claims["id"]
            or claims["intent_digest"] != record["fingerprint"]
            or claims["policy_digest"] != digest(policy_dict())
            or claims["policy_version"] != POLICY.version
            or claims["snapshot_digest"] != digest(snapshot)
            or claims["quote_digest"] != digest(snapshot["quotes"])
        ):
            raise ValueError("PAPER_APPROVAL_STATE_MISMATCH")
        if (
            not datetime.fromisoformat(claims["issued_at"])
            <= self.clock()
            < datetime.fromisoformat(claims["expires_at"])
        ):
            raise ValueError("PAPER_APPROVAL_EXPIRED")
        saved = self.store.get(conn, "paper-approval-" + claims["id"], "paper-risk-approval")
        approval = self.store.state(conn, "paper-approval:" + claims["id"])
        if saved != token or approval.get("status") != "ISSUED":
            raise ValueError("PAPER_APPROVAL_ALREADY_USED")
        reservation = self.store.state(conn, "paper-account-reservation:" + self.account_id)
        if reservation:
            raise ValueError("PAPER_ACCOUNT_HAS_PENDING_ORDER")
        self._decision(
            record["intent"],
            claims["strategy_id"],
            snapshot,
            self.store.state(conn, "kill", {"halted": True}).get("halted", True),
        )
        self.store.set_state(
            conn,
            "paper-approval:" + claims["id"],
            {"status": "CONSUMED", "outbox_id": record["id"]},
        )
        self.store.set_state(
            conn,
            "paper-account-reservation:" + self.account_id,
            {"outbox_id": record["id"], "approval_id": claims["id"]},
        )
        self.store.audit(conn, "external.paper_approval_consumed", "risk", {"id": claims["id"]})

    def _release(self, identity: str, outcome: dict[str, Any]) -> dict[str, Any]:
        if outcome["status"] in {"FILLED", "CANCELLED", "REJECTED"}:
            with self.store.transaction() as conn:
                key = "paper-account-reservation:" + self.account_id
                if self.store.state(conn, key).get("outbox_id") == identity:
                    self.store.set_state(conn, key, {})
        return outcome

    def _submit(self, intent: dict[str, Any], claims: dict[str, Any]) -> dict[str, Any]:
        existing = self.broker.by_client_id(intent["client_order_id"])
        if existing is not None:
            validate_order(existing, intent)
            return existing
        # Idempotency lookup is network I/O and may consume the permission lifetime.
        with self.store.transaction() as conn:
            state = self.store.state(conn, "external-order:" + intent["client_order_id"])
            if (
                self.clock() >= datetime.fromisoformat(claims["expires_at"])
                or self.store.state(conn, "kill", {"halted": True}).get("halted", True)
                or state.get("cancel_requested")
                or state.get("status") != "SENDING"
            ):
                raise ValueError("PAPER_PERMISSION_REVOKED_BEFORE_TRANSPORT")
        result = self.broker.request("POST", "/v2/orders", json=intent)
        if not isinstance(result, dict):
            raise ValueError("BROKER_ORDER_REQUIRED")
        return result

    def deliver(self, identity: str, token: dict[str, Any]) -> dict[str, Any]:
        claims = self._verify(token, identity)
        with self.store.transaction() as conn:
            state = self.store.state(conn, "external-order:" + identity)
        snapshot = self._snapshot(claims["strategy_id"]) if state.get("status") == "QUEUED" else {}

        def risk_check(
            intent: dict[str, Any], account: dict[str, Any], positions: list[dict[str, Any]]
        ) -> bool:
            fresh = self._snapshot(claims["strategy_id"], account, positions)
            # A changed quote or holding requires a new intent and approval.
            if digest(fresh) != claims["snapshot_digest"]:
                return False
            self._decision(intent, claims["strategy_id"], fresh, False)
            return self.clock() < datetime.fromisoformat(claims["expires_at"])

        outcome = self.outbox._deliver(
            identity,
            risk_check,
            lambda conn, record: self._reserve(conn, record, token, snapshot),
            lambda intent: self._submit(intent, claims),
        )
        return self._release(identity, outcome)

    def cancel(self, identity: str, token: dict[str, Any]) -> dict[str, Any]:
        self._verify(token, identity)
        return self._release(identity, self.outbox.cancel(identity, reserve=lambda *_: None))

    def reconcile(self, identity: str, token: dict[str, Any]) -> dict[str, Any]:
        """Recover a stopped worker without ever replaying its transport request."""
        self._verify(token, identity)
        with self.store.transaction() as conn:
            state = self.store.state(conn, "external-order:" + identity)
            if state.get("status") == "SENDING":
                state["status"] = "UNKNOWN"
                self.store.set_state(conn, "external-order:" + identity, state)
                self.store.set_state(
                    conn, "kill", {"halted": True, "reason": "Paper worker recovery"}
                )
                self.store.audit(
                    conn, "external.paper_worker_recovery", "operator", {"id": identity}
                )
        return self.deliver(identity, token)
