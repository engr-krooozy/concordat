"""Multimodal intake: a customer's voice note becomes a case.

Nobody reports fraud by filling in a form. In Nigerian retail banking the first contact is
overwhelmingly a phone call or a voice note to the bank's support line — a frightened person
talking fast, giving the account number as digits spoken aloud, saying "yesterday afternoon"
rather than a timestamp. Every earlier version of this system started from a tidy paragraph
of English that somebody had already typed up. That step is real work, it is done by a human
under time pressure, and it is exactly the kind of work an agent should absorb.

So the fleet takes the audio. Gemini transcribes it and pulls out the three things the
investigation actually needs — the account, the amount, the window — and writes the report
the tracer already knows how to read. Everything downstream is unchanged, which is the point:
the intake got wider, not the pipeline.

Two deliberate constraints:

- **Extraction is bounded.** The model returns a strict JSON shape that a Pydantic model
  validates, not free prose that later code has to parse hopefully. An unparseable answer
  falls back to the plain transcript rather than guessing.
- **The audio never crosses a perimeter.** It lives in the bank's own bucket, read by the
  bank's own service account, and only the derived report continues. A peer bank never sees
  it, and neither does the commons.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from services.bank.config import BankConfig

log = logging.getLogger("concordat.intake")

INSTRUCTION = """You are the intake desk of a Nigerian retail bank's fraud team.
Today is {today}.

Listen to the caller and return ONLY a JSON object, no prose and no code fence:
{{"account": "...", "amount_ngn": 0, "when": "...", "when_date": "YYYY-MM-DD",
  "channel": "...", "summary": "..."}}

- account: the caller's own account id exactly as spoken, normalised to the bank's format
  (three letters, a hyphen, then digits). "A L P nine million and one" is ALP-9000001.
- amount_ngn: a plain number, no separators. "two point four million" is 2400000.
- when: what the caller said about timing, in their words ("the 12th, in the afternoon").
- when_date: that resolved to an absolute date, using today's date above. Callers say "the
  twelfth" or "last Tuesday" and never say the year — work it out. Pick the most recent
  matching date that is not in the future. Empty string only if they gave no timing at all.
- channel: how they say the money moved (web transfer, POS, ATM, transfer), or "unknown".
- summary: one sentence, in the third person, for the case file.

If a field is genuinely not in the audio, use an empty string or 0. Never invent one."""


class VoiceReport(BaseModel):
    account: str = ""
    amount_ngn: float = 0
    when: str = ""
    when_date: str = ""  # ISO, resolved against the bank's clock — see below
    channel: str = "unknown"
    summary: str = ""
    transcript: str = Field(default="", exclude=True)

    def as_report(self) -> str:
        """The text a tracer already knows how to read.

        The absolute date matters more than it looks. An early version passed the caller's
        own words straight through — "the twelfth of August" — and the investigator searched
        2024, then 2023, then 2021, sensibly and exhaustively, for a ring that happened in
        2026. Nobody says the year out loud on the phone, so resolving it is the intake's
        job, not the caller's.
        """
        amount = f"approximately {self.amount_ngn:,.0f} naira" if self.amount_ngn else "an amount"
        channel = self.channel if self.channel != "unknown" else "an unauthorised transfer"
        if self.when_date:
            when = f"on {self.when_date}" + (f" ({self.when})" if self.when else "")
        else:
            when = self.when or "recently"
        return (
            f"Customer fraud report, filed by voice note: account holder of "
            f"{self.account or 'an unidentified account'} reports {amount} stolen via "
            f"{channel} they did not authorise, {when}. Investigate and trace where the "
            f"funds went."
        )


def _extract_json(text: str) -> dict:
    """Models fence JSON more often than they promise not to."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0)) if match else {}


async def transcribe_report(cfg: BankConfig, audio_uri: str) -> VoiceReport | None:
    """Turn a voice note in this bank's own bucket into a structured report.

    Returns None if the audio cannot be read or understood — the caller then falls back to
    whatever text came with the event, because a fraud report that arrives garbled should
    still open a case rather than vanish.
    """
    try:
        from google import genai
        from google.genai import types

        from services.bank.auth import bank_credentials

        client = genai.Client(
            vertexai=True,
            project=cfg.project,
            location=cfg.vertex_location,
            credentials=bank_credentials(cfg),
        )
        response = await client.aio.models.generate_content(
            model=cfg.model,
            contents=[
                types.Part.from_uri(file_uri=audio_uri, mime_type="audio/mpeg"),
                types.Part.from_text(
                    text=INSTRUCTION.format(today=datetime.now(UTC).date().isoformat())
                ),
            ],
        )
        raw = (response.text or "").strip()
        data = _extract_json(raw)
        if not data:
            log.warning("intake: model returned no JSON for %s", audio_uri)
            return None
        report = VoiceReport.model_validate(data)
        report.transcript = raw
        log.info(
            "intake: voice note understood — account=%s amount=%s date=%s channel=%s",
            report.account,
            report.amount_ngn,
            report.when_date or "unresolved",
            report.channel,
        )
        return report
    except Exception as exc:  # noqa: BLE001 - a bad recording must not swallow a fraud report
        log.warning("intake: could not read %s (%s: %s)", audio_uri, type(exc).__name__, exc)
        return None
