"""Firestore persistence for cases. One doc per case in collection 'cases'; the UI streams
this collection. Any service can die mid-case and resume from here (invariant #5).
"""

from __future__ import annotations

from google.cloud import firestore

from services.bank.auth import bank_credentials
from services.bank.case import CaseState
from services.bank.config import BankConfig


class CaseStore:
    def __init__(self, cfg: BankConfig):
        self.cfg = cfg
        self.db = firestore.Client(project=cfg.project, credentials=bank_credentials(cfg))
        self.col = self.db.collection("cases")

    def save(self, case: CaseState) -> None:
        self.col.document(case.case_id).set(case.model_dump(mode="json"))

    def load(self, case_id: str) -> CaseState:
        snap = self.col.document(case_id).get()
        if not snap.exists:
            raise KeyError(f"case {case_id} not found")
        return CaseState.model_validate(snap.to_dict())
