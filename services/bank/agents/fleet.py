"""Detection + tracing agents for one bank fleet (ADK).

Pattern (SPEC invariant #2): tools are deterministic parameterized SQL; Gemini decides which
tool to call, when the frontier is exhausted, and writes the human-readable summary. Tool
results — not model text — are what mutate the case.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from services.bank.case import BoundaryEdge, CaseState, Status
from services.bank.config import BankConfig
from services.bank.ledger import Ledger


def _use_vertex(cfg: BankConfig) -> None:
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "1")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", cfg.project)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", cfg.vertex_location)


class FleetContext:
    """Shared mutable state the tools close over during one investigation run."""

    def __init__(self, cfg: BankConfig, case: CaseState):
        self.cfg = cfg
        self.case = case
        self.ledger = Ledger(cfg)
        self.frontier: list[str] = []  # accounts still being followed
        self.frontier_after: datetime | None = None


def build_tools(ctx: FleetContext):
    def find_large_outflows(day: str, min_amount: float) -> list[dict]:
        """Find unusually large outbound transactions on a given day (YYYY-MM-DD) in our
        own ledger. Returns candidate victim-fraud debits, largest first."""
        since = datetime.fromisoformat(day).replace(tzinfo=UTC)
        txns = ctx.ledger.large_outflows(since, since + timedelta(days=1), min_amount)
        ctx.case.log(
            f"{ctx.cfg.bank}/detector",
            "query:large_outflows",
            f"day={day} min={min_amount} hits={len(txns)}",
        )
        return [t.model_dump(mode="json") for t in txns]

    def open_trace(txn_id: str) -> str:
        """Open the money trace at a specific transaction id previously returned by
        find_large_outflows. Call exactly once, before trace_next_hop."""
        found = ctx.ledger._query(
            f"""SELECT txn_id, ts, src_account, dst_account, src_bank, dst_bank, amount,
                       channel, narration FROM {ctx.ledger.table} WHERE txn_id = @txn_id""",
            txn_id=txn_id,
        )
        if not found:
            return f"ERROR: {txn_id} not found in our ledger"
        ctx.case.victim_txn = found[0]
        ctx.case.trace = [found[0]]
        ctx.case.transition(Status.TRACING, f"{ctx.cfg.bank}/tracer", f"victim txn {txn_id}")
        ctx.frontier = [found[0].dst_account]
        ctx.frontier_after = found[0].ts
        return f"trace opened at {txn_id}; frontier={ctx.frontier}"

    def trace_next_hop(min_amount: float) -> dict:
        """Follow the money one hop: where did the frontier accounts send funds next?
        Returns hops found, the new frontier, and any boundary edges (funds leaving our
        bank — we cannot see further past those)."""
        if not ctx.frontier:
            return {"hops": [], "frontier": [], "boundary_edges": [], "note": "frontier empty"}
        hops = ctx.ledger.outgoing_hops(ctx.frontier, ctx.frontier_after, 4, min_amount)
        new_frontier: list[str] = []
        boundaries = []
        for h in hops:
            ctx.case.trace.append(h)
            if h.dst_bank != ctx.cfg.bank:
                edge = BoundaryEdge(txn=h, peer_bank=h.dst_bank)
                ctx.case.boundary_edges.append(edge)
                boundaries.append(h.model_dump(mode="json"))
            else:
                new_frontier.append(h.dst_account)
        ctx.frontier = new_frontier
        if hops:
            ctx.frontier_after = max(h.ts for h in hops)
        ctx.case.log(
            f"{ctx.cfg.bank}/tracer",
            "hop",
            f"hops={len(hops)} frontier={len(new_frontier)} boundaries={len(boundaries)}",
        )
        return {
            "hops": [h.model_dump(mode="json") for h in hops],
            "frontier": new_frontier,
            "boundary_edges": boundaries,
        }

    def close_trace(summary: str) -> str:
        """Finish the trace with a one-paragraph summary of the money flow. If any boundary
        edges exist the case becomes DEAD_END (needs inter-bank negotiation); else CLOSED."""
        ctx.case.summary = summary
        if ctx.case.boundary_edges:
            ctx.case.transition(
                Status.DEAD_END,
                f"{ctx.cfg.bank}/tracer",
                f"{len(ctx.case.boundary_edges)} boundary edges",
            )
        else:
            ctx.case.transition(Status.CLOSED, f"{ctx.cfg.bank}/tracer", "resolved in-perimeter")
        return f"trace closed with status {ctx.case.status}"

    return [find_large_outflows, open_trace, trace_next_hop, close_trace]


def build_investigator(cfg: BankConfig, ctx: FleetContext) -> Agent:
    _use_vertex(cfg)
    return Agent(
        name=f"{cfg.bank}_investigator",
        model=cfg.model,
        instruction=(
            f"You are the fraud investigation agent for bank '{cfg.bank}'. You can only see "
            f"this bank's own ledger — that is a legal boundary, not a technical bug.\n"
            "Given a fraud report, work strictly with tools:\n"
            "1. find_large_outflows on the reported day/amount; pick the txn matching the report.\n"
            "2. open_trace on that txn_id.\n"
            "3. trace_next_hop repeatedly (use min_amount ~40% of the victim amount to skip "
            "noise) until the frontier is empty.\n"
            "4. close_trace with a concise factual summary naming accounts, amounts, and any "
            "funds that left our bank (boundary edges) — do not speculate about other banks.\n"
            "Never invent transaction data; only report what tools returned."
        ),
        tools=build_tools(ctx),
    )


async def run_investigation(cfg: BankConfig, case: CaseState, report: str) -> CaseState:
    ctx = FleetContext(cfg, case)
    agent = build_investigator(cfg, ctx)
    runner = InMemoryRunner(agent=agent, app_name="concordat")
    session = await runner.session_service.create_session(app_name="concordat", user_id="analyst")
    msg = types.Content(role="user", parts=[types.Part(text=report)])
    async for event in runner.run_async(user_id="analyst", session_id=session.id, new_message=msg):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    case.log(f"{cfg.bank}/investigator", "narrate", part.text[:400])
    return case
