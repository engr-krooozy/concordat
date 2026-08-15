"""Per-bank configuration. ONE codebase, deployed 3x — everything bank-specific lives here."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel

BANK_PREFIXES = {"alpha": "ALP", "meridian": "MER", "union": "UNI"}


class BankConfig(BaseModel):
    bank: str  # alpha | meridian | union
    prefix: str  # ALP | MER | UNI
    project: str = "concordat-hack"
    dataset: str  # bank_<name> — the ONLY dataset this fleet may read
    model: str = "gemini-3.5-flash"
    vertex_location: str = "global"  # 3.5 models serve from the global endpoint only
    service_account: str
    impersonate_locally: bool = (
        True  # local dev runs AS the bank SA so sovereignty holds everywhere
    )

    @property
    def peers(self) -> list[str]:
        return [b for b in BANK_PREFIXES if b != self.bank]


@lru_cache
def load_config() -> BankConfig:
    bank = os.environ.get("BANK", "alpha")
    if bank not in BANK_PREFIXES:
        raise ValueError(f"BANK must be one of {list(BANK_PREFIXES)}, got {bank!r}")
    project = os.environ.get("GCP_PROJECT", "concordat-hack")
    return BankConfig(
        bank=bank,
        prefix=BANK_PREFIXES[bank],
        project=project,
        dataset=f"bank_{bank}",
        service_account=f"sa-bank-{bank}@{project}.iam.gserviceaccount.com",
        impersonate_locally=os.environ.get("K_SERVICE") is None,  # on Cloud Run, SA is ambient
    )
