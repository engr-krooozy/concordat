"""Event-driven case orchestrator: one handler per event type; each handler loads state,
runs one step, persists, and publishes the next event. Nothing blocks waiting for a peer —
the fleet is resumable from Firestore at every boundary (invariant #5).
"""

from __future__ import annotations

import logging

from services.bank.agents.fleet import run_investigation
from services.bank.agents.reporter import draft_report
from services.bank.case import CaseState, Status
from services.bank.config import BankConfig
from services.bank.events import CaseEvent, EventBus
from services.bank.store import CaseStore

log = logging.getLogger("concordat.orchestrator")


class Orchestrator:
    def __init__(self, cfg: BankConfig):
        self.cfg = cfg
        self.store = CaseStore(cfg)
        self.bus = EventBus(cfg)

    async def handle(self, event: CaseEvent) -> None:
        log.info("handling %s for case %s", event.type, event.case_id)
        match event.type:
            case "case.kickoff":
                await self._kickoff(event)
            case "case.trace_done":
                await self._report(event)
            case "case.report_done":
                pass  # Phase 2: dead_end cases proceed to A2A discovery here

    async def _kickoff(self, event: CaseEvent) -> None:
        case = CaseState(case_id=event.case_id, bank=self.cfg.bank)
        case.log(f"{self.cfg.bank}/intake", "report", event.report)
        self.store.save(case)
        await run_investigation(self.cfg, case, event.report)
        self.store.save(case)
        self.bus.publish(
            CaseEvent(type="case.trace_done", bank=self.cfg.bank, case_id=case.case_id)
        )

    async def _report(self, event: CaseEvent) -> None:
        case = self.store.load(event.case_id)
        if case.status not in (Status.DEAD_END, Status.CLOSED):
            log.warning("trace_done for case %s in status %s; skipping", case.case_id, case.status)
            return
        case.report = await draft_report(self.cfg, case)
        case.log(f"{self.cfg.bank}/reporter", "report_drafted", f"{len(case.report)} chars")
        self.store.save(case)
        self.bus.publish(
            CaseEvent(type="case.report_done", bank=self.cfg.bank, case_id=case.case_id)
        )
