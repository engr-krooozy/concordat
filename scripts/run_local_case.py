"""Aug-17 checkpoint runner: one fleet investigates the golden ring locally.

Expected outcome: case ends DEAD_END with two boundary edges into meridian.

    BANK=alpha .venv/bin/python -m scripts.run_local_case
"""

import asyncio
import uuid

from services.bank.agents.fleet import run_investigation
from services.bank.case import CaseState
from services.bank.config import load_config

REPORT = (
    "Customer fraud report: account holder of ALP-9000001 reports approximately 2.4 million "
    "naira stolen via a web transfer they did not authorize on 2026-08-12 (afternoon, WAT). "
    "Investigate and trace where the funds went."
)


async def main() -> None:
    cfg = load_config()
    case = CaseState(case_id=f"case-{uuid.uuid4().hex[:8]}", bank=cfg.bank)
    case.log(f"{cfg.bank}/intake", "report", REPORT)
    await run_investigation(cfg, case, REPORT)

    print(f"\n=== case {case.case_id} [{cfg.bank}] -> {case.status} ===")
    print(f"victim txn: {case.victim_txn.txn_id if case.victim_txn else None}")
    print(f"trace length: {len(case.trace)} txns")
    for e in case.boundary_edges:
        print(
            f"boundary: {e.txn.txn_id} {e.txn.src_account} -> {e.txn.dst_account} "
            f"[{e.peer_bank}] {e.txn.amount:,.0f}"
        )
    print(f"summary: {case.summary}")
    print("\n--- audit trail ---")
    for a in case.audit:
        print(f"{a.ts:%H:%M:%S} {a.actor:<22} {a.action:<28} {a.detail[:80]}")


if __name__ == "__main__":
    asyncio.run(main())
