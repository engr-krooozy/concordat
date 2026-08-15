"""Negotiation loop against REAL responder logic (executor._respond with real policies),
with only the transport and the LLM rationale stubbed out."""

import pytest

from services.bank.a2a import protocol
from services.bank.a2a.executor import NegotiationExecutor
from services.bank.case import BoundaryEdge, CaseState, Status
from services.bank.ledger import Txn
from tests.test_policy import cfg_for


class StubDiplomat:
    """Routes messages directly to peer executors in-process."""

    def __init__(self, peers: dict[str, NegotiationExecutor]):
        self.peers = peers
        self.rounds_seen: list[int] = []
        self.last_gate_findings: list[str] = []  # mirrors the real Diplomat's interface

    async def discover(self) -> dict[str, str]:
        return {bank: f"stub://{bank}" for bank in self.peers}

    async def send(self, card_url: str, msg):
        bank = card_url.removeprefix("stub://")
        if isinstance(msg, protocol.InvestigationRequest):
            self.rounds_seen.append(msg.round)
        return self.peers[bank]._respond(msg)


def dead_end_case() -> CaseState:
    case = CaseState(case_id="case-t1", bank="alpha")
    case.transition(Status.TRACING, "t")
    case.boundary_edges = [
        BoundaryEdge(
            txn=Txn(
                txn_id="ALP-G3",
                ts="2026-08-12T13:27:00Z",
                src_account="ALP-9000003",
                dst_account="MER-9000101",
                src_bank="alpha",
                dst_bank="meridian",
                amount=1180800.0,
                channel="transfer",
                narration="transfer",
            ),
            peer_bank="meridian",
        )
    ]
    case.transition(Status.DEAD_END, "t")
    case.summary = "funds left our perimeter"
    return case


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    async def fake_rationale(cfg, case):
        return "redacted rationale"

    monkeypatch.setattr("services.bank.agents.negotiation._draft_rationale", fake_rationale)


async def test_negotiation_converges_after_counter():
    from services.bank.agents.negotiation import negotiate

    peers = {b: NegotiationExecutor(cfg_for(b)) for b in ("meridian", "union")}
    diplomat = StubDiplomat(peers)
    case = dead_end_case()

    signed = await negotiate(cfg_for("alpha"), case, diplomat)

    assert signed is not None
    assert case.status is Status.AGREED
    # meridian's floor won; union's ttl irrelevant; meridian tightened ttl
    assert signed.k_threshold == 25 and signed.ttl_hours == 48
    assert signed.parties == ["alpha", "meridian", "union"]
    # exactly two rounds: opening k=10 countered, k=25 accepted
    assert diplomat.rounds_seen == [1, 1, 2, 2]
    kinds = [t["message"]["kind"] for t in case.negotiation_transcript]
    assert "counter_proposal" in kinds and "concordat_signed" in kinds


async def test_non_negotiable_rejection_ends_case():
    from services.bank.agents import negotiation as neg

    peers = {b: NegotiationExecutor(cfg_for(b)) for b in ("meridian",)}
    diplomat = StubDiplomat(peers)
    case = dead_end_case()

    # force an illegal scheme so meridian's policy rejects outright
    import services.bank.agents.negotiation as mod

    orig = mod.IDENTIFIER_SCHEME
    mod.IDENTIFIER_SCHEME = "plaintext"
    try:
        signed = await neg.negotiate(cfg_for("alpha"), case, diplomat)
    finally:
        mod.IDENTIFIER_SCHEME = orig

    assert signed is None
    assert case.status is Status.REJECTED
