"""BigQuery access for ONE bank's ledger, always as that bank's service account.

Sovereignty invariant #1 lives here: every query is parameterized against the bank's own
dataset; locally we impersonate the bank SA so a cross-dataset read fails with Access Denied
in dev exactly as it does in prod.
"""

from __future__ import annotations

from datetime import datetime

import google.auth
from google.auth import impersonated_credentials
from google.cloud import bigquery
from pydantic import BaseModel

from services.bank.config import BankConfig

_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class Txn(BaseModel):
    txn_id: str
    ts: datetime
    src_account: str
    dst_account: str
    src_bank: str
    dst_bank: str
    amount: float
    channel: str
    narration: str


class Ledger:
    def __init__(self, cfg: BankConfig):
        self.cfg = cfg
        creds, _ = google.auth.default(scopes=_SCOPES)
        if cfg.impersonate_locally:
            creds = impersonated_credentials.Credentials(
                source_credentials=creds,
                target_principal=cfg.service_account,
                target_scopes=_SCOPES,
            )
        self.client = bigquery.Client(project=cfg.project, credentials=creds)
        self.table = f"`{cfg.project}.{cfg.dataset}.transactions`"

    def _query(self, sql: str, **params) -> list[Txn]:
        job_params = []
        for k, v in params.items():
            if isinstance(v, float):
                job_params.append(bigquery.ScalarQueryParameter(k, "FLOAT64", v))
            elif isinstance(v, datetime):
                job_params.append(bigquery.ScalarQueryParameter(k, "TIMESTAMP", v))
            elif isinstance(v, list):
                job_params.append(bigquery.ArrayQueryParameter(k, "STRING", v))
            else:
                job_params.append(bigquery.ScalarQueryParameter(k, "STRING", str(v)))
        job = self.client.query(
            sql, job_config=bigquery.QueryJobConfig(query_parameters=job_params)
        )
        return [Txn(**{f: row[f] for f in Txn.model_fields}) for row in job.result()]

    def large_outflows(self, since: datetime, until: datetime, min_amount: float) -> list[Txn]:
        return self._query(
            f"""SELECT txn_id, ts, src_account, dst_account, src_bank, dst_bank, amount,
                       channel, narration
                FROM {self.table}
                WHERE ts BETWEEN @since AND @until AND amount >= @min_amount
                  AND channel IN ('web','transfer')
                ORDER BY amount DESC LIMIT 20""",
            since=since,
            until=until,
            min_amount=min_amount,
        )

    def outgoing_hops(
        self, accounts: list[str], after: datetime, window_hours: int, min_amount: float
    ) -> list[Txn]:
        return self._query(
            f"""SELECT txn_id, ts, src_account, dst_account, src_bank, dst_bank, amount,
                       channel, narration
                FROM {self.table}
                WHERE src_account IN UNNEST(@accounts)
                  AND ts > @after AND ts <= TIMESTAMP_ADD(@after, INTERVAL {int(window_hours)} HOUR)
                  AND amount >= @min_amount
                ORDER BY ts LIMIT 50""",
            accounts=accounts,
            after=after,
            min_amount=min_amount,
        )
