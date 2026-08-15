"""Policies must be satisfiable, and unsatisfiable ones must fail loudly at load time.

This exists because a shipped policy capping probes at 20 hashes while demanding k>=25
sent a live negotiation into an endless counter-offer loop.
"""

import pytest
import yaml

from services.bank.policy.engine import _POLICY_DIR, BankPolicy, load_policy
from tests.test_policy import cfg_for


def test_every_shipped_policy_is_satisfiable():
    for bank in ("alpha", "meridian", "union"):
        rules = load_policy(cfg_for(bank)).rules
        assert rules.max_boundary_hashes >= rules.min_k_threshold, bank


def test_incoherent_policy_is_rejected_at_load(tmp_path, monkeypatch):
    raw = yaml.safe_load((_POLICY_DIR / "meridian.yaml").read_text())
    raw["rules"]["max_boundary_hashes"] = raw["rules"]["min_k_threshold"] - 1
    bad = tmp_path / "meridian.yaml"
    bad.write_text(yaml.safe_dump(raw))
    monkeypatch.setattr("services.bank.policy.engine._POLICY_DIR", tmp_path)
    with pytest.raises(ValueError, match="no proposal could satisfy"):
        load_policy(cfg_for("meridian"))


def test_the_golden_path_probe_width_is_acceptable_everywhere():
    # the ring is 30 accounts wide; every bank must permit a probe that size
    for bank in ("alpha", "meridian", "union"):
        assert load_policy(cfg_for(bank)).rules.max_boundary_hashes >= 30, bank


def test_model_still_validates_shape():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BankPolicy.model_validate({"version": "x", "rules": {"min_k_threshold": 1}})
