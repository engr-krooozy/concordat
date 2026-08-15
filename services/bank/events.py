"""Case events over Pub/Sub. Every state transition is event-driven — no request/response
chains between steps (invariant #5). One topic per bank: case-events-<bank>.
"""

from __future__ import annotations

import json
from typing import Literal

from google.cloud import pubsub_v1
from pydantic import BaseModel

from services.bank.auth import bank_credentials
from services.bank.config import BankConfig


class CaseEvent(BaseModel):
    type: Literal[
        "case.kickoff",  # analyst filed a fraud report
        "case.trace_done",  # investigation finished (dead_end or closed)
        "case.report_done",  # SAR-style report drafted
    ]
    bank: str
    case_id: str
    report: str = ""  # kickoff only: the analyst's fraud report text


class EventBus:
    def __init__(self, cfg: BankConfig):
        self.cfg = cfg
        self.publisher = pubsub_v1.PublisherClient(credentials=bank_credentials(cfg))
        self.topic = self.publisher.topic_path(cfg.project, f"case-events-{cfg.bank}")

    def publish(self, event: CaseEvent) -> None:
        self.publisher.publish(self.topic, event.model_dump_json().encode()).result(timeout=30)


def decode_push(envelope: dict) -> CaseEvent:
    """Decode a Pub/Sub push envelope (or a raw pulled message payload)."""
    import base64

    data = envelope["message"]["data"]
    return CaseEvent.model_validate(json.loads(base64.b64decode(data)))
