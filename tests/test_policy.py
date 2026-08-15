import os

from services.bank.a2a.protocol import InvestigationRequest, JointComputation
from services.bank.config import BankConfig, make_config
from services.bank.policy.engine import counter_terms, evaluate, load_policy


def cfg_for(bank: str) -> BankConfig:
    """Same construction the services use, so tests exercise the real project wiring."""
    return make_config(bank, impersonate_locally=False)


def request(k: int = 10, ttl: int = 72, comp: str = "path_join", n_hashes: int = 2):
    return InvestigationRequest(
        bank="alpha",
        case_ref="c1",
        round=1,
        rationale="joint trace",
        computations=[JointComputation(kind=comp, description="d")],
        k_threshold=k,
        identifier_scheme="sha256_salted_v1",
        ttl_hours=ttl,
        boundary_hashes=["h"] * n_hashes,
        case_salt="s",
    )


def test_alpha_accepts_its_own_floor():
    assert evaluate(load_policy(cfg_for("alpha")), request(k=10)) == []


def test_meridian_counters_low_k_with_its_floor():
    policy = load_policy(cfg_for("meridian"))
    req = request(k=10)
    assert evaluate(policy, req) == [
        "k_threshold_below_minimum:25",
        "ttl_exceeds_maximum:48",
    ]
    counter = counter_terms(policy, req)
    assert counter is not None and counter.k_threshold == 25
    assert counter.ttl_hours == 48  # meridian also tightens ttl 72 -> 48
    assert counter.round == 2


def test_disallowed_scheme_is_outright_rejection():
    policy = load_policy(cfg_for("meridian"))
    req = request(k=30, ttl=48)
    req.identifier_scheme = "plaintext"
    assert counter_terms(policy, req) is None  # non-negotiable
    assert evaluate(policy, req) == ["identifier_scheme_not_allowed:plaintext"]


def test_converged_terms_pass_all_three_policies():
    # what the negotiation should converge to: k=25 (meridian's floor), ttl=48
    req = request(k=25, ttl=48)
    for bank in ("alpha", "meridian", "union"):
        assert evaluate(load_policy(cfg_for(bank)), req) == [], bank


def test_environment_independent(monkeypatch):
    monkeypatch.setenv("BANK", "alpha")
    os.environ.get("BANK")  # policies load from files, not env
    assert load_policy(cfg_for("union")).rules.min_k_threshold == 15
