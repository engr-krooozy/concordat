"""Gemma 3 running INSIDE the bank's perimeter.

This is the one model in Concordat that never talks to a cloud API: it is loaded from a
local GGUF in the bank's own container, so text can be inspected for disclosure risk before
it crosses an institutional boundary. Asking a hosted model "is this safe to send?" would
require sending it first, which defeats the purpose.

Model choice was measured, not assumed (scripts/eval_gemma_gate.py, 16 cases drawn from
real agent output):

    gemma-3-270m-it-Q8      8/16   recall 8/8   false alarms 8/8    0.19s   (says LEAK always)
    gemma-3-1b-it-Q4_K_M    8/16   recall 0/8   false alarms 0/8    0.81s   (says SAFE always)
    gemma-3-4b-it-Q4_K_M   16/16   recall 8/8   false alarms 0/8    5.97s   <- shipped

Both smaller models are degenerate: they answer one word regardless of input, which looks
like accuracy on a balanced set only by luck. A false alarm stalls a live negotiation, so
the gate ships the 4B model and pays six seconds for it.

Even so, this is a second opinion. rules.py has already redacted deterministically, and a
Gemma that is missing, slow, or wrong can only add a restriction, never lift one.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("concordat.redaction.gemma")

MODEL_PATH = Path(os.environ.get("GEMMA_MODEL_PATH", "/app/models/gemma-3-4b-it-Q4_K_M.gguf"))

SYSTEM = (
    "You are a bank's data-loss-prevention gate. Decide if the message discloses any "
    "customer-identifying detail: a personal name, an account number, an exact amount, a "
    "precise timestamp, or contact details. Aggregate or statistical statements about groups "
    "are NOT disclosures. Answer with exactly one word: LEAK or SAFE."
)


@lru_cache(maxsize=1)
def _model():
    """Load the local GGUF once per process. None when unavailable — the caller then relies
    on the deterministic rules alone.
    """
    if not MODEL_PATH.exists():
        log.info("no local Gemma at %s; perimeter gate runs on rules only", MODEL_PATH)
        return None
    try:
        from llama_cpp import Llama
    except ImportError:
        log.info("llama_cpp not installed; perimeter gate runs on rules only")
        return None
    log.info("loading local Gemma from %s", MODEL_PATH)
    return Llama(model_path=str(MODEL_PATH), n_ctx=2048, n_threads=4, verbose=False)


def available() -> bool:
    return _model() is not None


@lru_cache(maxsize=256)
def looks_like_leak(text: str) -> bool | None:
    """True/False from the local model, or None when no model is loaded.

    Cached: the same rationale is sent to several peers across several rounds, and paying
    six seconds per peer for an identical verdict would be silly.
    """
    model = _model()
    if model is None:
        return None
    try:
        reply = model.create_chat_completion(
            messages=[{"role": "user", "content": f"{SYSTEM}\n\nMESSAGE: {text[:1500]}"}],
            max_tokens=5,
            temperature=0.0,
        )
        answer = reply["choices"][0]["message"]["content"].strip().upper()
    except Exception:
        log.exception("local Gemma inference failed; treating as suspicious")
        return True
    log.debug("gemma verdict: %s", answer)
    return "LEAK" in answer
