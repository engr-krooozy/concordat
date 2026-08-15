"""Deterministic perimeter rules — the hard guarantee.

These run on every outbound payload and cannot be talked out of a redaction. The local
Gemma classifier (gemma.py) adds a semantic second opinion on top, but nothing depends on a
model's judgement to keep an identifier inside the bank.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

# Bank account identifiers in this federation: ALP-9000001, MER-920004, UNI-93 0012 ...
ACCOUNT = re.compile(r"\b(?:ALP|MER|UNI)-\d{4,}\b")
# Long digit runs: card-like, BVN-like, phone-like
DIGIT_RUN = re.compile(r"\b\d{10,}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
# Exact naira amounts are quasi-identifiers: 2,400,000.00 / NGN 2400000
EXACT_AMOUNT = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d{2})?\b|\bNGN\s?\d{6,}\b")
# Timestamps precise enough to fingerprint a single transaction
PRECISE_TIME = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?\b")

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("account_id", ACCOUNT),
    ("email", EMAIL),
    ("long_digit_run", DIGIT_RUN),
    ("exact_amount", EXACT_AMOUNT),
    ("precise_timestamp", PRECISE_TIME),
]


class RuleFindings(BaseModel):
    text: str
    findings: list[str] = []  # rule ids that fired, with the count

    @property
    def clean(self) -> bool:
        return not self.findings


def scrub(text: str) -> RuleFindings:
    """Replace every match with a typed placeholder. Returns the redacted text and which
    rules fired, so the audit log records what was withheld without recording the value.
    """
    findings: list[str] = []
    out = text
    for rule_id, pattern in PATTERNS:
        matches = pattern.findall(out)
        if matches:
            findings.append(f"{rule_id}:{len(matches)}")
            out = pattern.sub(f"[REDACTED:{rule_id}]", out)
    return RuleFindings(text=out, findings=findings)
