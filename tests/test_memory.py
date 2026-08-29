"""Cross-case memory has to be useful and has to be safe, and the second one is load-bearing.

A memory bank is a place where data quietly accumulates outside the controls that guarded it
when it arrived. The whole system spends its effort making sure no individual crosses a
perimeter; it would be a poor trade to then write one into a store that outlives the case.

So: only aggregates go in, memory failures are never fatal, and one bank's memory is a
different bank's nothing.
"""

import pytest

from services.bank import memory
from tests.test_policy import cfg_for

FINDING = {
    "mule_accounts": 30,
    "banks_involved": ["alpha", "meridian", "union"],
    "total_ngn": 2316720.0,
    "cashout_cluster": "ATM-LAG-014",
    "hops": [
        {"bank": "alpha", "accounts": 30, "total_ngn": 2340240.0},
        {"bank": "meridian", "accounts": 30, "total_ngn": 2328480.0},
        {"bank": "union", "accounts": 30, "total_ngn": 2316720.0},
    ],
}


def test_a_remembered_ring_carries_no_individual():
    """Built from the k-thresholded finding only. Account ids exist nowhere in the finding,
    so they cannot reach memory — this asserts the shape of what we write, on purpose."""
    fact = memory.ring_fact(FINDING)

    assert "30 accounts" in fact
    assert "ATM-LAG-014" in fact
    assert "alpha, meridian, union" in fact
    for prefix in ("ALP-", "MER-", "UNI-"):
        assert prefix not in fact
    assert "@" not in fact


def test_a_ring_with_no_cluster_still_reads_as_a_sentence():
    """Half the value of a memory is that a model can use it. A dangling 'at None' is worse
    than saying plainly that the cash-out point was never identified."""
    fact = memory.ring_fact({**FINDING, "cashout_cluster": ""})

    assert "None" not in fact
    assert "unnamed cash-out point" in fact


def test_counterparty_memory_records_the_terms_not_the_ledger():
    """What we learn about a peer is how it negotiates, which we observed first-hand."""
    fact = memory.counterparty_fact("meridian", 25, 48, "meridian-policy-v1")

    assert "meridian" in fact and "25" in fact and "48" in fact
    assert "meridian-policy-v1" in fact


def test_memory_is_off_in_tests_and_fails_soft(monkeypatch):
    """The suite must not reach Vertex AI, and a fleet that cannot remember still works."""
    monkeypatch.setenv("AGENT_MEMORY", "off")
    cfg = cfg_for("alpha")

    assert memory.remember(cfg, "anything") is False
    assert memory.recall(cfg, "anything") == []


def test_an_unreachable_memory_bank_returns_nothing_rather_than_raising(monkeypatch):
    """Recall failing is a fleet starting from nothing, which is where it started before.
    Recall *raising* would take the whole investigation down with it."""
    monkeypatch.setenv("AGENT_MEMORY", "on")

    def explode(*_args, **_kwargs):
        raise RuntimeError("memory bank unreachable")

    monkeypatch.setattr(memory, "_engine_name", explode)
    cfg = cfg_for("alpha")

    assert memory.recall(cfg, "an ATM cluster in Lagos") == []
    assert memory.remember(cfg, "a fact worth keeping") is False


def test_the_two_domains_stay_separate():
    """Ring shapes and counterparty behaviour are retrieved for different questions; mixing
    them would put 'meridian settles at k=25' into an investigator's evidence."""
    assert memory.RINGS != memory.COUNTERPARTIES


@pytest.mark.parametrize("bank", ["alpha", "meridian", "union"])
def test_each_bank_remembers_inside_its_own_project(bank):
    """The point of the whole architecture. A shared memory bank would hand one bank's
    investigative history to its rivals after all the work of keeping the ledgers apart."""
    cfg = cfg_for(bank)

    assert cfg.project == f"concordat-{bank}"
