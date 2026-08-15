"""Negotiation protocol messages (ARCHITECTURE.md). Carried as JSON text parts inside
standard A2A Messages; every message Pydantic-validated on both ends and persisted to the
negotiation transcript. LLMs never emit these directly — they draft *content*, code builds
and validates the envelope (invariant #2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter


class JointComputation(BaseModel):
    """One computation the initiator asks to run in the clean room."""

    kind: Literal["path_join", "fan_in_cluster"]
    description: str
    # path_join: follow hashed dst accounts of my boundary edges through your ledger
    # fan_in_cluster: find common cash-out concentration across contributed edges


class Handshake(BaseModel):
    kind: Literal["handshake"] = "handshake"
    bank: str
    case_ref: str  # opaque case reference, NOT the internal case id
    identifier_scheme: str


class HandshakeAck(BaseModel):
    kind: Literal["handshake_ack"] = "handshake_ack"
    bank: str
    identifier_scheme: str
    policy_version: str


class InvestigationRequest(BaseModel):
    kind: Literal["investigation_request"] = "investigation_request"
    bank: str  # initiator
    case_ref: str
    round: int = 1
    rationale: str  # redacted natural-language rationale (Gemma-gated before send)
    computations: list[JointComputation]
    k_threshold: int
    identifier_scheme: str
    ttl_hours: int
    boundary_hashes: list[str]  # salted hashes of dst accounts at our boundary
    case_salt: str  # per-case salt all parties use so hashed identifiers join in the room


class PolicyVerdict(BaseModel):
    kind: Literal["policy_verdict"] = "policy_verdict"
    bank: str  # responder
    case_ref: str
    round: int
    verdict: Literal["accept", "reject"]
    violated_rules: list[str] = []  # machine-readable rule ids when rejecting


class CounterProposal(BaseModel):
    kind: Literal["counter_proposal"] = "counter_proposal"
    bank: str
    case_ref: str
    round: int
    k_threshold: int
    ttl_hours: int
    computations: list[JointComputation]
    note: str


class ConcordatSigned(BaseModel):
    kind: Literal["concordat_signed"] = "concordat_signed"
    case_ref: str
    parties: list[str]
    computations: list[JointComputation]
    k_threshold: int
    identifier_scheme: str
    ttl_hours: int
    signed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def terms_digest(self) -> str:
        """Stable hash of the agreed terms; doubles as the clean-room config key."""
        import hashlib

        blob = self.model_dump_json(
            include={
                "case_ref",
                "parties",
                "computations",
                "k_threshold",
                "identifier_scheme",
                "ttl_hours",
            }
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


class RoomDissolved(BaseModel):
    kind: Literal["room_dissolved"] = "room_dissolved"
    case_ref: str
    terms_digest: str


NegotiationMessage = Annotated[
    Handshake
    | HandshakeAck
    | InvestigationRequest
    | PolicyVerdict
    | CounterProposal
    | ConcordatSigned
    | RoomDissolved,
    Field(discriminator="kind"),
]

_adapter: TypeAdapter = TypeAdapter(NegotiationMessage)


def parse(raw: str | bytes) -> NegotiationMessage:
    return _adapter.validate_json(raw)


def dump(msg: NegotiationMessage) -> str:
    return msg.model_dump_json()
