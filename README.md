# Concordat

> Sovereign AI agent fleets, owned by rival banks, that **negotiate** privacy-safe joint fraud
> investigations — then compile the agreement into an ephemeral BigQuery clean room, catch the
> cross-bank ring, act only inside their own perimeters, and dissolve the room.

Entry for the **All Things Agentic Hackathon** (Devpost, Aug 2026) — Fortified Enterprise Fleet
track. Built solo, Aug 3–31 2026.

**Docs:** [SPEC.md](SPEC.md) · [PLAN.md](PLAN.md) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
[SUBMISSION.md](SUBMISSION.md)

## Stack

Gemini 3.5 (Vertex AI) · Google ADK + A2A protocol · Gemma 3 (local perimeter gate) ·
Cloud Run · Pub/Sub · Firestore · BigQuery (+ Analytics Hub clean rooms) · Next.js

## Quickstart

```bash
make seed      # generate + load synthetic ledgers (3 banks, 10M+ rows)
make test      # unit + contract tests
make demo      # run the golden-path investigation end to end
```

(Reproducible setup instructions land with the code — see PLAN.md for the build schedule.)
