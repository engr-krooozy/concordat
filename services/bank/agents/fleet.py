"""Detection + tracing agents for one bank fleet (ADK).

Pattern (SPEC invariant #2): tools are deterministic parameterized SQL; Gemini decides which
tool to call, when the frontier is exhausted, and writes the human-readable summary. Tool
results — not model text — are what mutate the case.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

from services.bank import memory
from services.bank.auth import bank_credentials
from services.bank.case import BoundaryEdge, CaseState, Status
from services.bank.config import BankConfig
from services.bank.ledger import Ledger


def bank_model(cfg: BankConfig) -> Gemini:
    """Gemini client running AS the bank service account (sovereignty even for model calls)."""
    return Gemini(
        model=cfg.model,
        client_kwargs={
            "vertexai": True,
            "project": cfg.project,
            "location": cfg.vertex_location,
            "credentials": bank_credentials(cfg),
        },
    )


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
        if not hops:
            # keep the frontier so the agent can retry with a lower threshold: mule networks
            # fan out into many small transfers, which a high min_amount hides
            ctx.case.log(f"{ctx.cfg.bank}/tracer", "hop_empty", f"min_amount={min_amount}")
            return {
                "hops": [],
                "frontier": ctx.frontier,
                "boundary_edges": [],
                "note": "no hops at this min_amount; retry lower before concluding",
            }
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
    return Agent(
        name=f"{cfg.bank}_investigator",
        model=bank_model(cfg),
        instruction=(
            f"You are the fraud investigation agent for bank '{cfg.bank}'. You can only see "
            f"this bank's own ledger — that is a legal boundary, not a technical bug.\n"
            "Given a fraud report, work strictly with tools:\n"
            "1. find_large_outflows on the reported day/amount; pick the txn matching the report.\n"
            "2. open_trace on that txn_id.\n"
            "3. trace_next_hop repeatedly until the frontier is empty. Start with min_amount "
            "~40% of the victim amount; whenever a hop returns no results while the frontier "
            "is NOT empty, retry the same hop with min_amount divided by 10 (down to 1% of "
            "the victim amount) before concluding the trail is cold — laundering networks "
            "fan out into many small transfers, and a high threshold hides them.\n"
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

    # Ask what this bank already knows. Every case used to begin from nothing, which meant
    # tracing the same ring shape to the same cash-out cluster on Tuesday having learned
    # nothing on Monday. Prior findings are k-thresholded aggregates, so there is no
    # individual in them — it is the shape of the network that carries forward, not a person.
    priors = await asyncio.to_thread(memory.recall, cfg, report, memory.RINGS)
    if priors:
        case.log(f"{cfg.bank}/investigator", "recalled", f"{len(priors)} prior finding(s)")
        report = (
            f"{report}\n\nWhat this bank has seen before (prior cases, aggregate only — "
            "treat as a hypothesis to check, not as evidence):\n"
            + "\n".join(f"- {p}" for p in priors)
        )

    msg = types.Content(role="user", parts=[types.Part(text=report)])
    async for event in runner.run_async(user_id="analyst", session_id=session.id, new_message=msg):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    case.log(f"{cfg.bank}/investigator", "narrate", part.text[:400])
    return case
