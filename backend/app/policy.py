"""Deterministic money rules.

The AI can only PROPOSE a purchase. Everything in this file decides whether
that proposal may go ahead. No LLM output is trusted here.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

SUPPORTED_CURRENCIES = {"AUD", "USD", "GBP", "EUR", "CAD", "NZD"}

ALLOW = "allow"
NEEDS_FAMILY = "needs_family"
BLOCK = "block"

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+instructions",
    r"disregard\s+(all\s+|any\s+)?(previous|prior|your)\s+",
    r"\b(system|developer)\s+prompt\b",
    r"\b(assistant|ai|agent|bot)\b[^.]{0,40}\b(buy|purchase|order|checkout|add to cart)\b",
    r"\byou\s+(must|should|need to)\s+(buy|purchase|order)\b",
    r"\bbuy\s+(\d+|five|ten|several|all)\s+(of\s+)?(these|this|them)\b",
    r"\bapprove\s+(this\s+)?(payment|purchase|order)\b",
    r"\bskip\s+(the\s+)?(confirmation|approval|check)",
    r"<\s*/?\s*(system|instructions?)\s*>",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def scan_untrusted(text: str) -> list[str]:
    """Return the suspicious phrases found in seller written text."""
    if not text:
        return []
    hits = []
    for rx in _INJECTION_RE:
        m = rx.search(text)
        if m:
            hits.append(m.group(0).strip())
    return hits


def untrusted_text(product: dict) -> str:
    """All seller written text for one product."""
    parts = [str(product.get("title", "")), str(product.get("description", ""))]
    parts += [str(f) for f in product.get("features") or []]
    return " ".join(parts)


@dataclass
class Settings:
    daily_cap: float
    family_over: float
    max_qty: int
    price_guard_ratio: float


@dataclass
class Decision:
    outcome: str
    total: float
    reasons: list[str] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "total": round(self.total, 2),
            "reasons": self.reasons,
            "checks": self.checks,
        }


def evaluate(product: dict, quantity: int, spent_today: float, s: Settings) -> Decision:
    """Decide ALLOW, NEEDS_FAMILY or BLOCK for one proposed purchase."""
    checks: list[dict] = []
    block: list[str] = []
    family: list[str] = []

    def check(name: str, ok: bool, detail: str):
        checks.append({"check": name, "passed": ok, "detail": detail})

    price = product.get("price")
    valid_price = isinstance(price, (int, float)) and price > 0
    check("price_known", valid_price, f"price {price}")
    if not valid_price:
        block.append("I couldn't confirm the price of this item.")
        return Decision(BLOCK, 0.0, block, checks)

    currency = str(product.get("currency", "")).upper()
    cur_ok = currency in SUPPORTED_CURRENCIES
    check("currency", cur_ok, currency or "unknown")
    if not cur_ok:
        block.append("I can't pay in that currency safely, so I won't buy this one.")

    qty_ok = isinstance(quantity, int) and not isinstance(quantity, bool) and 1 <= quantity <= s.max_qty
    check("quantity", qty_ok, f"{quantity} (max {s.max_qty})")
    if not qty_ok:
        block.append(f"Quantity must be between 1 and {s.max_qty}.")

    total = round(float(price) * (quantity if qty_ok else 1), 2)

    flags = scan_untrusted(untrusted_text(product))
    check("listing_safe", not flags, "; ".join(flags) or "no instructions found in listing")
    if flags:
        block.append("This listing contains hidden instructions aimed at me, so I won't buy it.")

    within_cap = spent_today + total <= s.daily_cap
    check("daily_cap", within_cap, f"{spent_today:.2f} spent + {total:.2f} vs cap {s.daily_cap:.2f}")
    if not within_cap:
        block.append(f"This would go over your daily limit of {s.daily_cap:.0f} dollars.")

    def _clean(xs):
        return [x for x in xs or [] if isinstance(x, (int, float)) and x > 0]

    shops = _clean(product.get("other_prices"))
    peers = _clean(product.get("peer_prices"))
    if len(shops) >= 2:
        basis, median, where = "shops", statistics.median(shops), "other shops selling the same item"
    elif len(peers) >= 3:
        basis, median, where = "similar items", statistics.median(peers), "similar items I found"
    else:
        basis, median, where = None, None, None
    if basis:
        fair = price <= median * s.price_guard_ratio
        check("fair_price", fair, f"{price:.2f} vs typical {median:.2f} ({basis})")
        if not fair:
            pct = round((price / median - 1) * 100)
            family.append(f"This price is about {pct} percent higher than {where}.")
    else:
        check("fair_price", True, "not enough prices to compare")

    under_family = total <= s.family_over
    check("family_threshold", under_family, f"{total:.2f} vs {s.family_over:.2f}")
    if not under_family:
        family.append(f"It costs more than {s.family_over:.0f} dollars, so your trusted contact needs to approve.")

    if block:
        return Decision(BLOCK, total, block, checks)
    if family:
        return Decision(NEEDS_FAMILY, total, family, checks)
    return Decision(ALLOW, total, [], checks)
