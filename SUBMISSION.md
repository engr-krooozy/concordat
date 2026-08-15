# SUBMISSION.md — Devpost checklist, video script, positioning

Deadline: **Aug 31, 2026, 5:00 PM PDT = Sep 1, 1:00 AM WAT. Internal stop: Aug 31, 6 PM WAT.**
Track entered: **The Fortified Enterprise Fleet**. Also eligible: Individual/Hobbyist (if solo),
Best Architectural Design, Grand Prize.

## Mandatory checklist (from hackathon rules — verify each before submitting)

- [ ] Functional project meeting track criteria
- [ ] **Hosted project URL** (mission-control UI `.run.app` URL)
- [ ] Text description: features, tech stack, data sources, learnings
- [ ] Code repository (private GitHub OK — grant judge access per Devpost instructions)
- [ ] README.md with **reproducible setup** (dry-run on clean machine Aug 30)
- [ ] **Architecture diagram** (`docs/architecture.png` from ARCHITECTURE.md)
- [ ] Demo video ≤ **4:00**, shows problem, value prop, live demo, **backend running on Google
      Cloud (logs / console / .run.app visible)**, English subtitles
- [ ] No third-party branding/unlicensed material in video (invent bank names/logos:
      Alpha, Meridian, Union — original artwork only)
- [ ] Newly created during Aug 3–31 ✓ (repo history proves it)
- [ ] Tech requirements visible: Gemini 3.5+ (Vertex AI), ADK + A2A, Cloud Run, Pub/Sub,
      Firestore, BigQuery

## Bonus points (up to 0.6)

- [ ] **Gemma** integration (perimeter redaction gate) — call it out explicitly in description + video
- [ ] Blog post on public platform (dev.to / Medium): "Data diplomacy: teaching rival banks'
      agent fleets to negotiate" — publish Aug 29
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
