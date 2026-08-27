"""A peer bank is allowed to be asleep.

Cloud Run answers for a scaled-to-zero service with a 500 before the container exists, and
the A2A client reports that as a failure to resolve the agent card. That happened three
times in eight unattended runs, and each time the case was stranded in `negotiating`
forever: the handler died after the status had already moved, and the Pub/Sub redelivery
was then turned away by a guard that only accepted `dead_end`.

Two defences, one test file: wait the peer out, and if the attempt dies anyway, let the
redelivery pick the case back up.
"""

import httpx
import pytest

from services.bank.a2a.executor import NegotiationExecutor
from services.bank.agents import diplomat as diplomat_mod
from services.bank.case import RESUMABLE_FROM, VALID_TRANSITIONS, Status
from tests.test_negotiation import StubDiplomat, dead_end_case
from tests.test_policy import cfg_for


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    async def fake_rationale(cfg, case):
        return "redacted rationale"

    monkeypatch.setattr("services.bank.agents.negotiation._draft_rationale", fake_rationale)


@pytest.fixture(autouse=True)
def instant_backoff(monkeypatch):
    monkeypatch.setattr(diplomat_mod, "RETRY_DELAYS", (0, 0, 0))


def cold_start_error() -> httpx.HTTPStatusError:
    """What Cloud Run returns while an instance is still starting."""
    request = httpx.Request("GET", "https://bank-meridian.example/.well-known/agent-card.json")
    return httpx.HTTPStatusError(
        "Server error '500 Internal Server Error'",
        request=request,
        response=httpx.Response(500, request=request),
    )


async def test_retry_waits_out_a_cold_peer():
    attempts = []

    async def attempt():
        attempts.append(1)
        if len(attempts) < 3:
            raise cold_start_error()
        return "card"

    assert await diplomat_mod._with_retry(attempt, "agent card") == "card"
    assert len(attempts) == 3


async def test_retry_does_not_mask_a_real_refusal():
    """A 403 is a peer saying no. Retrying it would turn a governance signal into a hang."""

    async def attempt():
        request = httpx.Request("GET", "https://bank-meridian.example/a2a")
        raise httpx.HTTPStatusError(
            "403", request=request, response=httpx.Response(403, request=request)
        )

    with pytest.raises(httpx.HTTPStatusError):
        await diplomat_mod._with_retry(attempt, "agent card")


class FlakyDiplomat(StubDiplomat):
    """Dies on the first outbound proposal, exactly as an unreachable peer did."""

    def __init__(self, peers, fail_on: int = 1):
        super().__init__(peers)
        self.fail_on = fail_on
        self.sends = 0

    async def send(self, card_url: str, msg):
        self.sends += 1
        if self.sends == self.fail_on:
            raise RuntimeError("agent card unreachable: peer is cold")
        return await super().send(card_url, msg)


async def test_interrupted_negotiation_resumes_on_redelivery():
    from services.bank.agents.negotiation import negotiate

    peers = {b: NegotiationExecutor(cfg_for(b)) for b in ("meridian", "union")}
    diplomat = FlakyDiplomat(peers)
    case = dead_end_case()
    cfg = cfg_for("alpha")

    with pytest.raises(RuntimeError):
        await negotiate(cfg, case, diplomat)

    # this is the state the three stranded cases were found in
    assert case.status is Status.NEGOTIATING

    signed = await negotiate(cfg, case, diplomat)

    assert signed is not None
    assert case.status is Status.AGREED
    assert signed.k_threshold == 25 and signed.ttl_hours == 48
    # the interrupted attempt stays in the record rather than being quietly overwritten
    assert any(e.action == "negotiation:restart" for e in case.audit)


def test_a_stranded_case_is_reachable_by_its_own_handler():
    """The guard and the state machine have to agree, or a redelivery is a silent no-op."""
    for status in RESUMABLE_FROM["negotiate"] - {Status.DEAD_END}:
        assert Status.NEGOTIATING in VALID_TRANSITIONS[status], status
    for status in RESUMABLE_FROM["joint_analysis"]:
        assert VALID_TRANSITIONS[status], status
    assert Status.NEGOTIATING in RESUMABLE_FROM["negotiate"]
    assert Status.ROOM_ACTIVE in RESUMABLE_FROM["joint_analysis"]
