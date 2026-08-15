"""Bank fleet service: Pub/Sub push endpoint + case reads + health.

BANK=alpha uvicorn services.bank.api.main:app --port 8081
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, Response

from services.bank.config import load_config
from services.bank.events import decode_push
from services.bank.orchestrator import Orchestrator

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("concordat.api")
cfg = load_config()
app = FastAPI(title=f"concordat-bank-{cfg.bank}")
orch = Orchestrator(cfg)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "bank": cfg.bank}


@app.post("/pubsub")
async def pubsub_push(request: Request) -> Response:
    envelope = await request.json()
    try:
        event = decode_push(envelope)
    except (KeyError, ValueError) as exc:  # malformed: ack (204) so it never redelivers
        log.warning("dropping malformed push message: %s", exc)
        return Response(status_code=204)
    if event.bank != cfg.bank:
        log.warning("event for bank %s delivered to %s; dropping", event.bank, cfg.bank)
        return Response(status_code=204)
    await orch.handle(event)
    return Response(status_code=204)


@app.get("/cases/{case_id}")
def get_case(case_id: str) -> dict:
    try:
        return orch.store.load(case_id).model_dump(mode="json")
    except KeyError:
        raise HTTPException(status_code=404, detail="case not found")
