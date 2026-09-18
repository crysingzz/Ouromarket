"""Fixed paper-only Alpaca REST adapter with idempotent recovery and bounded I/O."""

import json
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx

PAPER_ORIGIN = "https://paper-api.alpaca.markets"
TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced"}
ACTIVE = {
    "new",
    "accepted",
    "pending_new",
    "partially_filled",
    "pending_cancel",
    "pending_replace",
    "accepted_for_bidding",
    "stopped",
    "suspended",
    "calculated",
}


def validate_order(order: dict[str, Any], intent: dict[str, Any]) -> None:
    """Bind every broker observation to the original immutable order."""
    for key in ("client_order_id", "symbol", "side", "type", "time_in_force"):
        if order.get(key) != intent[key]:
            raise ValueError("BROKER_IDEMPOTENCY_CONFLICT")
    quantity = Decimal(str(order.get("qty")))
    if not quantity.is_finite() or quantity != Decimal(str(intent["qty"])):
        raise ValueError("BROKER_IDEMPOTENCY_CONFLICT")
    if not isinstance(order.get("id"), str) or not order["id"]:
        raise ValueError("BROKER_ORDER_ID_REQUIRED")
    if order.get("status") not in ACTIVE | TERMINAL:
        raise ValueError("UNKNOWN_BROKER_STATUS")


class AlpacaPaper:
    def __init__(self, key: str, secret: str, client: httpx.Client):
        if not key or not secret:
            raise ValueError("PAPER_BROKER_CREDENTIALS_REQUIRED")
        self.client = client
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        # No configurable origin, redirects, arbitrary URLs, or live endpoint.
        with self.client.stream(
            method, PAPER_ORIGIN + path, headers=self.headers, follow_redirects=False, **kwargs
        ) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 2_000_000:
                    raise ValueError("BROKER_RESPONSE_TOO_LARGE")
            return json.loads(data) if data else None

    def account(self) -> dict[str, Any]:
        value = self.request("GET", "/v2/account")
        if not isinstance(value, dict):
            raise ValueError("BROKER_ACCOUNT_REQUIRED")
        return value

    def positions(self) -> list[dict[str, Any]]:
        value = self.request("GET", "/v2/positions")
        if not isinstance(value, list):
            raise ValueError("BROKER_POSITIONS_REQUIRED")
        return value

    def by_client_id(self, client_id: str) -> dict[str, Any] | None:
        try:
            value = self.request(
                "GET", "/v2/orders:by_client_order_id", params={"client_order_id": client_id}
            )
            if not isinstance(value, dict):
                raise ValueError("BROKER_ORDER_REQUIRED")
            return value
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    def submit(self, intent: dict[str, Any]) -> dict[str, Any]:
        existing = self.by_client_id(intent["client_order_id"])
        if existing:
            validate_order(existing, intent)
            return existing
        value = self.request("POST", "/v2/orders", json=intent)
        if not isinstance(value, dict):
            raise ValueError("BROKER_ORDER_REQUIRED")
        return value

    def cancel(self, broker_id: str) -> None:
        self.request("DELETE", "/v2/orders/" + quote(broker_id, safe=""))
