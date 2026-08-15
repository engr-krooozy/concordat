"""Enforcement: acts ONLY inside our own perimeter, and only after a human approves.

The joint finding tells us a ring exists and how big it is. What we do about it is entirely
our own affair — we freeze our own accounts, file our own report. We never instruct a peer,
and we never learn which of their customers were involved.
"""

from __future__ import annotations

import logging

from services.bank.case import CaseState, Status
from services.bank.config import BankConfig

log = logging.getLogger("concordat.enforcer")


def enforce(cfg: BankConfig, case: CaseState, approver: str) -> list[str]:
    """Stage actions against our own flagged accounts. Deliberately not destructive: this
    writes the action list a bank's core system would execute, and audit-logs each one.
    """
    own_accounts = sorted({e.txn.src_account for e in case.boundary_edges})
    actions = [f"freeze_and_review:{acct}" for acct in own_accounts]
    if case.victim_txn:
        actions.append(f"open_reimbursement_claim:{case.victim_txn.src_account}")
    if case.finding:
        cluster = case.finding.get("cashout_cluster", "unknown")
        actions.append(f"file_sar_with_regulator:cluster={cluster}")

    for action in actions:
        case.log(f"{cfg.bank}/enforcer", "action", action)
    case.enforcement = actions
    case.log(f"{cfg.bank}/enforcer", "approved_by", approver)
    log.info("%s staged %d enforcement actions (approved by %s)", cfg.bank, len(actions), approver)
    return actions


def close(cfg: BankConfig, case: CaseState) -> None:
    case.transition(
        Status.CLOSED,
        f"{cfg.bank}/enforcer",
        f"{len(case.enforcement)} actions staged in own perimeter",
    )
