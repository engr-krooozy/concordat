"""The perimeter gate: nothing reaches a counterpart bank without passing through here.

Order matters. Deterministic rules redact first and always; the local Gemma model then
inspects what is left. If Gemma still smells a leak in already-scrubbed text, the payload
is withheld rather than sent — the gate fails closed.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from services.bank.redaction import gemma, rules

log = logging.getLogger("concordat.redaction.gate")


class GateResult(BaseModel):
    text: str
    findings: list[str] = []
    blocked: bool = False
    gemma_checked: bool = False

    def audit_detail(self) -> str:
        state = "BLOCKED" if self.blocked else "passed"
        checks = "rules+gemma" if self.gemma_checked else "rules"
        return f"{state} ({checks}): {', '.join(self.findings) or 'nothing withheld'}"


def gate(text: str) -> GateResult:
    if not text.strip():
        return GateResult(text=text)

    scrubbed = rules.scrub(text)
    findings = list(scrubbed.findings)

    verdict = gemma.looks_like_leak(scrubbed.text)
    if verdict is None:
        result = GateResult(text=scrubbed.text, findings=findings)
        log.info("perimeter gate: %s", result.audit_detail())
        return result

    if verdict:
        findings.append("gemma:residual_disclosure_risk")
        log.warning("local Gemma flagged already-scrubbed text; withholding payload")
        blocked = GateResult(text="", findings=findings, blocked=True, gemma_checked=True)
        log.info("perimeter gate: %s", blocked.audit_detail())
        return blocked
    passed = GateResult(text=scrubbed.text, findings=findings, gemma_checked=True)
    log.info("perimeter gate: %s", passed.audit_detail())
    return passed
