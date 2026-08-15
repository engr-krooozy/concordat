"""Mission control: the analyst's window onto fleets working in the background.

Read-only against Firestore, plus one write path — the approval gate, which is the single
point where a human decides anything. Bank services are private, so approvals are proxied
with this service's own identity rather than exposing the fleets to the browser.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import google.auth.transport.requests
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore
from google.oauth2 import id_token as id_token_mod

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("concordat.ui")

PROJECT = os.environ.get("GCP_PROJECT", "concordat-hack")
BANK_URLS = {
    "alpha": os.environ.get("BANK_ALPHA_URL", "https://bank-alpha-fa7ntw3nkq-uc.a.run.app"),
    "meridian": os.environ.get(
        "BANK_MERIDIAN_URL", "https://bank-meridian-fa7ntw3nkq-uc.a.run.app"
    ),
    "union": os.environ.get("BANK_UNION_URL", "https://bank-union-fa7ntw3nkq-uc.a.run.app"),
}
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="concordat-mission-control")
db = firestore.Client(project=PROJECT)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "mission-control"}


@app.get("/api/cases")
def list_cases(limit: int = 20) -> list[dict]:
    """Recent cases across all fleets, newest first."""
    docs = [d.to_dict() for d in db.collection("cases").stream()]
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
    snap = db.collection("cases").document(case_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="case not found")
    return snap.to_dict()


@app.get("/api/negotiations/{case_id}")
def peer_transcripts(case_id: str) -> list[dict]:
    """The other side of the conversation: what each peer's policy engine recorded."""
    out = []
    for bank in BANK_URLS:
        snap = db.collection("negotiations").document(f"{bank}:{case_id}").get()
        if snap.exists:
            out.append(snap.to_dict())
    return out


@app.post("/api/cases/{case_id}/approve")
def approve(case_id: str, approver: str = "analyst@mission-control") -> dict:
    """The human gate. Proxied to the owning fleet with this service's identity."""
    snap = db.collection("cases").document(case_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="case not found")
    bank = snap.to_dict()["bank"]
    url = BANK_URLS[bank]
    token = id_token_mod.fetch_id_token(google.auth.transport.requests.Request(), url)
    resp = httpx.post(
        f"{url}/cases/{case_id}/approve",
        params={"approver": approver},
        headers={"Authorization": f"Bearer {token}"},
        timeout=90,
    )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    log.info("case %s approved by %s", case_id, approver)
    return resp.json()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
