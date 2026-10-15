"""Checks that the PayPal sandbox, Channel3 and Groq keys in .env all work."""
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
PP_BASE = "https://api-m.sandbox.paypal.com"


def check_paypal():
    r = requests.post(f"{PP_BASE}/v1/oauth2/token",
                      auth=(os.getenv("PAYPAL_CLIENT_ID"), os.getenv("PAYPAL_CLIENT_SECRET")),
                      data={"grant_type": "client_credentials"}, timeout=20)
    r.raise_for_status()
    token = r.json()["access_token"]
    r = requests.post(f"{PP_BASE}/v2/checkout/orders",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"intent": "CAPTURE", "purchase_units": [{"amount": {"currency_code": "AUD", "value": "12.50"}}]},
                      timeout=20)
    r.raise_for_status()
    print(f"[OK] PayPal sandbox: test order {r.json()['id']} created")


def check_channel3():
    key = os.getenv("CHANNEL3_API_KEY")
    if not key:
        print("[SKIP] Channel3: no key, the demo catalog will be used")
        return
    r = requests.post("https://api.trychannel3.com/v1/search",
                      headers={"x-api-key": key}, json={"query": "talking alarm clock", "limit": 3}, timeout=30)
    r.raise_for_status()
    data = r.json()
    with open(os.path.join(os.path.dirname(__file__), "..", "channel3_sample.json"), "w") as f:
        json.dump(data, f, indent=2)
    items = data if isinstance(data, list) else (data.get("products") or data.get("results") or [])
    print(f"[OK] Channel3: {len(items)} products (saved to channel3_sample.json)")


def check_groq():
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                      json={"model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                            "messages": [{"role": "user", "content": "Reply with exactly: Groq is working"}]},
                      timeout=30)
    r.raise_for_status()
    print("[OK] Groq:", r.json()["choices"][0]["message"]["content"])


for name, fn in [("PayPal", check_paypal), ("Channel3", check_channel3), ("Groq", check_groq)]:
    try:
        fn()
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
