"""Publish each fleet's catalog entry to Vertex AI Agent Engine, then read it back.

Run after a deploy that changes a fleet's URL. Registration is idempotent: an existing
entry for a bank is refreshed in place rather than duplicated, because a catalog with two
entries for the same bank is worse than a stale one.

    CLOUDSDK_ACTIVE_CONFIG_NAME=concordat .venv/bin/python -m scripts.register_agent_engine
"""

from __future__ import annotations

import subprocess

from services.bank.config import BANK_PREFIXES, project_for
from services.registry import agent_engine


def gcloud(*args: str) -> str:
    import os

    env = {**os.environ, "CLOUDSDK_ACTIVE_CONFIG_NAME": "concordat"}
    return subprocess.run(
        ["gcloud", *args], capture_output=True, text=True, env=env, check=True
    ).stdout.strip()


def fleet_url(bank: str) -> str:
    return gcloud(
        "run", "services", "describe", f"bank-{bank}", "--region=us-central1",
        f"--project={project_for(bank)}", "--format=value(status.url)",
    )


def main() -> None:
    for bank in BANK_PREFIXES:
        url = fleet_url(bank)
        name = agent_engine.register(bank, f"{url}/.well-known/agent-card.json")
        print(f"  {bank:9s} -> {name.split('/')[-1]}")

    print("\ncatalog as a peer sees it:")
    for bank, record in sorted(agent_engine.catalog().items()):
        print(f"  {bank:9s} {record['runtime']:28s} {record['card_url']}")


if __name__ == "__main__":
    main()
