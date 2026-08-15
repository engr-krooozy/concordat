"""Joint analysis: assemble the cross-bank picture from the k-thresholded contributions
each party wrote into the room.

Nothing here touches bank data. By the time a row reaches the room, BigQuery has already
guaranteed it describes at least k distinct accounts — so the room joins only safe outputs,
and the ring is revealed exactly to the degree the parties agreed it could be.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

log = logging.getLogger("concordat.cleanroom.query")


class RingFinding(BaseModel):
    """The joint conclusion — the thing no single bank could reach alone."""

    hops: list[dict]  # per-bank: accounts, total, destination
    mule_accounts: int  # widest layer observed
    total_ngn: float  # value at the terminal hop
    cashout_cluster: str
    banks_involved: list[str]

    def headline(self) -> str:
        chain = " -> ".join(h["bank"] for h in self.hops)
        return (
            f"{self.mule_accounts} mule accounts across {chain}; "
            f"{self.total_ngn:,.0f} NGN concentrated at {self.cashout_cluster}"
        )


def assemble(contributions: list) -> RingFinding | None:
    """Build the finding from ordered per-bank contributions (initiator first)."""
    live = [c for c in contributions if c.accounts > 0]
    if not live:
        log.warning("no contribution survived its k threshold — nothing may be revealed")
        return None
    terminal = live[-1]
    return RingFinding(
        hops=[
            {
                "bank": c.bank,
                "accounts": c.accounts,
                "total_ngn": c.total_ngn,
                "cashout_cluster": c.cashout_cluster,
            }
            for c in live
        ],
        mule_accounts=max(c.accounts for c in live),
        total_ngn=terminal.total_ngn,
        cashout_cluster=terminal.cashout_cluster or "unknown",
        banks_involved=[c.bank for c in live],
    )
