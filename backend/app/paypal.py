"""Thin client for the PayPal REST API (sandbox): Orders v2 and Refunds."""
from __future__ import annotations

import time
import uuid

import requests

from . import config

from .policy import SUPPORTED_CURRENCIES


class PayPalError(Exception):
    pass


class PayPalClient:
    def __init__(self, client_id: str | None = None, secret: str | None = None, base: str | None = None):
        self.client_id = client_id or config.PAYPAL_CLIENT_ID
        self.secret = secret or config.PAYPAL_CLIENT_SECRET
        self.base = base or config.PAYPAL_BASE
        self._token: str | None = None
        self._token_expiry = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.secret)

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        if not self.configured:
            raise PayPalError("PayPal sandbox keys are missing. Add them to .env")
        r = requests.post(
            f"{self.base}/v1/oauth2/token",
            auth=(self.client_id, self.secret),
            data={"grant_type": "client_credentials"},
            timeout=20,
        )
        if r.status_code != 200:
            raise PayPalError(f"PayPal auth failed ({r.status_code})")
        data = r.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + int(data.get("expires_in", 3000))
        return self._token

    def _call(self, method: str, path: str, body: dict | None = None, idem_key: str | None = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": idem_key or str(uuid.uuid4()),
        }
        r = requests.request(method, f"{self.base}{path}", json=body, headers=headers, timeout=30)
        if r.status_code >= 400:
            try:
                detail = r.json()
                msg = detail.get("details", [{}])[0].get("description") or detail.get("message")
            except Exception:
                msg = r.text[:200]
            raise PayPalError(f"PayPal {r.status_code}: {msg}")
        return r.json() if r.text else {}

    def create_order(self, purchase_id: str, title: str, unit_price: float, quantity: int, currency: str) -> dict:
        if currency not in SUPPORTED_CURRENCIES:  # policy blocks this first; never silently change currency
            raise PayPalError(f"Unsupported currency {currency}")
        total = f"{unit_price * quantity:.2f}"
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": purchase_id,
                "description": title[:120],
                "custom_id": purchase_id,
                "amount": {
                    "currency_code": currency,
                    "value": total,
                    "breakdown": {"item_total": {"currency_code": currency, "value": total}},
                },
                "items": [{
                    "name": title[:120],
                    "quantity": str(quantity),
                    "unit_amount": {"currency_code": currency, "value": f"{unit_price:.2f}"},
                    "category": "PHYSICAL_GOODS",
                }],
            }],
            "payment_source": {"paypal": {"experience_context": {
                "brand_name": "Sahaya",
                "user_action": "PAY_NOW",
                "shipping_preference": "NO_SHIPPING",
                "return_url": f"{config.BACKEND_URL}/paypal/return?pid={purchase_id}",
                "cancel_url": f"{config.BACKEND_URL}/paypal/cancel?pid={purchase_id}",
            }}},
        }
        data = self._call("POST", "/v2/checkout/orders", body, idem_key=f"order-{purchase_id}")
        approve = next(
            (l["href"] for l in data.get("links", []) if l.get("rel") in ("payer-action", "approve")),
            None,
        )
        return {"order_id": data["id"], "status": data.get("status"), "approve_url": approve}

    def get_order(self, order_id: str) -> dict:
        return self._call("GET", f"/v2/checkout/orders/{order_id}")

    def capture_order(self, order_id: str) -> dict:
        data = self._call("POST", f"/v2/checkout/orders/{order_id}/capture", {}, idem_key=f"cap-{order_id}")
        capture = data["purchase_units"][0]["payments"]["captures"][0]
        return {"status": data.get("status"), "capture_id": capture["id"], "capture_status": capture.get("status")}

    def refund_capture(self, capture_id: str, note: str = "Refund requested by customer") -> dict:
        data = self._call(
            "POST",
            f"/v2/payments/captures/{capture_id}/refund",
            {"note_to_payer": note[:255]},
            idem_key=f"refund-{capture_id}",
        )
        return {"refund_id": data.get("id"), "status": data.get("status")}
