"""All settings come from environment variables (see .env.example)."""
import os

from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_BASE = "https://api-m.sandbox.paypal.com"  # sandbox only, never live money

CHANNEL3_API_KEY = os.getenv("CHANNEL3_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

# Guardrails (enforced in plain code, never by the AI)
DAILY_SPEND_CAP = _float("DAILY_SPEND_CAP", 150)
FAMILY_APPROVAL_OVER = _float("FAMILY_APPROVAL_OVER", 50)
MAX_QUANTITY = int(_float("MAX_QUANTITY", 5))
PRICE_GUARD_RATIO = _float("PRICE_GUARD_RATIO", 1.5)

# Adds one clearly labelled simulated malicious listing to results so the
# prompt injection defence can be shown in the demo. Off by default.
DEMO_INJECTION = os.getenv("DEMO_INJECTION", "false").lower() == "true"
