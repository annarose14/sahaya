"""Sahaya API."""
from __future__ import annotations

import json
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import config, dashboard
from .agent import Agent, LLMError, llm_text
from .paypal import PayPalClient, PayPalError
from .service import FlowError, PurchaseService, Store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sahaya")

app = FastAPI(title="Sahaya API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_URL, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = Store()
service = PurchaseService(store, PayPalClient())
agent = Agent(service)
ask_llm = llm_text  # model for family dashboard questions; tests and fake mode swap it

if os.getenv("SAHAYA_FAKE") == "1":
    # Offline mode for UI tests and demos without keys: fake PayPal, scripted AI, demo catalog.
    from .fakes import FakePayPal, ScriptedShopper

    config.CHANNEL3_API_KEY = ""
    config.GROQ_API_KEY = "fake"
    service.paypal = FakePayPal(approve_base=f"{config.BACKEND_URL}/fake-paypal")
    agent.llm = ScriptedShopper()

    def ask_llm(messages):  # noqa: F811  (fake mode: no model, answer from the numbers)
        data = json.loads(messages[-1]["content"].split("DATA:\n", 1)[1].split("\n\nQUESTION:")[0])
        s = data["summary"]
        return (f"{s['paid_count']} paid purchase(s) totalling {s['paid_total']:g} dollars today. "
                f"Sahaya stopped {s['stopped_count']} and caught {s['tricks_caught']} trick listing(s).")
    log.warning("SAHAYA_FAKE=1: fake PayPal and scripted AI, no real payments or model calls")

    @app.get("/fake-paypal/{pid}")
    def fake_paypal(pid: str):
        """Pretend PayPal approval: goes straight to the normal return URL."""
        return RedirectResponse(f"{config.BACKEND_URL}/paypal/return?pid={pid}")


class ChatIn(BaseModel):
    session_id: str = Field(min_length=6, max_length=64)
    message: str = Field(min_length=1, max_length=2000)


class FamilyIn(BaseModel):
    approve: bool


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=300)


class DemoIn(BaseModel):
    on: bool


def _guard(fn, *args):
    try:
        return service.public(fn(*args))
    except FlowError as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 409, str(e))
    except PayPalError as e:
        raise HTTPException(502, str(e))


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "paypal_configured": service.paypal.configured,
        "channel3_configured": bool(config.CHANNEL3_API_KEY),
        "llm_configured": bool(config.GROQ_API_KEY),
        "rules": {
            "daily_spend_cap": config.DAILY_SPEND_CAP,
            "family_approval_over": config.FAMILY_APPROVAL_OVER,
            "max_quantity": config.MAX_QUANTITY,
        },
    }


@app.post("/api/chat")
def chat(body: ChatIn):
    try:
        return agent.chat(body.session_id, body.message)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:  # always answer with JSON so the browser shows a real message
        log.exception("chat failed")
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:200]}")


@app.get("/api/purchases/{pid}")
def get_purchase(pid: str):
    return _guard(service.get, pid)


@app.get("/api/sessions/{sid}/purchases")
def list_purchases(sid: str):
    return [service.public(p) for p in service.list_for(sid)]


@app.get("/api/sessions/{sid}/state")
def session_state(sid: str):
    """Options on screen and the latest purchase, so a reload (or coming back from PayPal) shows the same page."""
    return agent.state(sid)


@app.post("/api/sessions/{sid}/reset")
def session_reset(sid: str):
    """Start over: clears the conversation and options, cancels anything still waiting. History is kept."""
    return agent.reset(sid)


@app.post("/api/sessions/{sid}/safety-demo")
def safety_demo(sid: str, body: DemoIn):
    """Adds one clearly labelled fake listing to this session's searches. It tries to trick the AI."""
    store.session(sid)["safety_demo"] = body.on
    service.trace(sid, "demo", "safety demo on" if body.on else "safety demo off")
    return {"safety_demo": body.on}


@app.get("/api/sessions/{sid}/dashboard")
def family_dashboard(sid: str):
    """Everything Sahaya did for this person, each payment checked live with PayPal."""
    return dashboard.build(service, sid)


@app.post("/api/sessions/{sid}/dashboard/ask")
def family_ask(sid: str, body: AskIn):
    try:
        return {"answer": dashboard.ask(service, sid, body.question, globals()["ask_llm"])}
    except (LLMError, RuntimeError) as e:
        log.warning("dashboard ask failed: %s", e)
        return {"answer": "I can't answer right now. The table below has every purchase."}


@app.get("/api/sessions/{sid}/trace")
def trace(sid: str):
    return store.session(sid)["trace"][-60:]


@app.post("/api/purchases/{pid}/confirm")
def confirm(pid: str):
    return _guard(service.confirm, pid)


@app.post("/api/purchases/{pid}/cancel")
def cancel(pid: str):
    return _guard(service.cancel, pid)


@app.post("/api/purchases/{pid}/family")
def family(pid: str, body: FamilyIn):
    return _guard(service.family_decide, pid, body.approve)


@app.post("/api/purchases/{pid}/refund")
def refund(pid: str):
    return _guard(service.refund, pid)


@app.get("/paypal/return")
def paypal_return(pid: str):
    try:
        service.complete(pid)
        return RedirectResponse(f"{config.FRONTEND_URL}/done?pid={pid}&result=paid")
    except (FlowError, PayPalError):
        return RedirectResponse(f"{config.FRONTEND_URL}/done?pid={pid}&result=error")


@app.get("/paypal/cancel")
def paypal_cancel(pid: str):
    try:
        service.cancel(pid)
    except FlowError:
        pass
    return RedirectResponse(f"{config.FRONTEND_URL}/done?pid={pid}&result=cancelled")
