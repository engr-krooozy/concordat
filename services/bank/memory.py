"""Cross-case memory, in Vertex AI Agent Engine's Memory Bank, sovereign to each bank.

Until now every investigation started from nothing. The fleet traced the same ring shape to
the same cash-out cluster on Tuesday that it had traced on Monday, and knew nothing about
Monday. That is not how a fraud analyst works, and it is not how an agent fleet should
either.

Two kinds of thing are worth remembering, and both of them are ours to keep:

**Ring shapes.** "A cash-out cluster concentrated N accounts across these banks." That comes
out of the joint finding, which is already k-thresholded aggregate — no bank contributed a
row to it, and nobody's customer is in it. Recalling it at the start of the next case gives
the investigator a prior: *we have seen this cluster before.*

**Counterparty behaviour.** "Meridian's policy engine has demanded k>=25 and ttl<=48 in
every negotiation so far." That is our own observation of a negotiation we took part in —
the same thing a human counterparty would remember about a bank they deal with weekly.

The memory bank lives in the bank's OWN project, beside its ledger and its case store. That
matters: a shared memory would leak one bank's investigative history to its rivals through
the back door, after all the trouble taken to keep the ledgers apart. Alpha remembers what
Alpha saw.

Failure here is never fatal. A fleet that cannot recall is a fleet that starts from nothing,
which is exactly where it started before — so every call fails soft and says so.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from services.bank.config import BankConfig

log = logging.getLogger("concordat.memory")

LOCATION = "us-central1"
RINGS = "fraud-rings"  # what a network looked like
COUNTERPARTIES = "counterparties"  # how a peer bank behaves


def _enabled() -> bool:
    return os.environ.get("AGENT_MEMORY", "on").lower() not in ("off", "0", "false")


def _endpoint() -> str:
    return f"{LOCATION}-aiplatform.googleapis.com"


@lru_cache(maxsize=4)
def _engine_name(bank: str, project: str) -> str | None:
    """The bank's memory engine, found by display name. Created by infra/setup_memory.sh."""
    from google.api_core.client_options import ClientOptions
    from google.cloud import aiplatform_v1beta1 as v1b

    from services.bank.auth import bank_credentials
    from services.bank.config import make_config

    client = v1b.ReasoningEngineServiceClient(
        credentials=bank_credentials(make_config(bank)),
        client_options=ClientOptions(api_endpoint=_endpoint()),
    )
    wanted = f"concordat-memory-{bank}"
    for engine in client.list_reasoning_engines(parent=f"projects/{project}/locations/{LOCATION}"):
        if engine.display_name == wanted:
            return engine.name
    log.warning(
        "no memory engine named %s in %s; the fleet will start from nothing", wanted, project
    )
    return None


def _memory_client(cfg: BankConfig):
    from google.api_core.client_options import ClientOptions
    from google.cloud import aiplatform_v1beta1 as v1b

    from services.bank.auth import bank_credentials

    return v1b.MemoryBankServiceClient(
        credentials=bank_credentials(cfg),
        client_options=ClientOptions(api_endpoint=_endpoint()),
    )


def remember(cfg: BankConfig, fact: str, domain: str = RINGS) -> bool:
    """Keep one fact. Returns whether it stuck."""
    if not _enabled() or not fact.strip():
        return False
    try:
        from google.cloud import aiplatform_v1beta1 as v1b

        parent = _engine_name(cfg.bank, cfg.project)
        if not parent:
            return False
        operation = _memory_client(cfg).create_memory(
            request=v1b.CreateMemoryRequest(
                parent=parent,
                memory=v1b.Memory(fact=fact, scope={"domain": domain}),
            )
        )
        operation.result(timeout=60)
        log.info("remembered (%s): %s", domain, fact[:90])
        return True
    except Exception as exc:  # noqa: BLE001 - a fleet that cannot remember still works
        log.warning("could not write memory (%s: %s)", type(exc).__name__, exc)
        return False


def recall(cfg: BankConfig, query: str, domain: str = RINGS, top_k: int = 3) -> list[str]:
    """Facts this bank has seen before that resemble the question. Empty on any failure."""
    if not _enabled() or not query.strip():
        return []
    try:
        from google.cloud import aiplatform_v1beta1 as v1b

        parent = _engine_name(cfg.bank, cfg.project)
        if not parent:
            return []
        response = _memory_client(cfg).retrieve_memories(
            request=v1b.RetrieveMemoriesRequest(
                parent=parent,
                scope={"domain": domain},
                similarity_search_params=v1b.RetrieveMemoriesRequest.SimilaritySearchParams(
                    search_query=query, top_k=top_k
                ),
            )
        )
        facts = [m.memory.fact for m in response.retrieved_memories]
        if facts:
            log.info("recalled %d prior fact(s) for %s", len(facts), domain)
        return facts
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read memory (%s: %s)", type(exc).__name__, exc)
        return []


def ring_fact(finding: dict) -> str:
    """One line describing a ring, built only from the k-thresholded joint finding.

    Everything here survived the clean room's aggregation threshold, so there is no
    individual in it to leak back out later.
    """
    banks = ", ".join(finding.get("banks_involved") or [])
    cluster = finding.get("cashout_cluster") or "an unnamed cash-out point"
    return (
        f"A mule network of {finding.get('mule_accounts', 0)} accounts spanning {banks} "
        f"concentrated {finding.get('total_ngn', 0):,.0f} NGN at {cluster}."
    )


def counterparty_fact(peer: str, k_threshold: int, ttl_hours: int, policy_version: str) -> str:
    """What a peer's policy engine actually demanded, as we observed it."""
    return (
        f"Bank {peer} ({policy_version}) settled at a minimum group size of {k_threshold} "
        f"and a room lifetime of {ttl_hours} hours."
    )
