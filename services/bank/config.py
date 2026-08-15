"""Per-bank configuration.

Each bank is a **separate GCP project**. That is the whole point: sovereignty is a billing and
IAM boundary drawn by Google, not a convention we promise to respect. One codebase, deployed
once per project, with no credential that can reach across.

The commons project holds only neutral infrastructure — the agent-card registry, the
mission-control observatory, and the clean rooms compiled from signed agreements. It holds no
bank's ledger.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel

BANK_PREFIXES = {"alpha": "ALP", "meridian": "MER", "union": "UNI"}

# The neutral ground. Nothing here can read a bank's transactions.
COMMONS_PROJECT = os.environ.get("COMMONS_PROJECT", "concordat-hack")


def project_for(bank: str) -> str:
    return os.environ.get(f"{bank.upper()}_PROJECT", f"concordat-{bank}")


class BankConfig(BaseModel):
    bank: str  # alpha | meridian | union
    prefix: str  # ALP | MER | UNI
    project: str  # this bank's OWN project — its perimeter
    commons: str = COMMONS_PROJECT
    dataset: str  # the only dataset this fleet may read
    model: str = "gemini-3.5-flash"
    vertex_location: str = "global"  # 3.5 models serve from the global endpoint only
    service_account: str
    impersonate_locally: bool = True  # local dev runs AS the bank SA so sovereignty holds

    @property
    def peers(self) -> list[str]:
        return [b for b in BANK_PREFIXES if b != self.bank]

    @property
    def room_runner(self) -> str:
        """The clean-room identity, which lives in the commons and holds no standing access
        to any bank's data."""
        return f"sa-cleanroom@{self.commons}.iam.gserviceaccount.com"


def make_config(bank: str, *, impersonate_locally: bool | None = None) -> BankConfig:
    if bank not in BANK_PREFIXES:
        raise ValueError(f"bank must be one of {list(BANK_PREFIXES)}, got {bank!r}")
    project = project_for(bank)
    return BankConfig(
        bank=bank,
        prefix=BANK_PREFIXES[bank],
        project=project,
        dataset=f"bank_{bank}",
        service_account=f"sa-bank-{bank}@{project}.iam.gserviceaccount.com",
        impersonate_locally=(
            os.environ.get("K_SERVICE") is None
            if impersonate_locally is None
            else impersonate_locally
        ),
    )


@lru_cache
def load_config() -> BankConfig:
    return make_config(os.environ.get("BANK", "alpha"))
