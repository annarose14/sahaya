"""Sahaya API."""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import config
from .agent import Agent
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


class ChatIn(BaseModel):
    session_id: str = Field(min_length=6, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


class FamilyIn(BaseModel):
    approve: bool


def _guard(fn, *args):
    try:
        return service.public(fn(*args))
    except FlowError as e:
        raise HTTPException(409, str(e))
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
