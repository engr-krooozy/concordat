"""Local A2A smoke test: start bank-meridian on :8082, then as alpha's diplomat send a
Handshake over real A2A (card resolution + JSON-RPC) and print the ack.

    .venv/bin/python -m scripts.test_a2a_local
"""

import asyncio
import os
import subprocess
import sys
import time

import httpx


async def run() -> int:
    from services.bank.a2a import protocol
    from services.bank.agents.diplomat import Diplomat
    from services.bank.config import load_config

    os.environ["BANK"] = "alpha"
    cfg = load_config()
    diplomat = Diplomat(cfg, registry_url="http://localhost:9999")  # registry unused here

    reply = await diplomat.send(
        "http://localhost:8082/.well-known/agent-card.json",
        protocol.Handshake(bank="alpha", case_ref="ref-001", identifier_scheme="sha256_salted_v1"),
    )
    print(f"reply: {reply!r}")
    assert isinstance(reply, protocol.HandshakeAck), f"expected ack, got {type(reply)}"
    assert reply.bank == "meridian"
    print("A2A HANDSHAKE OK: alpha -> meridian over JSON-RPC")
    return 0


def main() -> None:
    env = {**os.environ, "BANK": "meridian", "PORT": "8082"}
    server = subprocess.Popen(
        [".venv/bin/uvicorn", "services.bank.api.main:app", "--port", "8082"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(60):
            try:
                if httpx.get("http://localhost:8082/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(1)
        else:
            print("server never became healthy", file=sys.stderr)
            sys.exit(1)
        sys.exit(asyncio.run(run()))
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
