"""Case model + state machine (README.md). Firestore persistence lands in the
async-machinery step; every mutation goes through CaseState methods so persistence is a
drop-in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from services.bank.ledger import Txn


class Status(StrEnum):
    DETECTED = "detected"
    TRACING = "tracing"
    DEAD_END = "dead_end"
    DISCOVERING = "discovering"
    NEGOTIATING = "negotiating"
    AGREED = "agreed"
    ROOM_ACTIVE = "room_active"
    JOINT_ANALYSIS = "joint_analysis"
    AWAITING_APPROVAL = "awaiting_approval"
    ENFORCING = "enforcing"
    CLOSED = "closed"
    REJECTED = "rejected"


# Self-loops are not decoration: a handler that dies mid-step (a peer waking from zero, a
# dropped connection) is redelivered by Pub/Sub and re-runs that step from the top. Without
# a self-loop the retry hits an invalid transition and the case is stranded in the state it
# had reached — which is exactly how three demo cases froze in `negotiating`.
VALID_TRANSITIONS: dict[Status, set[Status]] = {
    Status.DETECTED: {Status.TRACING},
    Status.TRACING: {Status.DEAD_END, Status.CLOSED},
    Status.DEAD_END: {Status.DISCOVERING},
    Status.DISCOVERING: {Status.DISCOVERING, Status.NEGOTIATING},
    Status.NEGOTIATING: {Status.NEGOTIATING, Status.AGREED, Status.REJECTED},
    Status.AGREED: {Status.AGREED, Status.ROOM_ACTIVE},
    Status.ROOM_ACTIVE: {Status.ROOM_ACTIVE, Status.JOINT_ANALYSIS},
    Status.JOINT_ANALYSIS: {Status.JOINT_ANALYSIS, Status.AWAITING_APPROVAL},
    Status.AWAITING_APPROVAL: {Status.ENFORCING},
    Status.ENFORCING: {Status.CLOSED},
}

# Statuses a handler may pick a case up from. The first entry is the clean hand-off; the
# rest are a case resuming after its previous attempt was interrupted part-way.
RESUMABLE_FROM: dict[str, set[Status]] = {
    "negotiate": {Status.DEAD_END, Status.DISCOVERING, Status.NEGOTIATING},
    "joint_analysis": {Status.AGREED, Status.ROOM_ACTIVE, Status.JOINT_ANALYSIS},
}


class AuditEntry(BaseModel):
    ts: datetime
    actor: str  # e.g. "alpha/tracer", "meridian/policy_engine"
    action: str
    detail: str = ""


class BoundaryEdge(BaseModel):
    """A traced txn that leaves our perimeter — where the solo investigation dies."""

    txn: Txn
    peer_bank: str


class CaseState(BaseModel):
    case_id: str
    bank: str
    status: Status = Status.DETECTED
    opened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    victim_txn: Txn | None = None
    trace: list[Txn] = []
    boundary_edges: list[BoundaryEdge] = []
    audit: list[AuditEntry] = []
    summary: str = ""
    report: str = ""  # SAR-style case file drafted by the reporter agent
    case_salt: str = ""  # per-case identifier-hashing salt (set when negotiation opens)
    negotiation_transcript: list[dict] = []  # every sent/received NegotiationMessage
    concordat: dict | None = None  # the signed agreement (ConcordatSigned dump)
    finding: dict | None = None  # joint ring finding assembled in the clean room
    contributions: list[dict] = []  # per-bank k-thresholded hop receipts
    enforcement: list[str] = []  # actions taken inside OUR perimeter only
    # Stable across retries of the same approved case. Enforcement stages rather than
    # executes, so a repeat freezes nobody — but it does write the actions into the
    # append-only audit twice, and Pub/Sub redelivers whenever the handler dies between
    # staging and closing. The key is what a core banking system would key on downstream.
    enforcement_key: str = ""

    def log(self, actor: str, action: str, detail: str = "") -> None:
        self.audit.append(
            AuditEntry(ts=datetime.now(UTC), actor=actor, action=action, detail=detail)
        )

    def transition(self, to: Status, actor: str, detail: str = "") -> None:
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if to not in allowed:
            raise ValueError(f"illegal transition {self.status} -> {to}")
        self.log(actor, f"status:{self.status}->{to}", detail)
        self.status = to
