"""Mission control: the analyst's window onto fleets working in the background.

Read-only against Firestore, plus one write path — the approval gate, which is the single
point where a human decides anything. Bank services are private, so approvals are proxied
with this service's own identity rather than exposing the fleets to the browser.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import google.auth.transport.requests
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore, run_v2
from google.oauth2 import id_token as id_token_mod

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("concordat.ui")

PROJECT = os.environ.get("GCP_PROJECT", "concordat-hack")
BANKS = ("alpha", "meridian", "union")
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="concordat-mission-control")


def bank_project(bank: str) -> str:
    return os.environ.get(f"{bank.upper()}_PROJECT", f"concordat-{bank}")


# One Firestore per bank, because each bank keeps its own case state in its own project.
# Mission control is an observatory: every bank grants it read access to case metadata, and
# none of them grants it anything else. There is no single database behind this view.
#
# Built lazily and per-bank: a federation where one member is unreachable should degrade to
# showing the others, not fail to start.
@lru_cache(maxsize=len(BANKS))
def _store(bank: str) -> firestore.Client:
    return firestore.Client(project=bank_project(bank))


def _stores_items():
    for bank in BANKS:
        try:
            yield bank, _store(bank)
        except Exception as exc:  # noqa: BLE001 - one silent member must not blind the rest
            log.warning("cannot reach %s's case store: %s", bank, exc)


@lru_cache(maxsize=1)
def _bank_urls() -> dict[str, str]:
    """Resolve each fleet's Cloud Run URL in its own project, once.

    Normally these arrive as BANK_<BANK>_URL, set by infra/wire_federation.sh: this service
    holds run.invoker on each fleet but deliberately NOT run.services.get, so it can knock on
    a bank's door without enumerating what is behind it. The API lookup below therefore fails
    by design — it is a fallback for a dev running with wider credentials, and if it is being
    reached in production the wiring has been lost.
    """
    urls = {}
    for bank in BANKS:
        override = os.environ.get(f"BANK_{bank.upper()}_URL")
        if override:
            urls[bank] = override
            continue
        try:
            service = run_v2.ServicesClient()
            name = f"projects/{bank_project(bank)}/locations/us-central1/services/bank-{bank}"
            urls[bank] = service.get_service(name=name).uri
        except Exception as exc:  # surfaced as an actionable 503, never a bare traceback
            raise RuntimeError(
                f"mission control has not been told where bank {bank} lives: "
                f"BANK_{bank.upper()}_URL is unset and looking it up failed ({exc}). "
                "Re-run infra/wire_federation.sh — a deploy that replaces the environment "
                "wipes these."
            ) from exc
    return urls


# /healthz never reaches the container: Google's frontend answers that exact path
# with its own 404 before Cloud Run routes it. /health is ours.
@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "mission-control"}


@app.get("/api/cases")
def list_cases(limit: int = 20) -> list[dict]:
    """Recent cases across all fleets, newest first."""
    docs = [d.to_dict() for _, store in _stores_items() for d in store.collection("cases").stream()]
    docs.sort(key=lambda c: c.get("opened_at", ""), reverse=True)
    return [
        {
            "case_id": c["case_id"],
            "bank": c["bank"],
            "status": c["status"],
            "opened_at": c.get("opened_at"),
            "boundary_edges": len(c.get("boundary_edges", [])),
            "has_finding": bool(c.get("finding")),
        }
        for c in docs[:limit]
    ]


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    for _, store in _stores_items():
        snap = store.collection("cases").document(case_id).get()
        if snap.exists:
            return snap.to_dict()
    raise HTTPException(status_code=404, detail="case not found")


@app.get("/api/negotiations/{case_id}")
def peer_transcripts(case_id: str) -> list[dict]:
    """The other side of the conversation: what each peer's policy engine recorded."""
    out = []
    for bank, store in _stores_items():
        snap = store.collection("negotiations").document(f"{bank}:{case_id}").get()
        if snap.exists:
            out.append(snap.to_dict())
    return out


@app.post("/api/cases/{case_id}/approve")
def approve(case_id: str, approver: str = "analyst@mission-control") -> dict:
    """The human gate. Proxied to the owning fleet with this service's identity."""
    case = get_case(case_id)
    bank = case["bank"]
    try:
        url = _bank_urls()[bank]
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    token = id_token_mod.fetch_id_token(google.auth.transport.requests.Request(), url)
    resp = httpx.post(
        f"{url}/cases/{case_id}/approve",
        params={"approver": approver},
        headers={"Authorization": f"Bearer {token}"},
        timeout=90,
    )
    if resp.status_code >= 400:
        # The fleet already explains itself — a refused approval says which term lapsed and
        # what to do about it. Passing resp.text through wraps that in a second layer of JSON
        # and the analyst reads escape sequences instead of the sentence.
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)
    log.info("case %s approved by %s", case_id, approver)
    return resp.json()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
