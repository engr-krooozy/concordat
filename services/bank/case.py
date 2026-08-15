"""Case model + state machine (ARCHITECTURE.md). Firestore persistence lands in the
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


VALID_TRANSITIONS: dict[Status, set[Status]] = {
    Status.DETECTED: {Status.TRACING},
    Status.TRACING: {Status.DEAD_END, Status.CLOSED},
    Status.DEAD_END: {Status.DISCOVERING},
    Status.DISCOVERING: {Status.NEGOTIATING},
    Status.NEGOTIATING: {Status.NEGOTIATING, Status.AGREED, Status.REJECTED},
    Status.AGREED: {Status.ROOM_ACTIVE},
    Status.ROOM_ACTIVE: {Status.JOINT_ANALYSIS},
    Status.JOINT_ANALYSIS: {Status.AWAITING_APPROVAL},
    Status.AWAITING_APPROVAL: {Status.ENFORCING},
    Status.ENFORCING: {Status.CLOSED},
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
