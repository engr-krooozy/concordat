"""Enforcement: acts ONLY inside our own perimeter, and only after a human approves.

The joint finding tells us a ring exists and how big it is. What we do about it is entirely
our own affair — we freeze our own accounts, file our own report. We never instruct a peer,
and we never learn which of their customers were involved.

Nothing here is irreversible, and the distinction is worth being precise about because the
guards below are usually justified by a claim this code cannot make. `enforce` builds a list
of strings and stores it. It calls no core banking system; no customer account is frozen by
running it, which is what makes it safe to exercise against the live deployment.

Two things ARE one-way. A case's status: `awaiting_approval -> enforcing -> closed`, and
`closed` has no outgoing transition, so an approved case never returns to the gate. And the
audit trail, which is append-only — a duplicate run writes thirty more entries into the one
record we ask people to trust.

The guards sit here anyway, because this is where the handoff would happen. A line reading
`freeze_and_review:ALP-910000` is exactly the payload a bank's core system would consume, and
freezing a customer's account twice is not a retry, it is a second incident. The idempotency
key belongs on the side of that boundary we control.

The staleness guard lives at the approval gate rather than here (see `orchestrator.approve`):
by the time we reach this function a human has already decided, and the right moment to tell
them their decision would rest on expired terms is before they make it, not after.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from services.bank.case import CaseState, Status
from services.bank.config import BankConfig

log = logging.getLogger("concordat.enforcer")


def enforcement_key(case: CaseState) -> str:
    """Stable for one approved case under one agreement, and different if either changes.

    The terms digest is in here deliberately: a case re-approved under a renegotiated
    concordat is a genuinely new decision and should stage its actions again.
    """
    digest = (case.concordat or {}).get("terms_digest", "")
    if not digest and case.concordat:
        # ConcordatSigned computes its digest rather than storing it; recompute the same way
        digest = hashlib.sha256(
            f"{case.concordat.get('k_threshold')}:{case.concordat.get('ttl_hours')}:"
            f"{case.concordat.get('identifier_scheme')}:{case.concordat.get('parties')}".encode()
        ).hexdigest()[:16]
    return hashlib.sha256(f"{case.case_id}:{digest}".encode()).hexdigest()[:16]


def concordat_expiry(case: CaseState) -> datetime | None:
    """When the agreement this case rests on stops being an agreement."""
    signed = (case.concordat or {}).get("signed_at")
    ttl = (case.concordat or {}).get("ttl_hours")
    if not signed or not ttl:
        return None
    try:
        stamp = datetime.fromisoformat(str(signed))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp + timedelta(hours=int(ttl))


def stale_reason(case: CaseState, now: datetime | None = None) -> str | None:
    """Why enforcing this case right now would be acting on something that no longer holds.

    A case can sit at the approval gate for as long as it takes a human to get to it, and the
    agreement underneath it cannot. The concordat carries a TTL the counterparties negotiated;
    the clean room built from it has already been dissolved. Approving after that point would
    have this bank freeze customer accounts on the authority of an expired agreement, which is
    precisely the thing every party signed the agreement to avoid.

    The finding does not evaporate — it was true when it was computed. What lapses is the
    permission to act on it, and the answer is to renegotiate, not to press on.
    """
    expiry = concordat_expiry(case)
    if expiry is None:
        return None
    now = now or datetime.now(UTC)
    if now <= expiry:
        return None
    overdue = now - expiry
    hours = overdue.total_seconds() / 3600
    return (
        f"the concordat expired {hours:.1f}h ago (signed "
        f"{(case.concordat or {}).get('signed_at')}, ttl "
        f"{(case.concordat or {}).get('ttl_hours')}h). The finding stands, but the terms "
        "permitting enforcement have lapsed — reopen the case to renegotiate."
    )


def enforce(cfg: BankConfig, case: CaseState, approver: str) -> list[str]:
    """Stage actions against our own flagged accounts. Deliberately not destructive: this
    writes the action list a bank's core system would execute, and audit-logs each one.

    Idempotent by key. A redelivered `case.approved` — which happens whenever this handler
    dies after staging and before closing, and the report it drafts is an LLM call that can
    fail — finds the work already done and returns it rather than doing it again.
    """
    key = enforcement_key(case)
    if case.enforcement_key == key and case.enforcement:
        log.info("%s: enforcement %s already staged; not repeating", cfg.bank, key)
        case.log(f"{cfg.bank}/enforcer", "enforcement:already_staged", key)
        return case.enforcement

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
    case.enforcement_key = key
    case.log(f"{cfg.bank}/enforcer", "approved_by", approver)
    log.info("%s staged %d enforcement actions (approved by %s)", cfg.bank, len(actions), approver)
    return actions


def close(cfg: BankConfig, case: CaseState) -> None:
    case.transition(
        Status.CLOSED,
        f"{cfg.bank}/enforcer",
        f"{len(case.enforcement)} actions staged in own perimeter",
    )
