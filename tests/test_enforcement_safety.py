"""The two guards on the step that would be irreversible in a real bank.

Enforcement here stages rather than executes: it writes `freeze_and_review:ALP-910000` into
the case and stops. Nobody's account is touched, which is exactly why these guards can be
tested against the live deployment at all.

They still matter, for two reasons that hold today. A case's status is one-way — `closed` has
no outgoing transition, so an approved case never returns to the gate. And the audit trail is
append-only, so a duplicate run corrupts the record we ask people to trust. Beyond that, the
staged line is the payload a core banking system would consume, and freezing an account twice
is not a retry but a second incident.

Both failure modes are quiet. Nothing errors; the wrong thing simply happens.
"""

from datetime import UTC, datetime, timedelta

import pytest

from services.bank.agents.enforcer import concordat_expiry, enforce, enforcement_key, stale_reason
from services.bank.case import BoundaryEdge, CaseState, Status
from services.bank.ledger import Txn
from tests.test_policy import cfg_for


def signed(hours_ago: float, ttl_hours: int = 48) -> dict:
    return {
        "kind": "concordat_signed",
        "signed_at": (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat(),
        "ttl_hours": ttl_hours,
        "k_threshold": 25,
        "identifier_scheme": "sha256_salted_v1",
        "parties": ["alpha", "meridian", "union"],
        "terms_digest": "d49fd29478fac5f1",
    }


def approved_case(concordat: dict | None = None) -> CaseState:
    case = CaseState(case_id="case-enf1", bank="alpha")
    case.boundary_edges = [
        BoundaryEdge(
            txn=Txn(
                txn_id=f"ALP-G{i}",
                ts="2026-08-12T13:27:00Z",
                src_account=f"ALP-91000{i}",
                dst_account=f"MER-92000{i}",
                src_bank="alpha",
                dst_bank="meridian",
                amount=100000.0,
                channel="transfer",
                narration="transfer",
            ),
            peer_bank="meridian",
        )
        for i in range(3)
    ]
    case.finding = {"cashout_cluster": "ATM-LAG-014", "mule_accounts": 30}
    case.concordat = concordat if concordat is not None else signed(hours_ago=1)
    return case


# ---------- idempotency ----------


def test_a_redelivered_approval_does_not_freeze_anything_twice():
    """The enforcement handler drafts a report with an LLM after staging actions and before
    closing the case. That call can fail, the case stays `enforcing`, and Pub/Sub redelivers.
    Without a key, the second attempt stages every freeze again — harmless here, a duplicate
    instruction to a core banking system anywhere real."""
    cfg, case = cfg_for("alpha"), approved_case()

    first = enforce(cfg, case, approver="analyst@alpha")
    second = enforce(cfg, case, approver="analyst@alpha")

    assert first == second
    assert len(case.enforcement) == len(first)
    freezes = [a for a in case.enforcement if a.startswith("freeze_and_review")]
    assert len(freezes) == len(set(freezes)), "an account was staged for freezing twice"


def test_the_second_attempt_says_so_in_the_audit():
    """A silent no-op and a completed run look identical afterwards. The audit has to
    distinguish them, or nobody can tell whether enforcement actually ran."""
    cfg, case = cfg_for("alpha"), approved_case()

    enforce(cfg, case, approver="analyst@alpha")
    enforce(cfg, case, approver="analyst@alpha")

    assert any(e.action == "enforcement:already_staged" for e in case.audit)


def test_a_renegotiated_agreement_is_a_new_decision():
    """Re-approving under different terms is not a retry — the key must change so the actions
    are staged again against the agreement that actually authorises them."""
    case = approved_case()
    before = enforcement_key(case)

    case.concordat = {**case.concordat, "terms_digest": "aaaaaaaaaaaaaaaa"}

    assert enforcement_key(case) != before


def test_the_key_is_stable_for_the_same_case_and_terms():
    case = approved_case()

    assert enforcement_key(case) == enforcement_key(case)


# ---------- staleness ----------


def test_a_fresh_concordat_permits_enforcement():
    assert stale_reason(approved_case(signed(hours_ago=1, ttl_hours=48))) is None


def test_approving_after_the_ttl_has_lapsed_is_refused():
    """The room this rests on dissolved two days ago. Acting on the authority of an expired
    agreement is the thing every party signed the agreement to avoid."""
    reason = stale_reason(approved_case(signed(hours_ago=72, ttl_hours=48)))

    assert reason is not None
    assert "expired" in reason
    assert "renegotiate" in reason


def test_the_refusal_says_the_finding_still_stands():
    """It was true when it was computed. What lapsed is permission to act on it, and telling
    an analyst their evidence evaporated would be both wrong and demoralising."""
    reason = stale_reason(approved_case(signed(hours_ago=100, ttl_hours=48)))

    assert "finding stands" in reason


def test_a_case_with_no_agreement_is_not_judged_stale():
    """Solo cases that closed without ever negotiating have no TTL to breach."""
    assert stale_reason(approved_case(concordat={})) is None
    assert concordat_expiry(approved_case(concordat={})) is None


def test_an_unparseable_signature_time_does_not_block_enforcement():
    """Fail open here: refusing every approval because a timestamp is malformed would be a
    worse failure than the one it guards against, and it would be invisible."""
    assert stale_reason(approved_case({**signed(1), "signed_at": "not a timestamp"})) is None


@pytest.mark.parametrize("ttl,hours,expected_stale", [(48, 47.5, False), (48, 48.5, True)])
def test_the_boundary_is_the_negotiated_ttl(ttl, hours, expected_stale):
    """Not a grace period of our own invention. The counterparties chose this number."""
    reason = stale_reason(approved_case(signed(hours_ago=hours, ttl_hours=ttl)))

    assert (reason is not None) is expected_stale


def test_the_gate_is_where_staleness_is_checked_not_the_enforcer():
    """By the time enforce() runs a human has already decided. The moment to tell them their
    decision would rest on expired terms is before they make it."""
    cfg = cfg_for("alpha")
    expired = approved_case(signed(hours_ago=72, ttl_hours=48))
    expired.transition(Status.TRACING, "t")

    # enforce() itself does not second-guess the gate; it stages what it was told to
    actions = enforce(cfg, expired, approver="analyst@alpha")

    assert actions, "enforce must not silently do nothing; the gate is the guard"
