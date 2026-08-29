"""Model Armor: the third opinion at the perimeter, and the only one that looks inward.

The gate has two jobs, and until now it only did one of them.

Outbound, we are protecting our customers from our own agents: deterministic rules redact,
and a Gemma running inside this container gives a semantic second opinion. Model Armor's
Sensitive Data Protection filter is a third pass over the already-scrubbed text, run by
Google rather than by us — a bank that will not take our word for our own redaction can
point at somebody else's detector agreeing.

Inbound is the job we were missing. Every `rationale` and `note` a counterpart sends us is
free text written by another bank's LLM, and it lands in the context of ours. A peer that
wanted our investigator to misbehave would put it exactly there. Model Armor's prompt-
injection and jailbreak filter reads that text *before* our agents do. Rival banks are the
threat model this whole project is built around; it would be odd to trust their prose.

Where the text goes: outbound text is already scrubbed before it gets here, and the call is
made with the bank's own service account to a regional endpoint inside the bank's own
project. It crosses the container boundary, not the perimeter — unlike Gemma, which never
leaves the process. That distinction is the reason Gemma stays: if Model Armor is
unreachable, the local checks still stand on their own.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from pydantic import BaseModel

log = logging.getLogger("concordat.redaction.armor")

# Template ids created by infra/setup_armor.sh, one pair per bank project.
OUTBOUND_TEMPLATE = "concordat-outbound"  # sensitive data protection
INBOUND_TEMPLATE = "concordat-inbound"  # prompt injection + jailbreak
LOCATION = os.environ.get("ARMOR_LOCATION", "us-central1")
# A scanner is not allowed to hold a negotiation open. The default client retry
# budget is 60s per call, which across a four-round parley is minutes of silence.
ARMOR_TIMEOUT_S = 10.0


class ArmorVerdict(BaseModel):
    """None-ish by design: `available=False` means the gate falls back to rules + Gemma."""

    available: bool = False
    matched: bool = False
    filters: list[str] = []

    def summary(self) -> str:
        if not self.available:
            return "armor:unavailable"
        return f"armor:{'MATCH ' + ','.join(self.filters) if self.matched else 'clean'}"


def _enabled() -> bool:
    return os.environ.get("MODEL_ARMOR", "on").lower() not in ("off", "0", "false")


@lru_cache(maxsize=1)
def _client():
    from google.cloud import modelarmor_v1

    from services.bank.auth import bank_credentials
    from services.bank.config import load_config

    cfg = load_config()
    # Model Armor is regional and the endpoint must match, or every call 404s.
    return (
        modelarmor_v1.ModelArmorClient(
            credentials=bank_credentials(cfg),
            client_options={"api_endpoint": f"modelarmor.{LOCATION}.rep.googleapis.com"},
        ),
        cfg.project,
    )


def _template(project: str, template_id: str) -> str:
    return f"projects/{project}/locations/{LOCATION}/templates/{template_id}"


def _matched_filters(result) -> list[str]:
    """Which filters fired, by name. `filter_results` is a map keyed by filter id."""
    from google.cloud import modelarmor_v1 as ma

    names: list[str] = []
    for key, filter_result in (result.filter_results or {}).items():
        for field in (
            "sdp_filter_result",
            "pi_and_jailbreak_filter_result",
            "rai_filter_result",
            "malicious_uri_filter_result",
        ):
            sub = getattr(filter_result, field, None)
            if sub is None:
                continue
            # SDP reports through a nested inspect_result; the others carry match_state directly
            state = getattr(sub, "match_state", None)
            if not state:
                state = getattr(getattr(sub, "inspect_result", None), "match_state", None)
            if state == ma.FilterMatchState.MATCH_FOUND:
                names.append(key)
                break
    return sorted(set(names))


def _sanitize(text: str, template_id: str, inbound: bool) -> ArmorVerdict:
    if not _enabled() or not text.strip():
        return ArmorVerdict()
    try:
        from google.cloud import modelarmor_v1 as ma

        client, project = _client()
        name = _template(project, template_id)
        if inbound:
            resp = client.sanitize_user_prompt(
                request=ma.SanitizeUserPromptRequest(
                    name=name, user_prompt_data=ma.DataItem(text=text)
                ),
                timeout=ARMOR_TIMEOUT_S,
            )
        else:
            resp = client.sanitize_model_response(
                request=ma.SanitizeModelResponseRequest(
                    name=name, model_response_data=ma.DataItem(text=text)
                ),
                timeout=ARMOR_TIMEOUT_S,
            )
        result = resp.sanitization_result
        matched = result.filter_match_state == ma.FilterMatchState.MATCH_FOUND
        return ArmorVerdict(available=True, matched=matched, filters=_matched_filters(result))
    except Exception as exc:  # noqa: BLE001 - deliberate: see the fail-open note below
        # Fail *open* here specifically: rules already redacted and Gemma already voted, so
        # the guarantee does not rest on this call. Failing closed would let an outage in a
        # third-party scanner stall every case in the federation.
        log.warning(
            "Model Armor unavailable (%s: %s); rules + Gemma stand", type(exc).__name__, exc
        )
        return ArmorVerdict()


def scan_outbound(text: str) -> ArmorVerdict:
    """Third pass over already-scrubbed text leaving this bank."""
    return _sanitize(text, OUTBOUND_TEMPLATE, inbound=False)


def scan_inbound(text: str) -> ArmorVerdict:
    """Peer-authored free text, before it reaches our agents."""
    return _sanitize(text, INBOUND_TEMPLATE, inbound=True)
