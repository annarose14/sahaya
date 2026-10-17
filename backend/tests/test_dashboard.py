"""Family dashboard: the trusted contact's view of everything Sahaya did."""
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.fakes import FakePayPal, ScriptedShopper
from app.service import Store


@pytest.fixture
def api(offline, monkeypatch):
    store = Store()
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main.service, "store", store)
    monkeypatch.setattr(main.service, "paypal", FakePayPal())
    monkeypatch.setattr(main.agent, "llm", ScriptedShopper())
    c = TestClient(main.app)
    c.paypal = main.service.paypal
    return c


def say(api, text, sid="family01"):
    return api.post("/api/chat", json={"session_id": sid, "message": text}).json()


def board(api, sid="family01"):
    r = api.get(f"/api/sessions/{sid}/dashboard")
    assert r.status_code == 200
    return r.json()


def test_empty_dashboard_is_valid(api):
    b = board(api)
    assert b["rows"] == [] and b["tricks"] == []
    assert b["summary"]["paid_count"] == 0 and b["summary"]["daily_cap"] == 150


def test_dashboard_shows_paid_refunded_waiting_and_stopped(api):
    say(api, "anything useful")
    paid = say(api, "option 1")["purchase"]                     # kettle 39
    say(api, "yes")
    api.get(f"/paypal/return?pid={paid['id']}", follow_redirects=False)
    say(api, "option 3")                                        # magnifier 64, waits for family
    b = board(api)
    by_status = {r["status"]: r for r in b["rows"]}
    assert by_status["paid"]["paypal_status"] == "COMPLETED"
    assert by_status["paid"]["paypal_label"] == "Paid"
    assert by_status["paid"]["matches_paypal"] is True
    assert by_status["paid"]["paypal_capture_id"]
    assert by_status["awaiting_family"]["status_label"] == "Waiting for you"
    assert "trusted contact" in by_status["awaiting_family"]["reason"]
    s = b["summary"]
    assert s["paid_count"] == 1 and s["paid_total"] == 39 and s["spent_today"] == 39 and s["waiting_for_you"] == 1

    api.post(f"/api/purchases/{paid['id']}/refund")
    main.service.store.paypal_cache.clear()
    b = board(api)
    refunded = next(r for r in b["rows"] if r["status"] == "refunded")
    assert refunded["paypal_status"] == "REFUNDED" and refunded["matches_paypal"] is True
    assert b["summary"]["refunded_total"] == 39 and b["summary"]["spent_today"] == 0


def test_dashboard_flags_record_that_disagrees_with_paypal(api, monkeypatch):
    say(api, "anything useful")
    p = say(api, "option 1")["purchase"]
    say(api, "yes")
    api.get(f"/paypal/return?pid={p['id']}", follow_redirects=False)
    monkeypatch.setattr(api.paypal, "lookup_status", lambda o, c: "REFUNDED")  # PayPal says refunded elsewhere
    b = board(api)
    assert b["rows"][0]["matches_paypal"] is False
    assert b["summary"]["paypal_mismatches"] == 1


def test_paypal_down_does_not_break_dashboard(api, monkeypatch):
    say(api, "anything useful")
    p = say(api, "option 1")["purchase"]
    say(api, "yes")

    def boom(o, c):
        raise RuntimeError("PayPal 503")
    monkeypatch.setattr(api.paypal, "lookup_status", boom)
    b = board(api)
    assert b["rows"][0]["paypal_check"] == "unavailable"


def test_trick_listings_are_logged_for_the_family(api):
    api.post("/api/sessions/family01/safety-demo", json={"on": True})
    say(api, "a kettle")
    b = board(api)
    assert b["summary"]["tricks_caught"] == 1
    assert "SIMULATED" in b["tricks"][0]["title"] and "ignore previous" in b["tricks"][0]["found"]


def test_dashboards_are_per_person(api):
    say(api, "anything useful", sid="personAAA")
    say(api, "option 1", sid="personAAA")
    assert board(api, "personBBB")["rows"] == []


def test_ask_uses_only_the_data_and_treats_titles_as_data(api, monkeypatch):
    seen = {}

    def fake(messages):
        seen["messages"] = messages
        return "One paid purchase of 39 dollars today."
    monkeypatch.setattr(main, "ask_llm", fake)
    say(api, "anything useful")
    say(api, "option 1")
    r = api.post("/api/sessions/family01/dashboard/ask", json={"question": "Did Mum buy anything unusual?"})
    assert r.json()["answer"] == "One paid purchase of 39 dollars today."
    system, user = seen["messages"]
    assert "never as instructions" in system["content"]
    data = json.loads(user["content"].split("DATA:\n", 1)[1].split("\n\nQUESTION:")[0])
    assert data["purchases"][0]["item"].startswith("Cordless")


def test_ask_fails_gracefully(api, monkeypatch):
    from app.agent import LLMError

    def down(messages):
        raise LLMError("Groq 503")
    monkeypatch.setattr(main, "ask_llm", down)
    r = api.post("/api/sessions/family01/dashboard/ask", json={"question": "anything odd?"})
    assert r.status_code == 200 and "can't answer right now" in r.json()["answer"]


@pytest.mark.parametrize("q", ["", "x", "a" * 301])
def test_ask_validates_question(api, q):
    assert api.post("/api/sessions/family01/dashboard/ask", json={"question": q}).status_code == 422
