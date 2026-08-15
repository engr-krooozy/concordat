"""Reporter agent: drafts the SAR-style case file from CaseState. No tools — it may only
narrate facts already in the case (trace, boundary edges, audit); structure enforced by
prompt, never asserted verbatim in tests.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from services.bank.agents.fleet import bank_model
from services.bank.case import CaseState
from services.bank.config import BankConfig

_INSTRUCTION = (
    "You are the regulatory-reporting agent for bank '{bank}'. Draft a concise Suspicious "
    "Activity Report (SAR) style case file in markdown from the JSON case record the user "
    "provides. Sections: Summary; Timeline of Traced Transactions (table: txn_id, time, from, "
    "to, amount NGN); Funds Leaving Our Perimeter (list boundary edges and receiving "
    "institution); Recommended Actions (within OUR bank only). Use ONLY facts present in the "
    "JSON — never invent transactions, names, or amounts. Note explicitly that visibility ends "
    "at our perimeter."
)


async def draft_report(cfg: BankConfig, case: CaseState) -> str:
    agent = Agent(
        name=f"{cfg.bank}_reporter",
        model=bank_model(cfg),
        instruction=_INSTRUCTION.format(bank=cfg.bank),
    )
    runner = InMemoryRunner(agent=agent, app_name="concordat")
    session = await runner.session_service.create_session(app_name="concordat", user_id="system")
    payload = case.model_dump_json(
        include={
            "case_id",
            "bank",
            "status",
            "opened_at",
            "victim_txn",
            "trace",
            "boundary_edges",
            "summary",
        }
    )
    msg = types.Content(role="user", parts=[types.Part(text=payload)])
    chunks: list[str] = []
    async for event in runner.run_async(user_id="system", session_id=session.id, new_message=msg):
        if event.content and event.content.parts:
            chunks.extend(p.text for p in event.content.parts if p.text)
    return "".join(chunks).strip()
