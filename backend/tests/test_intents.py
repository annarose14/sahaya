"""Yes and no detection for pending payments. Typos, politeness and hedges."""
import pytest

from app.intents import is_no, is_yes


@pytest.mark.parametrize("text", [
    "yes", "Yes", "YES!", "yes.", "yes please", "Yes, please", "yeah", "yep", "yup", "yea", "ya",
    "yse", "yess", "sure", "ok", "okay", "OK then", "go ahead", "do it", "pay", "pay now", "confirm",
    "yes go ahead", "yeah sure", "yes pay it", "Yes Sahaya", "absolutely", "that's right", "  yes  ",
])
def test_clear_yes(text):
    assert is_yes(text)
    assert not is_no(text)


@pytest.mark.parametrize("text", [
    "no", "No.", "NO", "nope", "nah", "cancel", "Cancel it", "stop", "don't", "dont buy it",
    "not now", "never mind", "nevermind", "forget it", "no thanks", "no thank you",
])
def test_clear_no(text):
    assert is_no(text)
    assert not is_yes(text)


@pytest.mark.parametrize("text", [
    # hedged or changed minds must NOT pay
    "yes but cheaper", "yes, but wait", "yeah the other one", "ok what about option 2",
    "sure, tell me more", "yes the second one", "maybe", "hmm", "how much is shipping",
    "yes I want a different colour", "ok but is it loud enough", "wait",
    # long sentences go to the AI
    "yes I think that sounds like a good one for my grandmother",
    # not answers at all
    "", "   ", "...", "a talking clock", "option 1", "123",
    # sounds like yes but isn't
    "yesterday", "okra", "surely not", "paying is hard",
])
def test_not_a_clear_yes(text):
    assert not is_yes(text)


@pytest.mark.parametrize("text", [
    "no, the second one", "no the other one", "no, something cheaper", "no I want option 2 instead",
    "note this", "nobody", "know more",
])
def test_not_a_plain_no(text):
    assert not is_no(text)
