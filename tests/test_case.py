import pytest

from services.bank.case import CaseState, Status


def make() -> CaseState:
    return CaseState(case_id="c1", bank="alpha")


def test_happy_path_transitions():
    c = make()
    path = [
        Status.TRACING,
        Status.DEAD_END,
        Status.DISCOVERING,
        Status.NEGOTIATING,
        Status.AGREED,
        Status.ROOM_ACTIVE,
        Status.JOINT_ANALYSIS,
        Status.AWAITING_APPROVAL,
        Status.ENFORCING,
        Status.CLOSED,
    ]
    for s in path:
        c.transition(s, "test")
    assert c.status == Status.CLOSED
    # every transition audit-logged
    assert len([a for a in c.audit if a.action.startswith("status:")]) == len(path)


def test_negotiating_can_loop_and_reject():
    c = make()
    for s in (Status.TRACING, Status.DEAD_END, Status.DISCOVERING, Status.NEGOTIATING):
        c.transition(s, "test")
    c.transition(Status.NEGOTIATING, "test", "counter-round")
    c.transition(Status.REJECTED, "test")
    assert c.status == Status.REJECTED


def test_illegal_transition_raises():
    c = make()
    with pytest.raises(ValueError, match="illegal transition"):
        c.transition(Status.ENFORCING, "test")
    # terminal states have no exits
    for s in (Status.TRACING, Status.CLOSED):
        c.transition(s, "test")
    with pytest.raises(ValueError):
        c.transition(Status.TRACING, "test")
