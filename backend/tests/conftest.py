import pytest

from app import config
from app.fakes import FakePayPal, ScriptedShopper, call  # noqa: F401  (re-exported for tests)


@pytest.fixture
def offline(monkeypatch):
    """No network: demo catalog, no injected listing unless a test turns it on."""
    monkeypatch.setattr(config, "CHANNEL3_API_KEY", "")
    monkeypatch.setattr(config, "DEMO_INJECTION", False)
    monkeypatch.setattr(config, "GROQ_API_KEY", "test")
