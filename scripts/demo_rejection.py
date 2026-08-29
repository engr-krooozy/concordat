"""The governance path: what happens when a fleet asks for too much.

Sends three genuinely over-broad proposals to the live Meridian fleet and prints its
policy engine's answers. Nothing is mocked — these are real A2A calls to the deployed
service, refused by the same evaluator that governs the golden path.

    .venv/bin/python -m scripts.demo_rejection
"""

import asyncio
import os

REGISTRY_URL = "https://registry-fa7ntw3nkq-uc.a.run.app"


async def main() -> None:
    os.environ["BANK"] = "alpha"
    from services.bank.a2a import protocol
    from services.bank.agents.diplomat import Diplomat
    from services.bank.config import load_config

    cfg = load_config()
    diplomat = Diplomat(cfg, registry_url=REGISTRY_URL)
    peers = await diplomat.discover()
    meridian = peers["meridian"]

    def request(**overrides) -> protocol.InvestigationRequest:
        base = {
            "bank": "alpha",
            "case_ref": "case-governance-demo",
            "round": 1,
            "rationale": "Requesting a joint trace of a suspected cross-boundary network.",
            "computations": [
                protocol.JointComputation(kind="path_join", description="follow hashed accounts")
            ],
            "k_threshold": 25,
            "identifier_scheme": "sha256_salted_v1",
            "ttl_hours": 48,
            "boundary_hashes": [f"{i:064x}" for i in range(30)],
            "case_salt": "a1b2c3d4e5f60718",
        }
        return protocol.InvestigationRequest(**{**base, **overrides})

    probes = [
        (
            "a probe far wider than policy permits (200 accounts)",
            request(boundary_hashes=[f"{i:064x}" for i in range(200)]),
        ),
        ("plaintext identifiers instead of salted hashes", request(identifier_scheme="plaintext")),
        ("an aggregate group size below the privacy floor (k=2)", request(k_threshold=2)),
    ]

    print("=== Meridian's policy engine, asked for things it should refuse ===\n")
    for description, proposal in probes:
        reply = await diplomat.send(meridian, proposal)
        if isinstance(reply, protocol.PolicyVerdict):
            print(f"  ASK:      {description}")
            print(f"  ANSWER:   {reply.verdict.upper()} — {', '.join(reply.violated_rules)}\n")
        elif isinstance(reply, protocol.CounterProposal):
            print(f"  ASK:      {description}")
            print(f"  ANSWER:   COUNTER-OFFER — k={reply.k_threshold} ttl={reply.ttl_hours}h")
            print(f"            ({reply.note})\n")
        else:
            print(f"  ASK:      {description}\n  ANSWER:   unexpected {reply.kind}\n")

    print("No data moved in any of these exchanges. The refusals come from a deterministic")
    print("policy evaluator, so no phrasing of the request could have talked it round.")


if __name__ == "__main__":
    asyncio.run(main())
