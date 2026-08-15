"""Deterministic policy engine (invariant #2: LLMs propose, policy disposes).

Evaluates an InvestigationRequest / negotiated terms against this bank's YAML policy.
Pure code, pure functions — no model call can change a verdict. Every violated rule is
returned as a machine-readable id that goes into the PolicyVerdict and the audit log.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from services.bank.a2a.protocol import CounterProposal, InvestigationRequest
from services.bank.config import BankConfig

_POLICY_DIR = Path(__file__).parent / "bank_policies"


class PolicyRules(BaseModel):
    min_k_threshold: int
    max_ttl_hours: int
    allowed_computations: list[str]
    allowed_identifier_schemes: list[str]
    max_boundary_hashes: int
    require_case_ref: bool


class BankPolicy(BaseModel):
    version: str
    rules: PolicyRules


def load_policy(cfg: BankConfig) -> BankPolicy:
    raw = yaml.safe_load((_POLICY_DIR / f"{cfg.bank}.yaml").read_text())
    policy = BankPolicy.model_validate(raw)
    # A probe cap below our own k floor is unsatisfiable: we would demand aggregates over at
    # least k accounts while forbidding anyone to ask about that many. Catch it at load time
    # rather than letting negotiations loop forever against an impossible rule.
    if policy.rules.max_boundary_hashes < policy.rules.min_k_threshold:
        raise ValueError(
            f"{policy.version}: max_boundary_hashes ({policy.rules.max_boundary_hashes}) "
            f"< min_k_threshold ({policy.rules.min_k_threshold}) — no proposal could satisfy it"
        )
    return policy


def evaluate(policy: BankPolicy, req: InvestigationRequest) -> list[str]:
    """Return violated rule ids; empty list = compliant."""
    r = policy.rules
    violations: list[str] = []
    if req.k_threshold < r.min_k_threshold:
        violations.append(f"k_threshold_below_minimum:{r.min_k_threshold}")
    if req.ttl_hours > r.max_ttl_hours:
        violations.append(f"ttl_exceeds_maximum:{r.max_ttl_hours}")
    for comp in req.computations:
        if comp.kind not in r.allowed_computations:
            violations.append(f"computation_not_allowed:{comp.kind}")
    if req.identifier_scheme not in r.allowed_identifier_schemes:
        violations.append(f"identifier_scheme_not_allowed:{req.identifier_scheme}")
    if len(req.boundary_hashes) > r.max_boundary_hashes:
        violations.append(f"too_many_boundary_hashes:{r.max_boundary_hashes}")
    if r.require_case_ref and not req.case_ref.strip():
        violations.append("case_ref_required")
    return violations


def counter_terms(policy: BankPolicy, req: InvestigationRequest) -> CounterProposal | None:
    """If the request is negotiable (only threshold-type violations), produce the narrowest
    terms this bank WOULD accept. Non-negotiable violations (disallowed computation or
    identifier scheme) return None -> outright rejection."""
    violations = evaluate(policy, req)
    if not violations:
        return None  # nothing to counter — it's acceptable as-is
    # A probe that is too wide cannot be fixed by adjusting k or ttl — the initiator would
    # have to drop evidence — so it is an outright refusal, not a counter-offer.
    negotiable = ("k_threshold_below_minimum", "ttl_exceeds_maximum")
    if any(not v.startswith(negotiable) for v in violations):
        return None
    r = policy.rules
    return CounterProposal(
        bank="",  # filled by caller with cfg.bank
        case_ref=req.case_ref,
        round=req.round + 1,
        k_threshold=max(req.k_threshold, r.min_k_threshold),
        ttl_hours=min(req.ttl_hours, r.max_ttl_hours),
        computations=req.computations,
        note=f"terms adjusted to satisfy {policy.version}: {violations}",
    )
