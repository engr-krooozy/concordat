"""Bank-fleet identity: every credentialed client (BigQuery, Vertex) runs AS the bank's
service account — ambient on Cloud Run, impersonated locally. Sovereignty holds in dev
exactly as in prod, and the user's personal/work ADC never touches project workloads.
"""

from __future__ import annotations

from functools import lru_cache

import google.auth
from google.auth import impersonated_credentials

from services.bank.config import BankConfig

_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


@lru_cache
def _cached(service_account: str, impersonate: bool):
    creds, _ = google.auth.default(scopes=_SCOPES)
    if impersonate:
        creds = impersonated_credentials.Credentials(
            source_credentials=creds,
            target_principal=service_account,
            target_scopes=_SCOPES,
        )
    return creds


def bank_credentials(cfg: BankConfig):
    return _cached(cfg.service_account, cfg.impersonate_locally)
