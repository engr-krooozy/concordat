"""Agent-card registry — the fleet catalog (Fortified Enterprise Fleet: 'agent cataloging').

Banks register the URL of their A2A agent card; peers discover counterparts here and then
fetch cards directly from each bank (the registry stores pointers, never capabilities —
cards stay authoritative at their source).

    uvicorn services.registry.main:app --port 8090
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from google.cloud import firestore
from pydantic import BaseModel, HttpUrl

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("concordat.registry")
app = FastAPI(title="concordat-registry")
db = firestore.Client(project=os.environ.get("GCP_PROJECT", "concordat-hack"))
col = db.collection("agent_cards")


class Registration(BaseModel):
    bank: str
    card_url: HttpUrl  # e.g. https://bank-alpha-....run.app/.well-known/agent-card.json


# /healthz never reaches the container: Google's frontend answers that exact path
# with its own 404 before Cloud Run routes it. /health is ours.
@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "registry"}


@app.post("/register")
def register(reg: Registration) -> dict:
    col.document(reg.bank).set(
        {
            "bank": reg.bank,
            "card_url": str(reg.card_url),
            "registered_at": datetime.now(UTC).isoformat(),
        }
    )
    log.info("registered card for %s: %s", reg.bank, reg.card_url)
    return {"ok": True}


@app.get("/cards")
def cards() -> list[dict]:
    return [doc.to_dict() for doc in col.stream()]


@app.get("/cards/{bank}")
def card(bank: str) -> dict:
    snap = col.document(bank).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail=f"no card registered for {bank}")
    return snap.to_dict()
