"""Bank fleet service: Pub/Sub push endpoint + case reads + health.

BANK=alpha uvicorn services.bank.api.main:app --port 8081
"""

from __future__ import annotations

import logging
import os

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from fastapi import FastAPI, HTTPException, Request, Response

from services.bank.a2a.card import build_card, card_json
from services.bank.a2a.executor import NegotiationExecutor
from services.bank.config import load_config
from services.bank.events import decode_push
from services.bank.orchestrator import Orchestrator

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("concordat.api")
cfg = load_config()
app = FastAPI(title=f"concordat-bank-{cfg.bank}")
orch = Orchestrator(cfg)

# --- A2A endpoint: how other banks' fleets talk to this one -------------------
BASE_URL = os.environ.get("SERVICE_URL", f"http://localhost:{os.environ.get('PORT', '8081')}")
_handler = DefaultRequestHandler(
    agent_executor=NegotiationExecutor(cfg),
    task_store=InMemoryTaskStore(),
    agent_card=build_card(cfg, BASE_URL),
)
for route in create_jsonrpc_routes(_handler, rpc_url="/a2a"):
    app.router.routes.append(route)


@app.get("/.well-known/agent-card.json")
def agent_card() -> dict:
    return card_json(cfg, BASE_URL)


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


@app.post("/cases/{case_id}/approve")
async def approve_case(case_id: str, approver: str = "analyst") -> dict:
    """The human gate. Enforcement cannot start without a person calling this."""
    try:
        case = await orch.approve(case_id, approver)
    except KeyError:
        raise HTTPException(status_code=404, detail="case not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"case_id": case.case_id, "status": case.status, "approved_by": approver}
