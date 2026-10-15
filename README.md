# Sahaya

Shop by voice, safely. Sahaya is a voice first shopping agent for people who are blind, have low vision, or are older. It finds real products, reads options aloud, and pays through PayPal, but only after plain code safety rules and the person's own "yes".

Built for the PayPal AI Hackathon 2026.

## Run it locally

Needs Python 3.11+ and Node 18+.

```bash
cp .env.example .env          # then add your keys
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in Chrome.

## Tests

```bash
cd backend && source .venv/bin/activate && pytest -q
```
