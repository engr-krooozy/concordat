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
   - `make test` green; Vertex AI quota not exhausted (one smoke Gemini call)
   - UI shows three empty bank panels, no stale cases
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

## Judge mode

`scripts/judge_replay.sh` (build by Aug 30): replays the golden path against the deployed
environment with no GCP setup, for README quickstart.
