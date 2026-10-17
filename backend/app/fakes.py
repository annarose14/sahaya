"""Offline stand-ins for PayPal and the AI model.

Used by the test suite, and by SAHAYA_FAKE=1 mode so the whole app (including the
browser UI tests) can run with no keys and no network. Never used in production.
"""
from __future__ import annotations

import json


def call(cid, name, args):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class FakePayPal:
    """Stands in for the PayPal sandbox. Records every call so tests can prove what moved."""
    configured = True

    def __init__(self, approve_base: str = "https://pp.test"):
        self.orders, self.captures, self.refunds = [], [], []
        self.fail_next = False
        self.approve_base = approve_base

    def create_order(self, pid, title, price, qty, currency):
        if self.fail_next:
            self.fail_next = False
            from app.paypal import PayPalError
            raise PayPalError("PayPal 503: service unavailable")
        self.orders.append((pid, round(price * qty, 2), currency))
        return {"order_id": f"O-{pid}", "status": "PAYER_ACTION_REQUIRED", "approve_url": f"{self.approve_base}/{pid}"}

    def capture_order(self, order_id):
        self.captures.append(order_id)
        return {"status": "COMPLETED", "capture_id": f"C-{order_id}", "capture_status": "COMPLETED"}

    def lookup_status(self, order_id, capture_id):
        if capture_id:
            return "REFUNDED" if capture_id in self.refunds else "COMPLETED"
        if order_id:
            return "PAYER_ACTION_REQUIRED"
        return None

    def refund_capture(self, capture_id):
        self.refunds.append(capture_id)
        return {"refund_id": f"R-{capture_id}", "status": "COMPLETED"}


class ScriptedShopper:
    """A fake model that behaves like a well behaved LLM, so whole conversations can be tested
    without network. It searches for what was asked, shows the first three safe results,
    proposes the option number the person says, and records every call."""

    def __init__(self):
        self.calls = 0
        self.n = 0

    def __call__(self, msgs):
        self.calls += 1
        self.n += 1
        last = msgs[-1]
        if last["role"] == "user":
            text = last["content"].lower()
            for word, num in (("1", 1), ("one", 1), ("first", 1), ("2", 2), ("two", 2), ("second", 2),
                              ("3", 3), ("three", 3), ("third", 3)):
                if f"option {word}" in text or f"the {word}" in text:
                    qty = 5 if "five" in text else 1
                    return {"tool_calls": [call(f"c{self.n}", "propose_purchase", {"option": num, "quantity": qty})]}
            if "changed my mind" in text:
                return {"tool_calls": [call(f"c{self.n}", "cancel_pending", {})]}
            if "past orders" in text:
                return {"tool_calls": [call(f"c{self.n}", "list_purchases", {})]}
            return {"tool_calls": [call(f"c{self.n}", "search_products", {"query": last["content"]})]}
        if last["role"] == "tool":
            data = json.loads(last["content"].split(" ...(trimmed)")[0]) if "trimmed" not in last["content"] else {}
            if "candidates" in data:
                ids = [c["id"] for c in data["candidates"] if not c["listing_flagged"]][:3]
                return {"tool_calls": [call(f"c{self.n}", "present_options", {"product_ids": ids})]}
            if "options" in data:
                return {"content": " ".join(f"Option {o['option']}, {o['title']}, {o['price']} dollars."
                                            for o in data["options"])}
            if "status" in data and "purchase_id" in data:
                return {"content": f"Status {data['status']}. Say yes to pay with PayPal, or no to cancel."}
            return {"content": "Okay."}
        return {"content": "Okay."}
