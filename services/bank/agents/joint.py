"""Initiator-side joint analysis: compile the signed concordat into a room, walk the chain
of peer contributions over A2A, assemble the finding, then tear the room down.

The initiator never sees a peer's rows — only receipts BigQuery has already thresholded.
The chain order is discovered, not configured: each receipt names where the money went next.
"""

from __future__ import annotations

import logging

from services.bank.a2a import protocol
from services.bank.a2a.hashing import hash_account
from services.bank.agents.diplomat import Diplomat
from services.bank.auth import room_runner_credentials
from services.bank.case import CaseState, Status
from services.bank.config import BankConfig
from services.cleanroom.compiler import (
    Contribution,
    create_room,
    dissolve_room,
    initiator_contribution,
)
from services.cleanroom.query import assemble

log = logging.getLogger("concordat.joint")

MAX_HOPS = 4


def _grant_writers(project: str, room_id: str, credentials) -> None:
    from google.cloud import bigquery

    client = bigquery.Client(project=project, credentials=credentials)
    ds = client.get_dataset(room_id)
    entries = list(ds.access_entries)
    for bank in ("alpha", "meridian", "union"):
        entry = bigquery.AccessEntry(
            "WRITER", "userByEmail", f"sa-bank-{bank}@{project}.iam.gserviceaccount.com"
        )
        if entry not in entries:
            entries.append(entry)
    ds.access_entries = entries
    client.update_dataset(ds, ["access_entries"])


async def run_joint_analysis(cfg: BankConfig, case: CaseState, diplomat: Diplomat) -> None:
    """AGREED -> ROOM_ACTIVE -> JOINT_ANALYSIS -> AWAITING_APPROVAL."""
    signed = protocol.ConcordatSigned.model_validate(case.concordat)
    digest = signed.terms_digest()
    creds = room_runner_credentials(cfg)

    room_id = create_room(cfg.project, digest, signed.ttl_hours, creds)
    _grant_writers(cfg.project, room_id, creds)
    room_ds = room_id.split(".")[-1]
    case.transition(
        Status.ROOM_ACTIVE,
        f"{cfg.bank}/cleanroom",
        f"room={room_ds} ttl={signed.ttl_hours}h k={signed.k_threshold}",
    )

    # our own hop: the mule accounts our trace flagged, hashed
    own_hashes = sorted(
        {hash_account(case.case_salt, e.txn.src_account) for e in case.boundary_edges}
    )
    window = ("2026-08-12 00:00:00", "2026-08-13 00:00:00")
    contributions: list[Contribution] = [
        initiator_contribution(cfg, case.case_salt, window[0], window[1], own_hashes)
    ]
    case.transition(
        Status.JOINT_ANALYSIS,
        f"{cfg.bank}/cleanroom",
        f"own hop: {contributions[0].accounts} accounts",
    )

    peers = await diplomat.discover()
    probe = contributions[0].onward_hashes
    next_bank = contributions[0].onward_bank
    visited: set[str] = {cfg.bank}

    for _ in range(MAX_HOPS):
        if not probe or next_bank not in peers or next_bank in visited:
            break
        request = protocol.ContributionRequest(
            bank=cfg.bank,
            case_ref=case.case_id,
            terms_digest=digest,
            k_threshold=signed.k_threshold,
            identifier_scheme=signed.identifier_scheme,
            case_salt=case.case_salt,
            window_start=window[0],
            window_end=window[1],
            room_dataset=room_ds,
            room_runner=f"sa-cleanroom@{cfg.project}.iam.gserviceaccount.com",
            probe_hashes=probe,
        )
        case.negotiation_transcript.append(
            {
                "direction": "sent",
                "peer": next_bank,
                "message": {
                    **request.model_dump(mode="json"),
                    "probe_hashes": f"[{len(probe)} hashes]",
                },
            }
        )
        receipt = await diplomat.send(peers[next_bank], request)
        if not isinstance(receipt, protocol.ContributionReceipt):
            log.warning("unexpected reply to contribution request: %s", receipt.kind)
            break
        case.negotiation_transcript.append(
            {
                "direction": "received",
                "peer": receipt.bank,
                "message": {
                    **receipt.model_dump(mode="json"),
                    "onward_hashes": f"[{len(receipt.onward_hashes)} hashes]",
                },
            }
        )
        case.log(
            f"{cfg.bank}/cleanroom",
            "contribution",
            f"{receipt.bank}: {receipt.accounts} accounts, {receipt.total_ngn:,.0f} NGN"
            + (f", cluster {receipt.cashout_cluster}" if receipt.cashout_cluster else ""),
        )
        if receipt.refused:
            case.log(
                f"{cfg.bank}/cleanroom",
                "contribution_refused",
                f"{receipt.bank}: {receipt.refused}",
            )
            break
        contributions.append(
            Contribution(
                bank=receipt.bank,
                view_id=receipt.view_id,
                aggregate_table="",
                accounts=receipt.accounts,
                total_ngn=receipt.total_ngn,
                onward_hashes=receipt.onward_hashes,
                cashout_cluster=receipt.cashout_cluster,
                onward_bank=receipt.onward_bank,
            )
        )
        visited.add(receipt.bank)
        probe, next_bank = receipt.onward_hashes, receipt.onward_bank

    finding = assemble(contributions)
    case.contributions = [
        c.model_dump(mode="json", exclude={"onward_hashes"}) for c in contributions
    ]
    if finding:
        case.finding = finding.model_dump(mode="json")
        case.log(f"{cfg.bank}/cleanroom", "joint_finding", finding.headline())

    # the room's work is done: revoke peer contributions, drop the room
    for c in contributions[1:]:
        await diplomat.send(
            peers[c.bank],
            protocol.RevokeContribution(case_ref=case.case_id, terms_digest=digest),
        )
    dissolve_room(cfg.project, digest, creds)
    case.log(f"{cfg.bank}/cleanroom", "room_dissolved", f"digest={digest}")

    case.transition(
        Status.AWAITING_APPROVAL,
        f"{cfg.bank}/cleanroom",
        "analyst approval required before enforcement",
    )
