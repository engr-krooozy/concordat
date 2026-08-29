"""The fleet catalog, held in Vertex AI Agent Engine's registry.

Discovery and execution are different problems, and this project answers them differently
on purpose.

**Execution stays sovereign.** Each bank's fleet runs on Cloud Run inside that bank's own
GCP project, under that bank's own service account, next to that bank's own ledger. Moving
the runtime to a managed service in a shared project would be the single fastest way to
destroy the thing this project is arguing for — a bank does not hand its fraud investigator
to a neutral party any more than it hands over its ledger.

**Cataloging is neutral ground**, and so it belongs to the commons. An agent registry holds
public facts: which fleets exist, what they can do, which identifier scheme they speak, and
the URL of the agent card describing them. None of that is anybody's customer data. So the
catalog is Vertex AI Agent Engine, in `concordat-hack`, with one registered entry per bank.

An entry is metadata only — no packaged code, no managed runtime. That is not a shortcut
around Agent Engine; it is the correct use of it here. The registry answers "who is out
there and where do I knock", and the knocking happens over A2A, directly, bank to bank,
with nothing in the middle.

Our own registry service stays as a fallback so a discovery outage cannot strand the
federation, exactly as it does for every other dependency in this system.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("concordat.registry.agent_engine")

COMMONS = "concordat-hack"
LOCATION = "us-central1"
PREFIX = "concordat-bank-"


def _init(credentials=None) -> None:
    import vertexai

    vertexai.init(project=COMMONS, location=LOCATION, credentials=credentials)


def _descriptor(bank: str, card_url: str, scheme: str) -> str:
    """What a peer needs in order to open a negotiation, and nothing else."""
    return json.dumps(
        {
            "bank": bank,
            "card_url": card_url,
            "identifier_scheme": scheme,
            "transport": "a2a-jsonrpc",
            "runtime": f"cloud-run:concordat-{bank}",
            "note": "runtime is sovereign to this bank; only the catalog entry is shared",
        }
    )


def register(bank: str, card_url: str, scheme: str = "sha256_salted_v1", credentials=None) -> str:
    """Register (or refresh) one bank's fleet in the catalog. Idempotent by display name."""
    from vertexai import agent_engines

    _init(credentials)
    display = f"{PREFIX}{bank}"
    description = _descriptor(bank, card_url, scheme)

    for existing in agent_engines.list():
        if existing.display_name == display:
            existing.update(display_name=display, description=description)
            log.info("refreshed catalog entry for %s", bank)
            return existing.resource_name

    created = agent_engines.create(display_name=display, description=description)
    log.info("registered %s in the Agent Engine catalog", bank)
    return created.resource_name


def catalog(credentials=None) -> dict[str, dict[str, Any]]:
    """Every registered fleet, by bank. Entries we did not write are ignored rather than
    guessed at — a malformed description is a registry problem, not a reason to fail."""
    from vertexai import agent_engines

    _init(credentials)
    out: dict[str, dict[str, Any]] = {}
    for entry in agent_engines.list():
        if not (entry.display_name or "").startswith(PREFIX):
            continue
        # the SDK wrapper exposes display_name but not description; the proto underneath has it
        description = getattr(entry.gca_resource, "description", "") or ""
        try:
            record = json.loads(description or "{}")
        except json.JSONDecodeError:
            log.warning("catalog entry %s has an unreadable description", entry.display_name)
            continue
        bank = record.get("bank")
        if bank and record.get("card_url"):
            record["resource_name"] = entry.resource_name
            out[bank] = record
    return out


def cards(credentials=None) -> dict[str, str]:
    """Bank -> agent-card URL: the shape the diplomat actually wants."""
    return {bank: rec["card_url"] for bank, rec in catalog(credentials).items()}
