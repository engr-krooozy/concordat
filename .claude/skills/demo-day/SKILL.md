---
name: demo-day
description: Reset, run, and film the Concordat golden-path demo — deterministic end-to-end run for rehearsal, judging, and video capture. Use when asked to run the demo, rehearse, record the video, or when a judge-facing environment must be verified.
---

# Demo Day

Purpose: make the golden path boringly repeatable. The demo is a submission artifact, not a
byproduct — flakiness here is P0.

## Procedure

1. **Reset state**: `make seed` (re-loads the 3 BQ datasets from the fixed seed) then clear
   Firestore case collections (`make demo` does both when implemented — keep it that way).
2. **Pre-flight** (all must pass before filming or judge access):
   - Three bank services + registry + UI serving on Cloud Run. Check `/health`, NOT
     `/healthz` — Google's frontend answers that exact path with its own 404 before the
     request reaches the container, so it looks broken however healthy the service is.
     For the private services use `gcloud run services list` per project.
   - `make test` green (61 tests, no cloud needed); Vertex AI quota not exhausted
   - **ADC is the gmail account, not a work one.** Every local script that impersonates a
     bank service account dies without it, and the error names an IAM permission rather than
     the real cause. Check with `gcloud auth application-default login` if anything 403s on
     `iam.serviceAccounts.getAccessToken`.
   - The managed components answer: `python -m scripts.test_armor` (6/6 live),
     `python -m scripts.demo_injection` (2 stopped by armor, 1 by policy, 1 accepted),
     and a production gate line reading `rules+gemma+armor`
   - UI shows a case dated today, and enough parked at `awaiting_approval` to spend
3. **Run**: `make demo` — publishes the kickoff event for the planted cross-bank ring.
   Expected beats and rough timings (tune seed, not narration, if these drift):
   - < 20s: Alpha detects + traces to `dead_end`
   - < 40s: A2A discovery + first proposal
   - ~60s: Meridian policy **rejection** (k threshold) → counter → all sign
   - < 90s: clean room active, joint graph materializes across all panels
   - < 120s: approval gate → enforcement → reports → room dissolved
4. **Verify isolation after every run**: audit log contains zero direct cross-dataset reads;
   redactor log shows every outbound payload gated.
5. **Filming** (per SUBMISSION.md script): record scenes separately at 1080p+; keep Cloud
   console tabs pre-opened (Run services list, Pub/Sub metrics, BQ row counts) for the proof
   scene; `.run.app` URL must be visible in the browser bar.

## Failure triage

- Beat timing drifted → adjust generator seed/ring shape, never speed up narration
- Negotiation skips the rejection round → check the banks' policy YAMLs still differ (k values)
- Empty UI at judge time → Cloud Scheduler daily reseed job down; run step 1 manually
- Approval button does nothing → check `BANK_<X>_URL` still on mission-control. A deploy that
  uses `--set-env-vars` instead of `--update-env-vars` wipes them and every approve 500s.
- Gate line says `rules+gemma` without `armor` → the package is missing from the image. The
  Dockerfile pins its own dependency list; adding to pyproject alone changes nothing.
- A voice case stalls at `detected` → the intake could not resolve a date. Callers never say
  the year, so the extraction resolves it against the bank's clock; check `when_date` in the
  `voice_note` audit line is an ISO date and not empty.
- An approval is refused as stale → working as designed. The concordat's TTL has lapsed, so
  the terms permitting enforcement have expired. Park a fresher case; do not extend the TTL
  to make a demo work.

## Judge mode

`scripts/judge_replay.sh` — walks a real case against the live deployment with no clone, no
credentials and no GCP project; `APPROVE=1` exercises the human gate. Linked from the README
quickstart, because the judging Q&A said outright that they run your code.
