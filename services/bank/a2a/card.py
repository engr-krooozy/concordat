"""This bank's A2A agent card — the capability statement other fleets discover.

The card is the standard A2A proto served at /.well-known/agent-card.json. It advertises
the joint-investigation skill and the identifier scheme; it does NOT reveal anything about
our ledger contents (opacity is the point of A2A).
"""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from google.protobuf import json_format

from services.bank.config import BankConfig

IDENTIFIER_SCHEME = "sha256_salted_v1"


def build_card(cfg: BankConfig, base_url: str) -> AgentCard:
    return AgentCard(
        name=f"concordat-bank-{cfg.bank}",
        description=(
            f"Sovereign fraud-investigation fleet of bank '{cfg.bank}'. Negotiates "
            "privacy-safe joint investigations; never exposes raw ledger data."
        ),
        version="0.1.0",
        supported_interfaces=[
            AgentInterface(url=f"{base_url}/a2a", protocol_binding="JSONRPC"),
        ],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id="joint-trace-negotiation",
                name="Joint fund-trace negotiation",
                description=(
                    "Negotiate terms (computations, k-anonymity threshold, TTL) for a "
                    f"clean-room joint fund trace. Identifier scheme: {IDENTIFIER_SCHEME}. "
                    "Proposals are evaluated by a deterministic policy engine."
                ),
                tags=["fraud", "negotiation", "clean-room", IDENTIFIER_SCHEME],
            ),
        ],
    )


def card_json(cfg: BankConfig, base_url: str) -> dict:
    return json_format.MessageToDict(build_card(cfg, base_url), preserving_proto_field_name=False)
