"""Event-driven case orchestrator: one handler per event type; each handler loads state,
runs one step, persists, and publishes the next event. Nothing blocks waiting for a peer —
the fleet is resumable from Firestore at every boundary (invariant #5).
"""

from __future__ import annotations

import logging
import os
import uuid

from services.bank.agents.diplomat import Diplomat
from services.bank.agents.enforcer import close as close_case
from services.bank.agents.enforcer import enforce
from services.bank.agents.fleet import run_investigation
from services.bank.agents.joint import run_joint_analysis
from services.bank.agents.negotiation import negotiate
from services.bank.agents.reporter import draft_report
from services.bank.case import RESUMABLE_FROM, CaseState, Status
from services.bank.config import BankConfig
from services.bank.events import CaseEvent, EventBus
from services.bank.store import CaseStore

log = logging.getLogger("concordat.orchestrator")

REGISTRY_URL = os.environ.get("REGISTRY_URL", "https://registry-fa7ntw3nkq-uc.a.run.app")


class Orchestrator:
    def __init__(self, cfg: BankConfig):
        self.cfg = cfg
        self.store = CaseStore(cfg)
        self.bus = EventBus(cfg)
        self.diplomat = Diplomat(cfg, registry_url=REGISTRY_URL)

    async def handle(self, event: CaseEvent) -> None:
        log.info("handling %s for case %s", event.type, event.case_id)
        match event.type:
            case "case.kickoff":
                await self._kickoff(event)
            case "case.trace_done":
                await self._report(event)
            case "case.report_done":
                await self._negotiate(event)
            case "case.negotiated":
                await self._joint_analysis(event)
            case "case.approved":
                await self._enforce(event)

    async def _kickoff(self, event: CaseEvent) -> None:
        # scheduled kickoffs arrive without an id — a fixed one would overwrite the same case
        case_id = event.case_id or f"case-{uuid.uuid4().hex[:8]}"
        case = CaseState(case_id=case_id, bank=self.cfg.bank)
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

    async def _joint_analysis(self, event: CaseEvent) -> None:
        case = self.store.load(event.case_id)
        if case.status not in RESUMABLE_FROM["joint_analysis"]:
            log.info("case %s is %s — no room to compile", case.case_id, case.status)
            return
        if case.status is not Status.AGREED:
            log.warning("case %s resuming joint analysis from %s", case.case_id, case.status)
        try:
            await run_joint_analysis(self.cfg, case, self.diplomat)
        finally:
            self.store.save(case)
        self.bus.publish(
            CaseEvent(type="case.analysis_done", bank=self.cfg.bank, case_id=case.case_id)
        )

    async def approve(self, case_id: str, approver: str) -> CaseState:
        """Human approval gate. Called by the analyst UI, never by an agent."""
        case = self.store.load(case_id)
        if case.status is not Status.AWAITING_APPROVAL:
            raise ValueError(f"case {case_id} is {case.status}, not awaiting approval")
        case.transition(Status.ENFORCING, f"{self.cfg.bank}/analyst", f"approved by {approver}")
        self.store.save(case)
        self.bus.publish(
            CaseEvent(type="case.approved", bank=self.cfg.bank, case_id=case_id, report=approver)
        )
        return case

    async def _enforce(self, event: CaseEvent) -> None:
        case = self.store.load(event.case_id)
        if case.status is not Status.ENFORCING:
            return
        enforce(self.cfg, case, approver=event.report or "unknown")
        case.report = await draft_report(self.cfg, case)
        close_case(self.cfg, case)
        self.store.save(case)
        log.info("case %s closed", case.case_id)

    async def _negotiate(self, event: CaseEvent) -> None:
        case = self.store.load(event.case_id)
        if case.status not in RESUMABLE_FROM["negotiate"]:
            log.info("case %s is %s — no negotiation needed", case.case_id, case.status)
            return
        if case.status is not Status.DEAD_END:
            log.warning("case %s resuming negotiation from %s", case.case_id, case.status)
        try:
            signed = await negotiate(self.cfg, case, self.diplomat)
        finally:
            self.store.save(case)  # transcript + status persist even on failure
        if signed is not None:
            log.info("concordat signed for %s: %s", case.case_id, signed.terms_digest())
        self.bus.publish(
            CaseEvent(type="case.negotiated", bank=self.cfg.bank, case_id=case.case_id)
        )
