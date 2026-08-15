# PLAN.md — Concordat day-by-day build plan

17 days: **Aug 15 → Aug 31, 2026**. Deadline Aug 31 5:00 PM PDT = **Sep 1 1:00 AM WAT**;
internal hard stop: **Aug 31, 6:00 PM WAT** (submit with 7h buffer).

Principles: backend golden path before UI; the novel 40% (negotiation + policy engine + clean-room
compiler) gets the middle of the schedule when energy is highest; last 4 days are submission-only —
**no new features after Aug 27**.

Each day ends with a checkpoint. If a checkpoint slips 2 days, cut scope per the cut-list at the
bottom, never the demo polish days.

---

## Phase 0 — Foundations (Aug 15–16)

**Aug 15 (Fri) — Repo, GCP, verification of assumptions**
- [ ] `git init`, push new private GitHub repo `concordat`
- [ ] Create GCP project `concordat-hack`, enable billing + APIs (Vertex AI, BigQuery, Run,
      Pub/Sub, Firestore, Analytics Hub, Cloud Build)
- [ ] **Verify live**: Gemini 3.5 model IDs on Vertex AI; `a2a-sdk` / ADK A2A support versions;
      Analytics Hub clean rooms availability in chosen region (pick one region, likely `us-central1`)
- [ ] Name check: "Concordat" on Devpost + trademark sanity search → lock name
- [ ] Register on Devpost, start submission draft (saves panic later)
- [ ] Scaffold repo per SPEC structure; Makefile; ruff/pytest wired
- ✅ Checkpoint: `make test` green on empty skeleton; GCP project live; model IDs confirmed

**Aug 16 (Sat) — Synthetic ledger generator**
- [ ] `data/generator`: 3 banks × ~3.5M transactions, deterministic seed
- [ ] Planted patterns: 1 cross-bank mule ring (the golden path), 1 intra-bank ring (red herring),
      structuring/velocity noise, benign traffic
- [ ] Load to 3 BQ datasets (`bank_alpha`, `bank_meridian`, `bank_union`) with separate SAs; IAM:
      each bank SA can read ONLY its own dataset
- ✅ Checkpoint: 10M+ rows in BQ; a hand-written SQL trace confirms the planted ring exists and
  genuinely dies at each bank's boundary

## Phase 1 — One sovereign fleet (Aug 17–19)

**Aug 17 (Sun) — Bank fleet skeleton (ADK)**
- [ ] `services/bank`: ADK root orchestrator + `detector` (finds suspicious pattern) +
      `tracer` (iterative BQ hop-tracing tool calls)
- [ ] Runs locally against `bank_alpha`; produces a trace that ends at a boundary account
- ✅ Checkpoint: local run prints a case with N hops and a dead-end marker

**Aug 18 (Mon) — Async case machinery**
- [ ] Firestore case state (status machine: detected → tracing → dead_end → negotiating → joint →
      enforcing → closed); Pub/Sub topics + push handlers drive every transition
- [ ] `reporter` agent: SAR-style case file (Gemini 3.5 Pro) from case state
- ✅ Checkpoint: publish one "kickoff" message → case runs to `dead_end` unattended, state fully
  in Firestore, resumable

**Aug 19 (Tue) — First deploy**
- [ ] Cloud Build → Cloud Run for bank service (deployed once as bank-alpha); Secret Manager; logs clean
- ✅ Checkpoint: the Aug 18 flow works entirely on Cloud Run (this satisfies "deployment proof" early)

## Phase 2 — The novel core: diplomacy (Aug 20–23) ← the win is built here

**Aug 20 (Wed) — A2A discovery + registry**
- [ ] `services/registry`: agent-card registry (the "agent catalog"); each bank publishes a card
      (capabilities: joint-trace, hashed-id scheme, contact endpoint)
- [ ] Deploy bank-meridian + bank-union (same image, different config/SA)
- [ ] Bank-alpha's `diplomat` agent discovers counterparts via registry
- ✅ Checkpoint: three fleets on Cloud Run; alpha lists two counterpart cards

**Aug 21 (Thu) — Negotiation protocol + policy engine**
- [ ] `NegotiationProposal` / counter / accept / reject message types over A2A; state machine with
      full transcript persisted to Firestore
- [ ] `policy/`: YAML data-sharing policy per bank (allowed computations, min k, max TTL, banned
      fields) + deterministic evaluator; Gemini drafts proposals, **policy engine has veto**
- [ ] Deliberately different policies per bank so one **counter-offer round occurs naturally**
      (e.g. meridian requires k≥25, alpha proposes k=10 → counter)
- ✅ Checkpoint: contract tests green; live run shows propose → reject(policy) → narrowed
  counter → accept, all audit-logged

**Aug 22 (Fri) — Perimeter gate (Gemma) + clean-room compiler**
- [ ] `redactor`: Gemma 3 (Ollama sidecar or Cloud Run GPU) classifies/redacts every outbound
      A2A payload; salted-hash identifier scheme
- [ ] `services/cleanroom`: compile an accepted concordat → Analytics Hub clean room (or
      authorized-views fallback — **decide today per SPEC open question 3**) + joint-query builder
      (aggregation thresholds enforced in SQL)
- ✅ Checkpoint: accepted concordat produces a queryable joint view; raw cross-reads provably blocked

**Aug 23 (Sat) — Golden path end-to-end**
- [ ] Joint trace resolves the planted cross-bank ring; results (k-thresholded aggregates +
      hashed graph edges) returned to each fleet; `enforcer` agent stages per-bank actions behind
      an approval flag; room dissolution + final audit record
- ✅ Checkpoint: **`make demo` runs detection → diplomacy → clean room → ring → reports,
  unattended, on Cloud Run.** Backend feature-complete. (Slack day if slipped.)

## Phase 3 — Mission control UI (Aug 24–26)

**Aug 24 (Sun) — UI skeleton**
- [ ] Next.js on Cloud Run; three bank panels streaming case state (Firestore listeners);
      negotiation transcript feed with policy verdict badges
- ✅ Checkpoint: watching `make demo` live in the browser

**Aug 25 (Mon) — The money shot**
- [ ] Ring graph viz (cytoscape): each bank's fragment shown separately/greyed, then the joint
      graph materializing across all three panels on clean-room completion
- [ ] Approval-gate UI (analyst clicks approve → enforcement runs)
- ✅ Checkpoint: the 30-second sequence that wins the video works on screen

**Aug 26 (Tue) — Hardening + governance drama**
- [ ] Failed-negotiation path demoable (over-broad proposal rejected on screen)
- [ ] Audit-trail view; IAM tightening pass; error paths (timeout, counterpart offline)
- ✅ Checkpoint: demo runs twice in a row from `make seed` reset with zero manual fixes

## Phase 4 — Submission (Aug 27–31) — no new features

**Aug 27 (Wed)** — Full rehearsal ×3; fix timing/seed so the story lands in <3 min of runtime;
final architecture diagram (export `docs/architecture.png`); README with reproducible setup.
**Aug 28 (Thu)** — Write video script (SUBMISSION.md outline); record screen + voiceover;
capture Cloud console/logs shots with `.run.app` URL visible.
**Aug 29 (Fri)** — Edit video ≤4:00, English subtitles; write blog post (bonus) + social post
with `#AllThingsAgenticHackathon` (bonus).
**Aug 30 (Sat)** — Complete Devpost submission draft end-to-end: description, repo access for
judges, hosted URL, diagram, video link. Dry-run README on a clean machine/VM. Buffer.
**Aug 31 (Sun)** — Final read-through, **submit by 6 PM WAT**. Freeze the deployment; leave
services up through judging (Sep 1–?, per rules).

---

## Cut-list (in order, if behind schedule)
1. Cloud Run GPU Gemma → Ollama CPU with Gemma 1B (keep the bonus, shrink the model)
2. Analytics Hub clean room → authorized views + SQL-enforced thresholds (same guarantees)
3. Approval-gate UI → approval via signed URL / CLI shown in video
4. Third bank → two banks (ring still crosses a boundary; less spectacle, same novelty)
5. Blog post bonus (keep hashtag post — it's cheap)

## Risk register
| Risk | Mitigation |
|---|---|
| A2A SDK immaturity/breaking changes | Verify day 1; wrap all A2A I/O behind our own thin interface so we can swap to plain HTTPS+schema if needed (still "A2A-compatible messages") |
| Clean Rooms setup friction | Fallback pre-approved (open question 3), decision gate Aug 22 |
| Gemini 3.5 quota/latency on Vertex | Request quota day 1; Flash for loops, Pro only where it matters; cache demo-path prompts |
| Demo flakiness on video day | `make demo` determinism is a hard requirement (Aug 26 checkpoint); record in segments |
| Solo-builder illness/day job | Every phase checkpoint is independently submittable; worst case, Phase 2 output (Aug 23) + minimal UI is still a novel, complete submission |
