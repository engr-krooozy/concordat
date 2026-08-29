# ARCHITECTURE.md — Concordat

> Source of truth for the submission's architecture diagram. Export a rendered version to
> `docs/architecture.png` before Aug 27 (diagram is a mandatory submission item).

## System overview

Three sovereign bank fleets (identical codebase, isolated config/IAM/data) + two shared neutral
services (registry, clean-room compiler) + one observer UI. Everything on Cloud Run; all
cross-agent traffic is A2A messages; all intra-case orchestration is Pub/Sub-driven and resumable
from Firestore.

Managed Google Cloud components sit at the three places where a bank would refuse to take our
word for it. **Vertex AI Agent Engine** holds the fleet catalog in the commons — registry
entries are public facts, so cataloging is neutral ground while execution stays sovereign.
**Agent Engine Memory Bank** gives each bank cross-case memory *inside its own project*, so
nothing about one bank's investigative history is legible to a rival. **Model Armor** guards
both edges of every perimeter: a third opinion on text leaving, and prompt-injection screening
on peer prose arriving, because a counterparty's free text is written by a rival's LLM and
lands in the context of ours.

```mermaid
flowchart TB
    subgraph ALPHA["Bank Alpha perimeter (SA: alpha@) — deployed 3x, one image"]
        A_or[ADK Orchestrator]
        A_det[Detector agent]
        A_tr[Tracer agent]
        A_dip[Diplomat agent]
        A_pol[Policy engine<br/>deterministic YAML evaluator]
        A_red[Perimeter gate<br/>rules + local Gemma 3 4B]
        A_enf[Enforcer + Reporter]
        A_bq[(BQ: bank_alpha<br/>~3.5M rows)]
        A_det --> A_tr --> A_bq
        A_dip --> A_pol
        A_dip --> A_red
    end

    subgraph MER["Bank Meridian perimeter (SA: meridian@)"]
        M_fleet[Identical fleet]
        M_bq[(BQ: bank_meridian)]
    end
    subgraph UNI["Bank Union perimeter (SA: union@)"]
        U_fleet[Identical fleet]
        U_bq[(BQ: bank_union)]
    end

    REG[Agent-card Registry<br/>Cloud Run — the agent catalog]
    CR[Clean-room compiler<br/>concordat → room + k-policy views<br/>+ hop chaining + dissolver]
    ROOM[(Ephemeral room<br/>aggregation_threshold_policy<br/>raw SELECT refused by BigQuery)]
    FS[(Firestore<br/>cases, transcripts,<br/>concordats, audit log)]
    PS{{Pub/Sub<br/>case events}}
    UI[Mission Control UI<br/>Next.js on Cloud Run]
    GEM[Vertex AI<br/>Gemini 3.5 Pro / Flash]

    A_dip <-- "A2A: discover" --> REG
    M_fleet <-- "A2A" --> REG
    U_fleet <-- "A2A" --> REG
    A_red <-- "A2A: negotiate<br/>(redacted, hashed)" --> M_fleet
    A_red <-- "A2A: negotiate" --> U_fleet
    A_dip -- "accepted concordat" --> CR
    CR --> ROOM
    A_bq -. "authorized contribution<br/>(hashed ids)" .-> ROOM
    M_bq -.-> ROOM
    U_bq -.-> ROOM
    ROOM -- "joint ring graph<br/>(aggregates)" --> A_enf
    A_or <--> PS
    A_or <--> FS
    UI --> FS
    A_or & A_dip & A_enf --> GEM
```

## The invariants (put these on the diagram slide — they ARE the architecture)

1. **Sovereignty**: each bank is a **separate GCP project** with its own ledger, identity,
   topic and case store. A bank's service account does not appear in any peer's project at
   all, so a cross-perimeter read fails with a 403 from Google rather than a check in our
   code. The only route between banks is a clean room compiled from an accepted concordat.
   Reproduce with `scripts/verify_sovereignty.py`. The commons holds no bank's ledger, and
   that is checkable in one command: `bq ls --project_id=concordat-hack` lists exactly one
   dataset, `ground_truth`, and `gcloud run services list --project=concordat-hack` lists
   exactly two services, `registry` and `mission-control`.
2. **Deterministic veto**: Gemini drafts proposals and reports; the YAML policy evaluator (plain
   code) has final say on anything crossing the boundary. LLMs propose, policy disposes.
3. **Perimeter gate**: every outbound free-text field passes deterministic redaction rules,
   then a Gemma 3 4B running *inside the bank's own container* — the text being checked for
   leaks never leaves the process to be checked — and finally Model Armor, Google's detector
   in the bank's own project, which catches what a regex structurally cannot (a customer's
   name). Rules are the guarantee; the two model layers may only *add* a restriction, and the
   audit line names only the layers that actually answered. The gate fails closed on a finding
   and open on an outage, because a scanner being unreachable must not strand the federation.
   Inbound is screened too: peer-authored `rationale`, `note` and computation descriptions pass
   Model Armor's prompt-injection filter before our agents read them, and an attempt is
   rejected as a policy violation attributable to the bank that sent it. Identifiers leave only
   as salted hashes, and only in sets of at least k.
4. **Ephemerality**: rooms carry the concordat's TTL. Dissolution is *cooperative*, not central:
   the room runner drops the room, and each bank revokes its own contribution view — the runner
   has no delete rights inside anyone's dataset. The audit record is the only survivor.
5. **Asynchrony**: no request/response chains across the system — Pub/Sub events + Firestore
   state; any service can die mid-case and the case resumes. Resumption is the whole point and
   it has to hold at every step, not just at the clean hand-offs: a handler must be able to
   pick a case up from whatever state its previous attempt died in (`RESUMABLE_FROM` in
   `services/bank/case.py`), or a Pub/Sub redelivery is silently dropped and the case is
   stranded. `case-cdbca153` stopped mid-parley on Aug 22 and resumed on Aug 27.
6. **Auditability**: every negotiation round, policy verdict, clean-room query, and enforcement
   action is an append-only Firestore audit entry with actor + timestamp + payload hash.
7. **Memory is sovereign too**: each fleet's cross-case memory lives in that bank's own Memory
   Bank, in that bank's own project. Only k-thresholded aggregates go in — the shape of a
   network, never a person — so a store that outlives the case cannot become the back door
   through which an individual escapes the perimeter that protected them.

## Case lifecycle (state machine)

```
detected → tracing → dead_end → discovering → negotiating ⇄ countering
   → agreed → room_active → joint_analysis → awaiting_approval → enforcing → closed
                    ↘ rejected (terminal, audit-logged — the governance demo path)
```

## Negotiation protocol (A2A message types)

| Message | Sender | Content |
|---|---|---|
| `InvestigationRequest` | initiating diplomat | case summary (redacted), requested computations, proposed k/TTL |
| `PolicyVerdict` | responding policy engine | accept / reject with violated-rule references |
| `CounterProposal` | responder | narrowed computations / raised k / shorter TTL |
| `ConcordatSigned` | both | final terms; hash of terms doubles as clean-room config key |
| `ContributionRequest` | initiator | probe set (>= k hashes), room, k, salt, window |
| `ContributionReceipt` | peer | k-thresholded aggregate only — never rows |
| `RevokeContribution` | initiator | asks a peer to withdraw its own view |
| `RoomDissolved` | peer/compiler | closure record for all parties' audit logs |

All messages: Pydantic-validated, transcript-persisted, replayable in the UI.

## Where each judging axis is won

- **Innovation/utility (40%)**: the negotiation layer + federated model (see SPEC novelty ledger).
- **Architecture (30%)**: the seven invariants above; one parameterized bank image deployed 3×;
  event-driven long-running cases.
- **Demo/production-readiness (30%)**: IAM-proven isolation, audit trail, approval gates,
  CI/CD, deterministic `make demo`.
