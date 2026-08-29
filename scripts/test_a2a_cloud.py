"""Are the fleets awake and talking? Run this before filming or judging.

As alpha's diplomat, under the impersonated bank service account: discover counterpart
fleets through the Agent Engine catalog, then A2A-handshake each of them on Cloud Run. It
should return in a couple of seconds. If it pauses first, a retry is waiting out a peer that
has scaled to zero, and something has knocked min-instances back down.

    CLOUDSDK_ACTIVE_CONFIG_NAME=concordat .venv/bin/python -m scripts.test_a2a_cloud
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
    print(f"discovered: {sorted(peers)}")
    assert set(peers) == {"meridian", "union"}

    for bank, card_url in sorted(peers.items()):
        reply = await diplomat.send(
            card_url,
            protocol.Handshake(
                bank=cfg.bank, case_ref="ref-cloud-001", identifier_scheme="sha256_salted_v1"
            ),
        )
        assert isinstance(reply, protocol.HandshakeAck) and reply.bank == bank
        print(f"A2A handshake OK: alpha -> {bank} ({reply.policy_version})")
    print("CLOUD A2A DISCOVERY + HANDSHAKES: ALL OK")


if __name__ == "__main__":
    asyncio.run(main())
