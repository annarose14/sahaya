"""Purchase lifecycle. This is the only code path that can move money.

proposed ──policy──► blocked
                 ├─► awaiting_family ──family yes──► awaiting_confirm
                 │                   └─family no───► declined
                 └─► awaiting_confirm ──user yes──► awaiting_paypal ──PayPal approve──► paid ──► refunded
                                      └─user no───► cancelled
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import date

from . import config, policy
from .paypal import PayPalClient


class FlowError(Exception):
    pass


class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.purchases: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}
        self.spend: dict[str, float] = {}

    def session(self, sid: str) -> dict:
        return self.sessions.setdefault(sid, {"messages": [], "products": {}, "trace": []})

    def spent_today(self, sid: str) -> float:
        return self.spend.get(f"{sid}:{date.today().isoformat()}", 0.0)

    def add_spend(self, sid: str, amount: float):
        key = f"{sid}:{date.today().isoformat()}"
        self.spend[key] = round(self.spend.get(key, 0.0) + amount, 2)


def settings() -> policy.Settings:
    return policy.Settings(
        daily_cap=config.DAILY_SPEND_CAP,
        family_over=config.FAMILY_APPROVAL_OVER,
        max_qty=config.MAX_QUANTITY,
        price_guard_ratio=config.PRICE_GUARD_RATIO,
    )


class PurchaseService:
    def __init__(self, store: Store, paypal: PayPalClient):
        self.store = store
        self.paypal = paypal

    def trace(self, sid: str, step: str, detail: str):
        self.store.session(sid)["trace"].append({"t": time.time(), "step": step, "detail": detail})

    def get(self, pid: str) -> dict:
        p = self.store.purchases.get(pid)
        if not p:
            raise FlowError("Purchase not found")
        return p

    def public(self, p: dict) -> dict:
        return {k: v for k, v in p.items() if not k.startswith("_")}

    def propose(self, sid: str, product_id: str, quantity: int) -> dict:
        product = self.store.session(sid)["products"].get(product_id)
        if not product:
            raise FlowError("That product is not in the latest search results.")
        # Only one purchase waits at a time, so a later "yes" can never pay for an older forgotten one.
        for old in self.list_for(sid):
            if old["status"] in ("awaiting_confirm", "awaiting_family"):
                old["status"] = "cancelled"
                self.trace(sid, "cancel", f"{old['id']} replaced by a new choice")
        decision = policy.evaluate(product, quantity, self.store.spent_today(sid), settings())
        status = {
            policy.ALLOW: "awaiting_confirm",
            policy.NEEDS_FAMILY: "awaiting_family",
            policy.BLOCK: "blocked",
        }[decision.outcome]
        pid = uuid.uuid4().hex[:10]
        purchase = {
            "id": pid,
            "session_id": sid,
            "product": product,
            "quantity": quantity,
            "total": decision.total,
            "currency": product["currency"],
            "status": status,
            "decision": decision.to_dict(),
            "approve_url": None,
            "order_id": None,
            "capture_id": None,
            "refund_id": None,
            "created": time.time(),
        }
        self.store.purchases[pid] = purchase
        self.trace(sid, "policy", f"{product['title'][:50]}: {decision.outcome} ({', '.join(decision.reasons) or 'all checks passed'})")
        return purchase

    def family_decide(self, pid: str, approve: bool) -> dict:
        p = self.get(pid)
        if p["status"] != "awaiting_family":
            raise FlowError(f"Purchase is {p['status']}, not waiting for family")
        p["status"] = "awaiting_confirm" if approve else "declined"
        self.trace(p["session_id"], "family", "approved" if approve else "declined")
        return p

    def cancel(self, pid: str) -> dict:
        p = self.get(pid)
        if p["status"] not in ("awaiting_confirm", "awaiting_family", "awaiting_paypal"):
            raise FlowError(f"Purchase is {p['status']} and can't be cancelled")
        p["status"] = "cancelled"
        self.trace(p["session_id"], "cancel", pid)
        return p

    def confirm(self, pid: str) -> dict:
        """The user said yes. Only now does PayPal get involved."""
        with self.store.lock:
            p = self.get(pid)
            if p["status"] == "awaiting_paypal":
                return p
            if p["status"] != "awaiting_confirm":
                raise FlowError(f"Purchase is {p['status']} and can't be confirmed")
            # Re-check the cap at payment time, in case other buys happened meanwhile.
            again = policy.evaluate(p["product"], p["quantity"], self.store.spent_today(p["session_id"]), settings())
            if again.outcome == policy.BLOCK:
                p["status"] = "blocked"
                p["decision"] = again.to_dict()
                return p
            order = self.paypal.create_order(pid, p["product"]["title"], p["product"]["price"], p["quantity"], p["currency"])
            p.update(order_id=order["order_id"], approve_url=order["approve_url"], status="awaiting_paypal")
        self.trace(p["session_id"], "paypal", f"order {order['order_id']} created")
        return p

    def complete(self, pid: str) -> dict:
        """Called when the buyer returns from PayPal approval."""
        with self.store.lock:
            p = self.get(pid)
            if p["status"] == "paid":
                return p
            if p["status"] != "awaiting_paypal":
                raise FlowError(f"Purchase is {p['status']}")
            cap = self.paypal.capture_order(p["order_id"])
            if cap["capture_status"] not in ("COMPLETED", "PENDING"):
                raise FlowError(f"Capture status {cap['capture_status']}")
            p.update(status="paid", capture_id=cap["capture_id"])
            self.store.add_spend(p["session_id"], p["total"])
        self.trace(p["session_id"], "paypal", f"captured {cap['capture_id']}")
        return p

    def refund(self, pid: str) -> dict:
        with self.store.lock:
            p = self.get(pid)
            if p["status"] == "refunded":
                return p
            if p["status"] != "paid":
                raise FlowError("Only paid purchases can be refunded")
            r = self.paypal.refund_capture(p["capture_id"])
            p.update(status="refunded", refund_id=r["refund_id"])
            self.store.add_spend(p["session_id"], -p["total"])
        self.trace(p["session_id"], "paypal", f"refund {r['refund_id']}")
        return p

    def pending(self, sid: str) -> dict | None:
        """The newest purchase still waiting on the person or their trusted contact."""
        for p in self.list_for(sid):
            if p["status"] in ("awaiting_confirm", "awaiting_family", "awaiting_paypal"):
                return p
        return None

    def list_for(self, sid: str) -> list[dict]:
        return sorted(
            (p for p in self.store.purchases.values() if p["session_id"] == sid),
            key=lambda p: p["created"], reverse=True,
        )
