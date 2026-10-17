"""End to end tests through the HTTP API, written like a tester walking through real journeys.

The model is scripted and PayPal is faked, so these run offline in under a second,
but every request goes through the same FastAPI routes the browser uses.
"""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import FALLBACK_REPLY, LLMError
from app.service import Store

from app.fakes import FakePayPal, ScriptedShopper

ORIGIN = "http://localhost:5173"


@pytest.fixture
def api(offline, monkeypatch):
    store = Store()
    paypal = FakePayPal()
    shopper = ScriptedShopper()
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main.service, "store", store)
    monkeypatch.setattr(main.service, "paypal", paypal)
    monkeypatch.setattr(main.agent, "llm", shopper)
    client = TestClient(main.app)
    client.paypal, client.shopper = paypal, shopper
    return client


def say(api, text, sid="tester01"):
    r = api.post("/api/chat", json={"session_id": sid, "message": text})
    assert r.status_code == 200, r.text
    return r.json()


def shop_to_ready(api, option=1, sid="tester01"):
    """Search 'anything' (all three demo products: kettle 39, clock 24.50, magnifier 64) and pick one."""
    first = say(api, "anything useful", sid)
    assert [p["title"][:7] for p in first["products"]] == ["Cordles", "Talking", "LED han"]
    return say(api, f"option {option}", sid)["purchase"]


# ---------- basics ----------

def test_health_reports_config_and_rules(api):
    body = api.get("/api/health").json()
    assert body["ok"] is True
    assert body["rules"] == {"daily_spend_cap": 150.0, "family_approval_over": 50.0, "max_quantity": 5}


@pytest.mark.parametrize("payload", [
    {"session_id": "abc", "message": "hi"},              # session id too short
    {"session_id": "x" * 65, "message": "hi"},           # session id too long
    {"session_id": "tester01", "message": ""},           # empty message
    {"session_id": "tester01", "message": "a" * 2001},   # too long
    {"session_id": "tester01"},                          # missing message
    {},
])
def test_bad_chat_input_is_rejected_cleanly(api, payload):
    assert api.post("/api/chat", json=payload).status_code == 422


def test_unicode_and_emoji_messages_work(api):
    out = say(api, "Ich brauche eine Uhr ⏰ für Oma, s'il vous plaît")
    assert out["reply"]


def test_unknown_purchase_is_404_not_500(api):
    assert api.get("/api/purchases/nope").status_code == 404
    assert api.post("/api/purchases/nope/confirm").status_code == 404
    assert api.post("/api/purchases/nope/refund").status_code == 404


def test_errors_still_carry_cors_header_so_browser_can_read_them(api):
    r = api.get("/api/purchases/nope", headers={"Origin": ORIGIN})
    assert r.headers.get("access-control-allow-origin") == ORIGIN


# ---------- the happy path ----------

def test_full_journey_search_pick_yes_pay_refund(api):
    p = shop_to_ready(api, option=1)
    assert p["status"] == "awaiting_confirm" and p["total"] == 39.0
    assert api.paypal.orders == []                        # nothing created before the yes

    llm_calls_before = api.shopper.calls
    out = say(api, "yes")
    assert api.shopper.calls == llm_calls_before          # the AI was not asked; plain code handled it
    assert out["purchase"]["status"] == "awaiting_paypal"
    assert out["purchase"]["approve_url"].startswith("https://pp.test/")
    assert len(api.paypal.orders) == 1

    r = api.get(f"/paypal/return?pid={p['id']}", follow_redirects=False)
    assert r.status_code == 307 and "result=paid" in r.headers["location"]
    assert api.get(f"/api/purchases/{p['id']}").json()["status"] == "paid"

    r = api.post(f"/api/purchases/{p['id']}/refund")
    assert r.json()["status"] == "refunded"
    assert api.post(f"/api/purchases/{p['id']}/refund").json()["status"] == "refunded"  # twice is safe
    assert len(api.paypal.refunds) == 1


def test_clicking_pay_twice_creates_one_order(api):
    p = shop_to_ready(api)
    api.post(f"/api/purchases/{p['id']}/confirm")
    api.post(f"/api/purchases/{p['id']}/confirm")
    say(api, "yes")
    assert len(api.paypal.orders) == 1


def test_paypal_return_twice_captures_once(api):
    p = shop_to_ready(api)
    say(api, "yes")
    api.get(f"/paypal/return?pid={p['id']}", follow_redirects=False)
    api.get(f"/paypal/return?pid={p['id']}", follow_redirects=False)
    assert len(api.paypal.captures) == 1


# ---------- yes, no and everything in between ----------

@pytest.mark.parametrize("answer", ["Yes!", "yse", "yeah sure", "ok", "go ahead", "Yes please Sahaya"])
def test_typos_and_polite_yes_pay(api, answer):
    shop_to_ready(api)
    assert say(api, answer)["purchase"]["status"] == "awaiting_paypal"


@pytest.mark.parametrize("answer", ["no", "No thanks", "nope", "cancel", "never mind", "not now"])
def test_no_cancels_and_nothing_is_paid(api, answer):
    shop_to_ready(api)
    out = say(api, answer)
    assert out["purchase"]["status"] == "cancelled"
    assert "Nothing was paid" in out["reply"]
    assert api.paypal.orders == []


@pytest.mark.parametrize("answer", ["yes but cheaper", "ok what about option 2", "wait", "hmm"])
def test_hedged_answers_never_pay(api, answer):
    shop_to_ready(api)
    say(api, answer)
    assert api.paypal.orders == []


def test_yes_with_nothing_pending_goes_to_the_ai(api):
    before = api.shopper.calls
    say(api, "yes")
    assert api.shopper.calls > before
    assert api.paypal.orders == []


def test_changing_choice_cancels_the_old_one(api):
    old = shop_to_ready(api, option=1)
    new = say(api, "option 2")["purchase"]
    assert api.get(f"/api/purchases/{old['id']}").json()["status"] == "cancelled"
    say(api, "yes")
    assert api.paypal.orders[0][0] == new["id"]   # only the newest choice was paid


def test_changed_my_mind_via_ai_cancels(api):
    shop_to_ready(api)
    out = say(api, "actually I changed my mind")
    assert out["purchase"]["status"] == "cancelled"


# ---------- trusted contact ----------

def test_family_approval_flow(api):
    p = shop_to_ready(api, option=3)                      # magnifier, 64 dollars
    assert p["status"] == "awaiting_family"

    out = say(api, "yes")                                 # yes before family answers must not pay
    assert "still waiting" in out["reply"] and api.paypal.orders == []

    assert api.post(f"/api/purchases/{p['id']}/family", json={"approve": True}).json()["status"] == "awaiting_confirm"
    assert say(api, "yes")["purchase"]["status"] == "awaiting_paypal"


def test_family_decline_stops_it(api):
    p = shop_to_ready(api, option=3)
    api.post(f"/api/purchases/{p['id']}/family", json={"approve": False})
    say(api, "yes")
    assert api.paypal.orders == []
    assert api.post(f"/api/purchases/{p['id']}/family", json={"approve": True}).status_code == 409


def test_family_bad_body_is_422(api):
    p = shop_to_ready(api, option=3)
    assert api.post(f"/api/purchases/{p['id']}/family", json={"approve": "maybe"}).status_code == 422


# ---------- limits ----------

def test_daily_cap_counts_paid_orders_and_refunds_give_it_back(api, monkeypatch):
    monkeypatch.setattr(main.config, "DAILY_SPEND_CAP", 70)
    p = shop_to_ready(api, option=1)                      # 39 dollars
    say(api, "yes")
    api.get(f"/paypal/return?pid={p['id']}", follow_redirects=False)
    second = say(api, "option 1")["purchase"]             # another 39 would make 78 > 70
    assert second["status"] == "blocked"
    api.post(f"/api/purchases/{p['id']}/refund")
    third = say(api, "option 1")["purchase"]
    assert third["status"] == "awaiting_confirm"


def test_five_at_once_needs_family_and_six_is_blocked(api):
    say(api, "anything useful")
    assert say(api, "option 2, five of them")["purchase"]["status"] == "awaiting_family"  # 5 x 24.50 = 122.50


# ---------- failures ----------

def test_paypal_down_gives_friendly_reply_and_keeps_purchase(api):
    p = shop_to_ready(api)
    api.paypal.fail_next = True
    out = say(api, "yes")
    assert "Nothing was paid" in out["reply"]
    assert api.get(f"/api/purchases/{p['id']}").json()["status"] == "awaiting_confirm"
    assert say(api, "yes")["purchase"]["status"] == "awaiting_paypal"   # works on retry


def test_ai_down_gives_friendly_reply(api, monkeypatch):
    def down(msgs):
        raise LLMError("Groq 503")
    monkeypatch.setattr(main.agent, "llm", down)
    assert say(api, "a kettle")["reply"] == FALLBACK_REPLY


def test_paypal_return_for_unknown_purchase_shows_error_page(api):
    r = api.get("/paypal/return?pid=ghost", follow_redirects=False)
    assert r.status_code == 307 and "result=error" in r.headers["location"]


def test_paypal_cancel_link_cancels(api):
    p = shop_to_ready(api)
    say(api, "yes")
    r = api.get(f"/paypal/cancel?pid={p['id']}", follow_redirects=False)
    assert "result=cancelled" in r.headers["location"]
    assert api.get(f"/api/purchases/{p['id']}").json()["status"] == "cancelled"


# ---------- safety demo ----------

def test_safety_demo_listing_is_caught_and_never_shown(api):
    api.post("/api/sessions/tester01/safety-demo", json={"on": True})
    out = say(api, "a kettle")
    assert out["ignored"] and "SIMULATED" in out["ignored"][0]["title"]
    assert not any(p.get("simulated") for p in out["products"])
    trace = api.get("/api/sessions/tester01/trace").json()
    assert any(t["step"] == "blocked" for t in trace)


def test_sessions_are_isolated(api):
    shop_to_ready(api, sid="personAAA")
    out = say(api, "yes", sid="personBBB")                # someone else's yes
    assert api.paypal.orders == []
    assert out["purchase"] is None
