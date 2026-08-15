"""Initiator-side negotiation: the diplomat opens a joint investigation with every
discovered counterpart and converges on terms all policy engines accept.

Division of labour (invariant #2):
- Gemini drafts the natural-language *rationale* only.
- Code builds the typed proposal (clamped to our own policy), collects verdicts and
  counters, converges (k = max of all demands, ttl = min), and signs.
A rejection with non-negotiable violations ends the negotiation (REJECTED) — that path is
demoable governance, not a failure mode.
"""

from __future__ import annotations

import logging

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from services.bank.a2a import protocol
from services.bank.a2a.card import IDENTIFIER_SCHEME
from services.bank.a2a.hashing import hash_account, new_case_salt
from services.bank.agents.diplomat import Diplomat
from services.bank.agents.fleet import bank_model
from services.bank.case import CaseState, Status
from services.bank.config import BankConfig
from services.bank.policy.engine import load_policy

log = logging.getLogger("concordat.negotiation")

MAX_ROUNDS = 4


async def _draft_rationale(cfg: BankConfig, case: CaseState) -> str:
    """Gemini drafts a one-paragraph redacted rationale for peers. No account ids, no
    amounts precise enough to fingerprint a customer — instructions enforce, redactor
    gate (Phase 2 day 3) will verify."""
    agent = Agent(
        name=f"{cfg.bank}_rationale_drafter",
        model=bank_model(cfg),
        instruction=(
            "Draft ONE paragraph (<80 words) asking peer banks to join a privacy-safe joint "
            "fund-trace. State: fraud type, that funds crossed institutional boundaries, "
            "urgency, and that only hashed identifiers and k-thresholded aggregates will be "
            "shared. NEVER include account numbers, exact amounts, names, or dates more "
            "precise than the month."
        ),
    )
    runner = InMemoryRunner(agent=agent, app_name="concordat")
    session = await runner.session_service.create_session(app_name="concordat", user_id="system")
    msg = types.Content(role="user", parts=[types.Part(text=case.summary or "cross-bank fraud")])
    chunks: list[str] = []
    async for event in runner.run_async(user_id="system", session_id=session.id, new_message=msg):
        if event.content and event.content.parts:
            chunks.extend(p.text for p in event.content.parts if p.text)
    return "".join(chunks).strip()


def _record(case: CaseState, direction: str, peer: str, msg: protocol.NegotiationMessage) -> None:
    case.negotiation_transcript.append(
        {"direction": direction, "peer": peer, "message": msg.model_dump(mode="json")}
    )
    case.log(f"{case.bank}/diplomat", f"negotiation:{direction}:{msg.kind}", f"peer={peer}")


async def negotiate(
    cfg: BankConfig, case: CaseState, diplomat: Diplomat
) -> protocol.ConcordatSigned | None:
    """Run the full negotiation. Returns the signed concordat, or None if rejected.
    Mutates case (status, transcript, concordat) — caller persists."""
    own_policy = load_policy(cfg)
    case.transition(Status.DISCOVERING, f"{cfg.bank}/diplomat")
    peers = await diplomat.discover()
    case.log(f"{cfg.bank}/diplomat", "discovered", f"{sorted(peers)}")

    case.case_salt = case.case_salt or new_case_salt()
    boundary_hashes = [hash_account(case.case_salt, e.txn.dst_account) for e in case.boundary_edges]
    rationale = await _draft_rationale(cfg, case)

    proposal = protocol.InvestigationRequest(
        bank=cfg.bank,
        case_ref=case.case_id,
        round=1,
        rationale=rationale,
        computations=[
            protocol.JointComputation(
                kind="path_join",
                description="follow hashed boundary accounts through peer ledgers",
            ),
            protocol.JointComputation(
                kind="fan_in_cluster",
                description="find common cash-out concentration across all parties",
            ),
        ],
        k_threshold=own_policy.rules.min_k_threshold,
        identifier_scheme=IDENTIFIER_SCHEME,
        ttl_hours=own_policy.rules.max_ttl_hours,
        boundary_hashes=boundary_hashes,
        case_salt=case.case_salt,
    )
    case.transition(
        Status.NEGOTIATING,
        f"{cfg.bank}/diplomat",
        f"opening k={proposal.k_threshold} ttl={proposal.ttl_hours}",
    )

    for round_no in range(1, MAX_ROUNDS + 1):
        proposal.round = round_no
        accepts: set[str] = set()
        demanded_k = [proposal.k_threshold]
        demanded_ttl = [proposal.ttl_hours]
        for peer, card_url in sorted(peers.items()):
            _record(case, "sent", peer, proposal)
            reply = await diplomat.send(card_url, proposal)
            _record(case, "received", peer, reply)
            match reply:
                case protocol.PolicyVerdict(verdict="accept"):
                    accepts.add(peer)
                case protocol.CounterProposal():
                    demanded_k.append(reply.k_threshold)
                    demanded_ttl.append(reply.ttl_hours)
                case protocol.PolicyVerdict(verdict="reject"):
                    case.transition(
                        Status.REJECTED,
                        f"{cfg.bank}/diplomat",
                        f"{peer} rejected: {reply.violated_rules}",
                    )
                    return None
                case _:
                    log.warning("unexpected reply %s from %s", reply.kind, peer)
        if accepts == set(peers):
            break
        # converge: strictest demands win, next round
        proposal.k_threshold = max(demanded_k)
        proposal.ttl_hours = min(demanded_ttl)
        case.log(
            f"{cfg.bank}/diplomat",
            "negotiation:converge",
            f"round {round_no + 1}: k={proposal.k_threshold} ttl={proposal.ttl_hours}",
        )
    else:
        case.transition(Status.REJECTED, f"{cfg.bank}/diplomat", "no convergence in max rounds")
        return None

    signed = protocol.ConcordatSigned(
        case_ref=case.case_id,
        parties=sorted([cfg.bank, *peers]),
        computations=proposal.computations,
        k_threshold=proposal.k_threshold,
        identifier_scheme=proposal.identifier_scheme,
        ttl_hours=proposal.ttl_hours,
    )
    for peer, card_url in sorted(peers.items()):
        _record(case, "sent", peer, signed)
        echo = await diplomat.send(card_url, signed)
        _record(case, "received", peer, echo)
    case.concordat = signed.model_dump(mode="json")
    case.transition(
        Status.AGREED,
        f"{cfg.bank}/diplomat",
        f"terms_digest={signed.terms_digest()} k={signed.k_threshold}",
    )
    return signed
