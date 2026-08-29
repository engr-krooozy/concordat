"""Create one memory-enabled Agent Engine per bank, in that bank's own project.

Idempotent: a bank that already has `concordat-memory-<bank>` is left alone, because a
second engine would silently split the fleet's memory in half.

    CLOUDSDK_ACTIVE_CONFIG_NAME=concordat .venv/bin/python -m scripts.setup_memory_engines
"""

from __future__ import annotations

from google.api_core.client_options import ClientOptions
from google.cloud import aiplatform_v1beta1 as v1b

from services.bank.auth import bank_credentials
from services.bank.config import BANK_PREFIXES, make_config
from services.bank.memory import LOCATION


def main() -> None:
    for bank in BANK_PREFIXES:
        cfg = make_config(bank)
        client = v1b.ReasoningEngineServiceClient(
            credentials=bank_credentials(cfg),
            client_options=ClientOptions(api_endpoint=f"{LOCATION}-aiplatform.googleapis.com"),
        )
        parent = f"projects/{cfg.project}/locations/{LOCATION}"
        display = f"concordat-memory-{bank}"

        existing = [e for e in client.list_reasoning_engines(parent=parent)
                    if e.display_name == display]
        if existing:
            print(f"  {bank:9s} already remembers -> {existing[0].name.split('/')[-1]}")
            continue

        engine = v1b.ReasoningEngine(
            display_name=display,
            description=f"Cross-case memory for bank {bank}'s fleet. Sovereign to {bank}.",
            context_spec=v1b.ReasoningEngineContextSpec(
                memory_bank_config=v1b.ReasoningEngineContextSpec.MemoryBankConfig()
            ),
        )
        created = client.create_reasoning_engine(
            parent=parent, reasoning_engine=engine
        ).result(timeout=600)
        print(f"  {bank:9s} -> {created.name.split('/')[-1]}")


if __name__ == "__main__":
    main()
