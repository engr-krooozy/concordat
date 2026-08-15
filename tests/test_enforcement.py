from services.bank.agents.enforcer import close, enforce
from services.bank.case import Status
from tests.test_negotiation import dead_end_case
from tests.test_policy import cfg_for


def approved_case():
    case = dead_end_case()
    for s in (
        Status.DISCOVERING,
        Status.NEGOTIATING,
        Status.AGREED,
        Status.ROOM_ACTIVE,
        Status.JOINT_ANALYSIS,
        Status.AWAITING_APPROVAL,
        Status.ENFORCING,
    ):
        case.transition(s, "test")
    case.finding = {"cashout_cluster": "ATM-LAG-014", "mule_accounts": 30}
    return case


def test_enforcement_touches_only_own_accounts():
    case = approved_case()
    actions = enforce(cfg_for("alpha"), case, approver="analyst@alpha")
    frozen = [a.split(":", 1)[1] for a in actions if a.startswith("freeze_and_review:")]
    assert frozen, "expected at least one account frozen"
    # every frozen account is ours; peers' customers are never named
    assert all(acct.startswith("ALP-") for acct in frozen), frozen
    assert any(a.startswith("file_sar_with_regulator:") for a in actions)


def test_enforcement_is_audit_logged_with_approver():
    case = approved_case()
    enforce(cfg_for("alpha"), case, approver="analyst@alpha")
    entries = [a for a in case.audit if a.actor == "alpha/enforcer"]
    assert len(entries) == len(case.enforcement) + 1  # actions + approver record
    assert any("analyst@alpha" in a.detail for a in entries)


def test_close_requires_enforcing_state():
    case = approved_case()
    enforce(cfg_for("alpha"), case, approver="a")
    close(cfg_for("alpha"), case)
    assert case.status is Status.CLOSED
