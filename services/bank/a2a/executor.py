"""A2A server executor: how OTHER banks' fleets talk to ours. Incoming Messages carry one
JSON text part = one NegotiationMessage. Today: handshake. The negotiation state machine
plugs in here (Phase 2 day 2).
"""

from __future__ import annotations

import logging
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import Message, Part, Role
from google.cloud import firestore

from services.bank.a2a import protocol
from services.bank.a2a.card import IDENTIFIER_SCHEME
from services.bank.auth import bank_credentials
from services.bank.config import BankConfig
from services.bank.policy.engine import counter_terms, evaluate, load_policy
from services.cleanroom.compiler import contribute_hop, revoke_contribution

log = logging.getLogger("concordat.a2a")


class NegotiationExecutor(AgentExecutor):
    def __init__(self, cfg: BankConfig):
        self.cfg = cfg
        self.policy = load_policy(cfg)
        self._db: firestore.Client | None = None

    def _log_exchange(
        self, incoming: protocol.NegotiationMessage, outgoing: protocol.NegotiationMessage
    ) -> None:
        """Responder-side transcript: append both halves to negotiations/<case_ref>."""
        case_ref = getattr(incoming, "case_ref", "unknown")
        if self._db is None:
            self._db = firestore.Client(
                project=self.cfg.project, credentials=bank_credentials(self.cfg)
            )
        self._db.collection("negotiations").document(f"{self.cfg.bank}:{case_ref}").set(
            {
                "bank": self.cfg.bank,
                "case_ref": case_ref,
                "transcript": firestore.ArrayUnion(
                    [
                        {"direction": "received", "message": incoming.model_dump(mode="json")},
                        {"direction": "sent", "message": outgoing.model_dump(mode="json")},
                    ]
                ),
            },
            merge=True,
        )

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        raw = ""
        if context.message and context.message.parts:
            raw = context.message.parts[0].text
        try:
            incoming = protocol.parse(raw)
        except (ValueError, KeyError) as exc:
            log.warning("unparseable negotiation message: %s", exc)
            reply = Message(
                message_id=str(uuid4()),
                role=Role.ROLE_AGENT,
                parts=[Part(text='{"error": "unparseable message"}')],
            )
            await event_queue.enqueue_event(reply)
            return

        response = await self.handle(incoming)
        reply = Message(
            message_id=str(uuid4()),
            role=Role.ROLE_AGENT,
            context_id=context.context_id,
            parts=[Part(text=protocol.dump(response))],
        )
        await event_queue.enqueue_event(reply)

    async def handle(self, incoming: protocol.NegotiationMessage) -> protocol.NegotiationMessage:
        response = self._respond(incoming)
        if not isinstance(incoming, protocol.Handshake):  # handshakes are not case-bound
            self._log_exchange(incoming, response)
        return response

    def _respond(self, incoming: protocol.NegotiationMessage) -> protocol.NegotiationMessage:
        match incoming:
            case protocol.Handshake():
                log.info("handshake from %s (case %s)", incoming.bank, incoming.case_ref)
                return protocol.HandshakeAck(
                    bank=self.cfg.bank,
                    identifier_scheme=IDENTIFIER_SCHEME,
                    policy_version=self.policy.version,
                )
            case protocol.InvestigationRequest():
                violations = evaluate(self.policy, incoming)
                if not violations:
                    log.info(
                        "ACCEPT round %d from %s (k=%d)",
                        incoming.round,
                        incoming.bank,
                        incoming.k_threshold,
                    )
                    return protocol.PolicyVerdict(
                        bank=self.cfg.bank,
                        case_ref=incoming.case_ref,
                        round=incoming.round,
                        verdict="accept",
                    )
                counter = counter_terms(self.policy, incoming)
                if counter is not None:
                    counter.bank = self.cfg.bank
                    log.info(
                        "COUNTER round %d from %s: %s", incoming.round, incoming.bank, violations
                    )
                    return counter
                log.info("REJECT round %d from %s: %s", incoming.round, incoming.bank, violations)
                return protocol.PolicyVerdict(
                    bank=self.cfg.bank,
                    case_ref=incoming.case_ref,
                    round=incoming.round,
                    verdict="reject",
                    violated_rules=violations,
                )
            case protocol.ConcordatSigned():
                # final check: never countersign terms our policy would not accept
                as_request = protocol.InvestigationRequest(
                    bank=self.cfg.bank,
                    case_ref=incoming.case_ref,
                    round=0,
                    rationale="final",
                    computations=incoming.computations,
                    k_threshold=incoming.k_threshold,
                    identifier_scheme=incoming.identifier_scheme,
                    ttl_hours=incoming.ttl_hours,
                    boundary_hashes=[],
                    case_salt="",
                )
                violations = evaluate(self.policy, as_request)
                if violations:
                    log.warning("refusing to countersign: %s", violations)
                    return protocol.PolicyVerdict(
                        bank=self.cfg.bank,
                        case_ref=incoming.case_ref,
                        round=99,
                        verdict="reject",
                        violated_rules=violations,
                    )
                log.info(
                    "countersigned concordat %s (k=%d, parties=%s)",
                    incoming.terms_digest(),
                    incoming.k_threshold,
                    incoming.parties,
                )
                return incoming  # echo = countersignature
            case protocol.ContributionRequest():
                # never contribute on terms our own policy would not have accepted
                as_request = protocol.InvestigationRequest(
                    bank=self.cfg.bank,
                    case_ref=incoming.case_ref,
                    round=0,
                    rationale="contribution",
                    computations=[],
                    boundary_hashes=[],
                    k_threshold=incoming.k_threshold,
                    identifier_scheme=incoming.identifier_scheme,
                    ttl_hours=1,
                    case_salt="",
                )
                violations = evaluate(self.policy, as_request)
                if violations:
                    log.warning("refusing contribution: %s", violations)
                    return protocol.ContributionReceipt(
                        bank=self.cfg.bank,
                        case_ref=incoming.case_ref,
                        accounts=0,
                        total_ngn=0.0,
                        refused=violations,
                    )
                contribution = contribute_hop(
                    self.cfg,
                    incoming.terms_digest,
                    incoming.k_threshold,
                    incoming.case_salt,
                    incoming.window_start,
                    incoming.window_end,
                    incoming.room_runner,
                    list(incoming.probe_hashes),
                    incoming.room_dataset,
                )
                log.info(
                    "contributed hop for %s: %d accounts", incoming.case_ref, contribution.accounts
                )
                return protocol.ContributionReceipt(
                    bank=self.cfg.bank,
                    case_ref=incoming.case_ref,
                    accounts=contribution.accounts,
                    total_ngn=contribution.total_ngn,
                    onward_bank=contribution.onward_bank,
                    cashout_cluster=contribution.cashout_cluster,
                    onward_hashes=contribution.onward_hashes,
                    view_id=contribution.view_id,
                )
            case protocol.RevokeContribution():
                revoke_contribution(self.cfg, incoming.terms_digest)
                return protocol.RoomDissolved(
                    case_ref=incoming.case_ref, terms_digest=incoming.terms_digest
                )
            case protocol.RoomDissolved():
                log.info("room dissolved for case %s", incoming.case_ref)
                return incoming
            case _:
                raise NotImplementedError(f"no handler for {incoming.kind}")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        log.info("cancel requested; negotiations are short-lived, nothing to do")
