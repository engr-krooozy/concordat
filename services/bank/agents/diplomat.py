"""Diplomat: cross-perimeter communication for the fleet. Discovers counterpart fleets via
the registry, resolves their A2A cards, and exchanges negotiation messages. All outbound
payloads pass the perimeter gate before leaving: deterministic rules redact, then a Gemma
running locally in this container gives a second opinion.

Auth: Cloud Run services are private; outbound calls attach an OIDC identity token minted
for the bank SA, and each bank grants run.invoker to its peers — modeling 'banks accept
authenticated requests from known counterparts'.
"""

from __future__ import annotations

import logging

import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest
from google.auth import impersonated_credentials

from services.bank.a2a import protocol
from services.bank.auth import bank_credentials
from services.bank.config import BankConfig
from services.bank.redaction.gate import gate

log = logging.getLogger("concordat.diplomat")

# Free-text fields are the only place a customer detail can hide; everything else in the
# protocol is hashes, enums and numbers that the policy engine has already constrained.
FREE_TEXT_FIELDS = ("rationale", "note", "description")


class PayloadWithheld(RuntimeError):
    """The perimeter gate refused to let a payload leave."""


def _id_token(cfg: BankConfig, audience: str) -> str:
    """OIDC identity token AS the bank service account for a peer's Cloud Run audience.

    Locally we mint it via impersonation; on Cloud Run the ambient identity IS the bank SA,
    so the metadata server issues it directly.
    """
    request = google.auth.transport.requests.Request()
    if cfg.impersonate_locally:
        creds = impersonated_credentials.IDTokenCredentials(
            bank_credentials(cfg), target_audience=audience, include_email=True
        )
        creds.refresh(request)
        return creds.token
    from google.oauth2 import id_token as id_token_mod

    return id_token_mod.fetch_id_token(request, audience)


class Diplomat:
    def __init__(self, cfg: BankConfig, registry_url: str):
        self.cfg = cfg
        self.registry_url = registry_url.rstrip("/")
        self.last_gate_findings: list[str] = []
        self.last_gate_summary: str = ""

    def _gate_outbound(
        self, msg: protocol.NegotiationMessage
    ) -> tuple[protocol.NegotiationMessage, list[str]]:
        """Scrub every free-text field. A blocked field aborts the send outright: we would
        rather stall a negotiation than leak a customer across an institutional boundary.
        """
        findings: list[str] = []
        summaries: list[str] = []
        updates: dict[str, str] = {}
        for field in FREE_TEXT_FIELDS:
            value = getattr(msg, field, None)
            if not isinstance(value, str) or not value.strip():
                continue
            result = gate(value)
            findings.extend(f"{field}/{f}" for f in result.findings)
            summaries.append(f"{field}: {result.audit_detail()}")
            if result.blocked:
                raise PayloadWithheld(
                    f"perimeter gate withheld {msg.kind}.{field}: {result.findings}"
                )
            if result.text != value:
                updates[field] = result.text
        self.last_gate_summary = "; ".join(summaries)
        if updates:
            msg = msg.model_copy(update=updates)
            log.info("perimeter gate redacted %s in %s", sorted(updates), msg.kind)
        return msg, findings

    async def _authed_httpx(self, audience: str) -> httpx.AsyncClient:
        if "localhost" in audience or "127.0.0.1" in audience:  # local dev: no Cloud Run IAM
            return httpx.AsyncClient(timeout=60)
        token = _id_token(self.cfg, audience)
        return httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=60)

    async def discover(self) -> dict[str, str]:
        """Peer bank -> agent-card URL, from the registry catalog."""
        async with await self._authed_httpx(self.registry_url) as client:
            resp = await client.get(f"{self.registry_url}/cards")
            resp.raise_for_status()
        peers = {c["bank"]: c["card_url"] for c in resp.json() if c["bank"] != self.cfg.bank}
        log.info("discovered %d counterpart fleets: %s", len(peers), sorted(peers))
        return peers

    async def send(
        self, card_url: str, msg: protocol.NegotiationMessage
    ) -> protocol.NegotiationMessage:
        """Send one negotiation message over A2A; return the counterpart's reply.

        Every free-text field passes the perimeter gate first — Gemma runs locally here, so
        the text being checked for leaks never leaves the bank to be checked.
        """
        msg, self.last_gate_findings = self._gate_outbound(msg)
        base = card_url.split("/.well-known/")[0]  # create_client appends the well-known path
        httpx_client = await self._authed_httpx(base)
        try:
            client = await create_client(base, ClientConfig(httpx_client=httpx_client))
            request = SendMessageRequest(
                message=Message(
                    message_id=f"{self.cfg.bank}-{msg.kind}",
                    role=Role.ROLE_USER,
                    parts=[Part(text=protocol.dump(msg))],
                )
            )
            async for response in client.send_message(request):
                reply_msg = response.message if response.HasField("message") else None
                if reply_msg and reply_msg.parts:
                    return protocol.parse(reply_msg.parts[0].text)
            raise RuntimeError("no reply message in A2A response stream")
        finally:
            await httpx_client.aclose()
