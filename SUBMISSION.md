# SUBMISSION.md — Devpost checklist, video script, positioning

Deadline: **Aug 31, 2026, 5:00 PM PDT = Sep 1, 1:00 AM WAT. Internal stop: Aug 31, 6 PM WAT.**
Track entered: **The Fortified Enterprise Fleet**. Also eligible: Individual/Hobbyist (if solo),
Best Architectural Design, Grand Prize.

## Live deployment — four GCP projects (re-verified 2026-08-29)

Each bank is a **separate project**. The differing Cloud Run hostname hashes below are
themselves evidence: these services were not deployed side by side.

| What | Project | URL |
|---|---|---|
| **Hosted project (public)** | concordat-hack | https://mission-control-fa7ntw3nkq-uc.a.run.app |
| Bank Alpha fleet (private) | concordat-alpha | https://bank-alpha-4u5ubaqvyq-uc.a.run.app |
| Bank Meridian fleet (private) | concordat-meridian | https://bank-meridian-omz2lybk2q-uc.a.run.app |
| Bank Union fleet (private) | concordat-union | https://bank-union-ui3fivllxa-uc.a.run.app |
| Registry fallback (private) | concordat-hack | https://registry-fa7ntw3nkq-uc.a.run.app |

The catalog of record is **Vertex AI Agent Engine** in `concordat-hack`; the registry service
above stays as a fallback so a catalog outage cannot strand the federation. Each bank also
holds its own **Memory Bank** and its own **Model Armor** templates inside its own project.

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

- [x] Functional project meeting track criteria — verified end to end in production 29 Aug
- [x] **Hosted project URL** — https://mission-control-fa7ntw3nkq-uc.a.run.app (public, verified)
- [x] Text description — `docs/devpost-description.md`, current as of 29 Aug (paste into Devpost)
- [ ] **Code repository — grant judge access.** Private GitHub is allowed; without this the
      submission cannot be judged at all, so do it first
- [x] README.md with reproducible setup, a judge quickstart, and `judge_replay.sh`, which the
      dashboard serves at `/judge_replay.sh` so the quickstart genuinely needs no clone, no
      credentials and no GCP project (they said they run your code)
- [x] **Architecture diagram** — `docs/architecture.png` (3000x1875, hand-built; source
      `docs/architecture.svg`). Redrawn 29 Aug for the four managed components
- [ ] Demo video ≤ **4:00**, shows problem, value prop, live demo, **backend running on Google
      Cloud (logs / console / .run.app visible)**, English subtitles
- [ ] No third-party branding/unlicensed material in video (invent bank names/logos:
      Alpha, Meridian, Union — original artwork only)
- [ ] Newly created during Aug 3–31 ✓ (repo history proves it)
- [ ] Tech requirements visible: Gemini 3.5+ (Vertex AI), ADK + A2A, Cloud Run, Pub/Sub,
      Firestore, BigQuery

## Agent-platform components (named by the judges in the live Q&A)

The Fortified Enterprise Fleet Q&A said outright: *"we do prefer if you can use the agent
registry from the agent platform inside Google Cloud… if we are picking the winner we'll
prefer somebody that has implemented with the agent registry."* And, on what to show:
*"just show us that you have agent runtime, memory bank, and model armor and what you're
using them for."*

- [x] **Agent registry** — Vertex AI Agent Engine holds the fleet catalog in the commons;
      `diplomat.discover()` reads it, with our own registry service as fallback. Verified in
      production: `discovered 2 fleets via Agent Engine: ['meridian', 'union']`
- [x] **Memory Bank** — one per bank, in that bank's own project. Ring shapes and
      counterparty behaviour carry across cases; only k-thresholded aggregates go in
- [x] **Model Armor** — outbound third opinion (DLP inspect template, because basic SDP does
      not fire on a person's name) and inbound prompt-injection screening on peer prose.
      Verified live: injection MATCH_FOUND at HIGH confidence, ordinary proposals clean.
      Production gate line reads `passed (rules+gemma+armor)`
- [x] **Agent runtime** — deliberately *not* Agent Engine. Each fleet runs on Cloud Run inside
      its own project. Say this out loud rather than hiding it: three rival banks' investigators
      sharing one managed runtime is the exact arrangement this project argues against, and a
      judge who notices the choice should hear the reason

## Bonus points (up to 0.6)

- [x] **Gemma** integration — Gemma 3 4B in-container perimeter gate; model size chosen by a measured eval (`scripts/eval_gemma_gate.py`), which is itself worth a line in the video
- [x] **Multimodal** — a case is opened by a customer's *voice note*; Gemini extracts the
      account, amount and window and writes the report the tracer reads. Opens the Best
      Multimodal category, and it is how fraud is actually reported in Nigerian retail banking
- [ ] Blog post — `docs/blog-post.md` is written and current ("I taught rival banks' AI agents
      to negotiate with each other", six failures, ~1,900 words). **Publish it.** Cheapest
      points on the board and the only ones still unclaimed
- [ ] Social post with `#AllThingsAgenticHackathon` linking the blog

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
| 0:25–0:45 | **Claim.** "Concordat: agent fleets that negotiate joint investigations — raw data never leaves any bank." One-slide architecture (invariants condensed to 3 bullets) | |
| 0:45–1:15 | **Solo failure.** Mission control: Bank Alpha's fleet detects, traces 4 hops, hits the wall. Case state → `dead_end`. VO explains async: "no chat window — this ran in the background." | Live UI |
| 1:15–2:15 | **The negotiation (the star).** A2A discovery via registry; proposal appears; Meridian's policy engine **rejects** (k too low) with the violated rule on screen; counter-proposal; all sign. VO: "Gemini drafts. Policy — deterministic code — disposes." | Live transcript feed, policy verdict badges |
| 2:15–2:50 | **The money shot.** Clean room spins up (Cloud console flash); joint graph materializes across all three panels; the full ring lights up. Gemma redaction log ticker at the bottom. | Rehearsed to land < 30s |
| 2:50–3:15 | **Governance.** Analyst approval gate → per-bank enforcement → SAR reports → room dissolved; audit trail scroll. | |
| 3:15–3:45 | **Proof + close.** Cloud Run services list, Pub/Sub throughput, BQ row counts (10M+), `.run.app` URL on screen. "Built solo in 17 days with ADK, A2A, Gemini 3.5, Gemma. Data diplomacy — a new job for agent fleets." | Mandatory GCP proof lives here |

Record scenes separately; UI runs from deterministic `make demo`. Subtitles burned in.

## Judge-access notes

- All five services carry `--min-instances=1` in `infra/cloudbuild.yaml`, so they stay warm
  through judging and a peer is never cold when a fleet reaches for it (~$3-5/day; drop to 0
  after judging). Budget alert at $100.
- Seed a fresh demo case daily during judging (Cloud Scheduler) so the UI is never empty when a
  judge opens the URL.
- `scripts/judge_replay.sh` is judge mode, and it is done: it walks a real case beat by beat
  against the live deployment with nothing but `curl` and `python3`. `APPROVE=1` exercises the
  human gate. It is also served from the public dashboard at `/judge_replay.sh`, because the
  README promised "no clone" while requiring one to obtain the file.
- **Local scripts need ADC on the gmail account.** Anything that impersonates a bank service
  account fails with an IAM error naming `iam.serviceAccounts.getAccessToken` if ADC is a work
  account. `gcloud auth application-default login`, then
  `gcloud auth application-default set-quota-project concordat-hack`.
- Sixteen cases sit at the approval gate. Approving is one-way — a closed case cannot return —
  so spend a different one on each take, and do not approve a case whose concordat has expired
  expecting it to work: the gate refuses it on purpose.

## Order for the last hours

Christina's closing advice in the judging Q&A was to submit first and refine after, because an
unsubmitted project scores zero however good it is. So:

1. **Grant judge access to the repo.** Everything else is worthless without it.
2. **Submit the Devpost form** with the description, diagram, and repo — even before the video
   is cut. The form can be edited until the deadline; a missed deadline cannot.
3. **Shoot the video** while the system is warm (`scripts/test_a2a_cloud.py` returns in
   seconds if it is). Run of show and per-screen directions are in the two companion guides.
4. **Publish the blog**, then the social post with the hashtag. Up to 0.6 bonus points for
   maybe an hour of work.
5. Re-run the pre-flight the morning of judging: `make test`, `scripts/test_armor.py`,
   `scripts/verify_sovereignty.py`, and confirm the dashboard's newest case is dated today.
