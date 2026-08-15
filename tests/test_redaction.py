"""The perimeter gate. Rules are the guarantee, so they are tested without any model;
Gemma is tested only for how the gate behaves around its verdicts.
"""

import pytest

from services.bank.a2a import protocol
from services.bank.agents.diplomat import Diplomat, PayloadWithheld
from services.bank.redaction import rules
from services.bank.redaction.gate import gate
from tests.test_policy import cfg_for


def test_account_ids_never_survive_scrubbing():
    text = "Funds moved from ALP-9000001 to MER-920004 then out via UNI-930011."
    out = rules.scrub(text)
    assert "ALP-9000001" not in out.text and "MER-920004" not in out.text
    assert "UNI-930011" not in out.text
    assert any(f.startswith("account_id:3") for f in out.findings)


def test_quasi_identifiers_are_scrubbed():
    out = rules.scrub("2,400,000.00 NGN moved at 2026-08-12 13:02:00; ask fraud@alpha.example")
    assert out.findings
    joined = " ".join(out.findings)
    assert "exact_amount" in joined and "precise_timestamp" in joined and "email" in joined
    assert "2,400,000.00" not in out.text and "fraud@alpha.example" not in out.text


def test_benign_text_passes_untouched():
    text = "A cross-boundary laundering pattern is suspected; requesting a joint trace."
    out = rules.scrub(text)
    assert out.clean and out.text == text


def test_gate_blocks_when_local_model_still_sees_a_leak(monkeypatch):
    monkeypatch.setattr("services.bank.redaction.gemma.looks_like_leak", lambda _t: True)
    result = gate("Customer Adebayo moved money last night.")
    assert result.blocked and result.text == ""
    assert "gemma:residual_disclosure_risk" in result.findings


def test_gate_passes_when_local_model_agrees(monkeypatch):
    monkeypatch.setattr("services.bank.redaction.gemma.looks_like_leak", lambda _t: False)
    result = gate("Requesting a joint trace under agreed terms.")
    assert not result.blocked and result.gemma_checked


def test_gate_works_with_no_model_present(monkeypatch):
    monkeypatch.setattr("services.bank.redaction.gemma.looks_like_leak", lambda _t: None)
    result = gate("Account ALP-9000001 is implicated.")
    assert not result.blocked and not result.gemma_checked
    assert "ALP-9000001" not in result.text  # rules still did their job


def test_diplomat_redacts_before_sending(monkeypatch):
    monkeypatch.setattr("services.bank.redaction.gemma.looks_like_leak", lambda _t: None)
    diplomat = Diplomat(cfg_for("alpha"), registry_url="http://localhost")
    msg = protocol.InvestigationRequest(
        bank="alpha",
        case_ref="c1",
        round=1,
        rationale="Trace ALP-9000001 which sent 2,400,000.00 NGN offshore.",
        computations=[],
        k_threshold=25,
        identifier_scheme="sha256_salted_v1",
        ttl_hours=48,
        boundary_hashes=[],
        case_salt="a1b2c3d4e5f60718",
    )
    gated, findings = diplomat._gate_outbound(msg)
    assert "ALP-9000001" not in gated.rationale
    assert "2,400,000.00" not in gated.rationale
    assert any(f.startswith("rationale/") for f in findings)


def test_diplomat_refuses_to_send_a_blocked_payload(monkeypatch):
    monkeypatch.setattr("services.bank.redaction.gemma.looks_like_leak", lambda _t: True)
    diplomat = Diplomat(cfg_for("alpha"), registry_url="http://localhost")
    msg = protocol.CounterProposal(
        bank="meridian",
        case_ref="c1",
        round=2,
        k_threshold=25,
        ttl_hours=48,
        computations=[],
        note="customer Adebayo flagged",
    )
    with pytest.raises(PayloadWithheld):
        diplomat._gate_outbound(msg)
