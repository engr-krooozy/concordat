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

from services.bank.a2a import protocol
from services.bank.a2a.card import IDENTIFIER_SCHEME
from services.bank.config import BankConfig

log = logging.getLogger("concordat.a2a")


class NegotiationExecutor(AgentExecutor):
    def __init__(self, cfg: BankConfig):
        self.cfg = cfg

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
        match incoming:
            case protocol.Handshake():
                log.info("handshake from %s (case %s)", incoming.bank, incoming.case_ref)
                return protocol.HandshakeAck(
                    bank=self.cfg.bank,
                    identifier_scheme=IDENTIFIER_SCHEME,
                    policy_version="policy-v1",  # real policy digest lands with the engine
                )
            case _:
                raise NotImplementedError(f"handler for {incoming.kind} lands in Phase 2 day 2")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        log.info("cancel requested; negotiations are short-lived, nothing to do")
