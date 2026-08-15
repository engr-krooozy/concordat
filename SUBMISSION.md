# SUBMISSION.md — Devpost checklist, video script, positioning

Deadline: **Aug 31, 2026, 5:00 PM PDT = Sep 1, 1:00 AM WAT. Internal stop: Aug 31, 6 PM WAT.**
Track entered: **The Fortified Enterprise Fleet**. Also eligible: Individual/Hobbyist (if solo),
Best Architectural Design, Grand Prize.

## Live deployment — four GCP projects (verified 2026-08-15)

Each bank is a **separate project**. The differing Cloud Run hostname hashes below are
themselves evidence: these services were not deployed side by side.

| What | Project | URL |
|---|---|---|
| **Hosted project (public)** | concordat-hack | https://mission-control-fa7ntw3nkq-uc.a.run.app |
| Bank Alpha fleet (private) | concordat-alpha | https://bank-alpha-4u5ubaqvyq-uc.a.run.app |
| Bank Meridian fleet (private) | concordat-meridian | https://bank-meridian-omz2lybk2q-uc.a.run.app |
| Bank Union fleet (private) | concordat-union | https://bank-union-ui3fivllxa-uc.a.run.app |
| Agent-card registry (private) | concordat-hack | https://registry-fa7ntw3nkq-uc.a.run.app |

Verified anonymously end to end: the dashboard aggregates case state from three separate
Firestores, and the approval button reaches across a project boundary to drive a case from
`awaiting_approval` through `enforcing` to `closed`, with the approver in the audit trail.

**The claim worth making in the video:** `scripts/verify_sovereignty.py` shows no bank's
identity appears in any peer's project, then has Alpha's fleet read its own ledger
(3,743,998 rows) and a peer's (403 from Google). In one project you can only show you chose
not to grant access. Across projects, the access does not exist to grant.

**Known limitation to state plainly if asked:** the approval endpoint is unauthenticated so
judges can exercise the gate. In production it would sit behind the bank's SSO — the gate's
purpose is to prove a *human* decided, and that property is unchanged. All data is synthetic.

## Mandatory checklist (from hackathon rules — verify each before submitting)

- [ ] Functional project meeting track criteria
- [x] **Hosted project URL** — https://mission-control-fa7ntw3nkq-uc.a.run.app (public, verified)
- [x] Text description — drafted in `docs/devpost-description.md` (paste into Devpost)
- [ ] Code repository (private GitHub OK — grant judge access per Devpost instructions)
- [ ] README.md with **reproducible setup** (dry-run on clean machine Aug 30)
- [x] **Architecture diagram** — `docs/architecture.png` (3000x1875, hand-built; source `docs/architecture.svg`)
- [ ] Demo video ≤ **4:00**, shows problem, value prop, live demo, **backend running on Google
      Cloud (logs / console / .run.app visible)**, English subtitles
- [ ] No third-party branding/unlicensed material in video (invent bank names/logos:
      Alpha, Meridian, Union — original artwork only)
- [ ] Newly created during Aug 3–31 ✓ (repo history proves it)
- [ ] Tech requirements visible: Gemini 3.5+ (Vertex AI), ADK + A2A, Cloud Run, Pub/Sub,
      Firestore, BigQuery

## Bonus points (up to 0.6)

- [x] **Gemma** integration — Gemma 3 4B in-container perimeter gate; model size chosen by a measured eval (`scripts/eval_gemma_gate.py`), which is itself worth a line in the video
- [x] Blog post drafted — `docs/blog-post.md` ("I taught rival banks' AI agents to negotiate
      with each other"). Publish to dev.to/Medium by Aug 29 — **needs Mustapha to post**
- [ ] Social post with `#AllThingsAgenticHackathon` linking the blog — Aug 29

## Positioning (use consistently: Devpost description, video VO, blog)

**One-liner:** *Concordat is a fleet of sovereign AI agents that lets rival banks jointly hunt
fraud rings none of them can see alone — by negotiating, not by sharing data.*

**The category claim:** "data diplomacy" — autonomous negotiation of inter-organizational data
collaboration. State the novelty ledger honestly (SPEC.md): A2A, clean rooms, and central
consortia all exist; the negotiation layer that compiles agreements into ephemeral infrastructure
does not.

**Track keyword mapping (say these words):** agent cataloging (A2A card registry) · long-running
asynchronous operations (Pub/Sub cases) · context persistence (Firestore) · compliance
enforcement (deterministic policy veto) · production-level security governance (IAM sovereignty,
approval gates, append-only audit).

## Video script (target 3:45)

| t | Scene | Notes |
|---|---|---|
| 0:00–0:25 | **Problem.** Map of a fraud ring spanning 3 banks; each bank's view fragments and greys out. VO: "The same mule ring hits five banks. Privacy law means no one sees the whole picture." | Motion graphic, no product yet |
| 0:25–0:45 | **Claim.** "Concordat: agent fleets that negotiate joint investigations — raw data never leaves any bank." One-slide architecture (six invariants condensed to 3 bullets) | |
| 0:45–1:15 | **Solo failure.** Mission control: Bank Alpha's fleet detects, traces 4 hops, hits the wall. Case state → `dead_end`. VO explains async: "no chat window — this ran in the background." | Live UI |
| 1:15–2:15 | **The negotiation (the star).** A2A discovery via registry; proposal appears; Meridian's policy engine **rejects** (k too low) with the violated rule on screen; counter-proposal; all sign. VO: "Gemini drafts. Policy — deterministic code — disposes." | Live transcript feed, policy verdict badges |
| 2:15–2:50 | **The money shot.** Clean room spins up (Cloud console flash); joint graph materializes across all three panels; the full ring lights up. Gemma redaction log ticker at the bottom. | Rehearsed to land < 30s |
| 2:50–3:15 | **Governance.** Analyst approval gate → per-bank enforcement → SAR reports → room dissolved; audit trail scroll. | |
| 3:15–3:45 | **Proof + close.** Cloud Run services list, Pub/Sub throughput, BQ row counts (10M+), `.run.app` URL on screen. "Built solo in 17 days with ADK, A2A, Gemini 3.5, Gemma. Data diplomacy — a new job for agent fleets." | Mandatory GCP proof lives here |

Record scenes separately; UI runs from deterministic `make demo`. Subtitles burned in.

## Judge-access notes

- Keep all Cloud Run services deployed and warm through judging; set min-instances=1 on UI +
  registry for judging window; budget alert at $100.
- Seed a fresh demo case daily during judging (Cloud Scheduler) so the UI is never empty when a
  judge opens the URL.
- README quickstart must include a "judge mode": one script that replays the golden path against
  the deployed environment without any GCP setup.
