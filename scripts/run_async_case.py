"""Aug-18 checkpoint runner: publish ONE kickoff event, then drive the case purely via
Pub/Sub pull until the report is done. Locally this loop plays the role Cloud Run push
subscriptions play in prod — the orchestrator code is identical.

    BANK=alpha .venv/bin/python -m scripts.run_async_case
"""

import asyncio
import base64
import json
import uuid

from google.cloud import pubsub_v1

from services.bank.auth import bank_credentials
from services.bank.config import load_config
from services.bank.events import CaseEvent, EventBus
from services.bank.orchestrator import Orchestrator

REPORT = (
    "Customer fraud report: account holder of ALP-9000001 reports approximately 2.4 million "
    "naira stolen via a web transfer they did not authorize on 2026-08-12 (afternoon, WAT). "
    "Investigate and trace where the funds went."
)


async def main() -> None:
    cfg = load_config()
    orch = Orchestrator(cfg)
    case_id = f"case-{uuid.uuid4().hex[:8]}"

    EventBus(cfg).publish(
        CaseEvent(type="case.kickoff", bank=cfg.bank, case_id=case_id, report=REPORT)
    )
    print(f"published kickoff for {case_id}; pulling events...")

    subscriber = pubsub_v1.SubscriberClient(credentials=bank_credentials(cfg))
    sub = subscriber.subscription_path(cfg.project, f"case-events-{cfg.bank}-local")
    done = False
    while not done:
        resp = subscriber.pull(subscription=sub, max_messages=5, timeout=60)
        for received in resp.received_messages:
            payload = {"message": {"data": base64.b64encode(received.message.data).decode()}}
            event = CaseEvent.model_validate(
                json.loads(base64.b64decode(payload["message"]["data"]))
            )
            if event.case_id != case_id:  # stale message from an earlier run: ack and skip
                subscriber.acknowledge(subscription=sub, ack_ids=[received.ack_id])
                continue
            print(f"  -> {event.type}")
            await orch.handle(event)
            subscriber.acknowledge(subscription=sub, ack_ids=[received.ack_id])
            if event.type == "case.report_done":
                done = True

    case = orch.store.load(case_id)
    print(f"\n=== case {case.case_id} [{cfg.bank}] -> {case.status} ===")
    print(f"boundary edges: {[e.txn.txn_id for e in case.boundary_edges]}")
    print(f"\n--- SAR report ({len(case.report)} chars) ---\n")
    print(case.report[:1500])
    print("\n--- audit trail ---")
    for a in case.audit:
        print(f"{a.ts:%H:%M:%S} {a.actor:<22} {a.action:<28} {a.detail[:70]}")


if __name__ == "__main__":
    asyncio.run(main())
