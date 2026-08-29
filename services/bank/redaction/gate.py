"""The perimeter gate: nothing reaches a counterpart bank without passing through here.

Order matters, and so does what each layer is allowed to conclude.

1. Deterministic rules redact first and always. They are the guarantee; nothing below can
   talk them out of a redaction.
2. A Gemma running inside this container reads what is left. It never leaves the process,
   so the text being checked for leaks is not itself disclosed to check it.
3. Model Armor reads it last — Google's detector, in this bank's own project, agreeing (or
   not) with ours. It catches what regexes structurally cannot: a customer's name.

Layers 2 and 3 may only *add* a restriction. Either one flagging already-scrubbed text
withholds the payload: the gate fails closed on a finding, and open on an outage, because a
scanner being unreachable must not strand every case in the federation.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from services.bank.redaction import armor, gemma, rules

log = logging.getLogger("concordat.redaction.gate")


class GateResult(BaseModel):
    text: str
    findings: list[str] = []
    blocked: bool = False
    gemma_checked: bool = False
    armor_checked: bool = False

    def layers(self) -> str:
        """Which layers actually ran. An audit entry that says 'rules+gemma+armor' when armor
        was unreachable would be a lie in the one record we ask people to trust."""
        names = ["rules"]
        if self.gemma_checked:
            names.append("gemma")
        if self.armor_checked:
            names.append("armor")
        return "+".join(names)

    def audit_detail(self) -> str:
        state = "BLOCKED" if self.blocked else "passed"
        return f"{state} ({self.layers()}): {', '.join(self.findings) or 'nothing withheld'}"


def gate(text: str) -> GateResult:
    if not text.strip():
        return GateResult(text=text)

    scrubbed = rules.scrub(text)
    findings = list(scrubbed.findings)

    verdict = gemma.looks_like_leak(scrubbed.text)
    gemma_checked = verdict is not None
    if verdict:
        findings.append("gemma:residual_disclosure_risk")

    armor_verdict = armor.scan_outbound(scrubbed.text)
    if armor_verdict.matched:
        findings.extend(f"armor:{f}" for f in armor_verdict.filters)

    blocked = bool(verdict) or armor_verdict.matched
    if blocked:
        log.warning("perimeter withheld a payload: %s", findings)
    result = GateResult(
        text="" if blocked else scrubbed.text,
        findings=findings,
        blocked=blocked,
        gemma_checked=gemma_checked,
        armor_checked=armor_verdict.available,
    )
    log.info("perimeter gate: %s", result.audit_detail())
    return result
