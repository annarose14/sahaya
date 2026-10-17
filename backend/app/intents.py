"""Yes and no answers to a pending payment, decided by plain code.

The AI never confirms a payment. When a purchase is waiting for the person's
answer, a short clear "yes" pays and a short clear "no" cancels. Anything
hedged ("yes but cheaper", "wait") or long goes to the AI as normal talk, so a
half sentence can never move money.
"""
from __future__ import annotations

import re

_YES = {
    "yes", "yeah", "yep", "yup", "ya", "yea", "yess", "yes please", "yse", "yas", "ye",
    "sure", "ok", "okay", "confirm", "pay", "pay now", "buy", "buy it", "go ahead", "do it",
    "please do", "absolutely", "correct", "that's right", "thats right",
}
_NO = {
    "no", "nope", "nah", "na", "noo", "cancel", "stop", "don't", "dont", "do not", "not now",
    "never mind", "nevermind", "forget it", "no thanks", "no thank you", "cancel it", "cancel that",
}
_HEDGE = re.compile(
    r"\b(but|wait|hold on|cheaper|other|another|instead|change|different|more|less|tell|what|which|how|why|"
    r"maybe|later|not sure|second|first|third|option|two|three)\b"
)
_FILLER = re.compile(r"\b(please|thanks|thank you|sahaya|then|now|go|let's|lets|it|that)\b")


def _clean(text: str) -> str:
    t = text.lower().replace("’", "'")
    t = re.sub(r"[^a-z' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _matches(t: str, words: set[str]) -> bool:
    if t in words:
        return True
    first_two = " ".join(t.split()[:2])
    first = t.split()[0] if t else ""
    return first_two in words or first in words


def is_yes(text: str) -> bool:
    t = _clean(text)
    if not t or len(t.split()) > 6 or _HEDGE.search(t) or is_no(text):
        return False
    return _matches(t, _YES) or _matches(_FILLER.sub(" ", t).strip(), _YES)


def is_no(text: str) -> bool:
    t = _clean(text)
    if not t or len(t.split()) > 5:
        return False
    if _matches(t, _NO):
        # "no, the second one" is a change of mind, not a plain no: let the AI handle it
        return not re.search(r"\b(other|another|second|first|third|option|instead|cheaper|different)\b", t)
    return False
