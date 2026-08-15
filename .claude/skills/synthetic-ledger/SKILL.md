---
name: synthetic-ledger
description: Generate, extend, or reseed the Concordat synthetic transaction data — 3 bank ledgers with planted cross-bank fraud patterns loaded to BigQuery. Use when changing data volume, ring topology, demo timing, or adding noise patterns.
---

# Synthetic Ledger

Source: `data/generator/`. Deterministic — same seed, same bytes. The demo's narrative timing
depends on the planted ring's shape, so treat topology changes as demo changes (rerun /demo-day
rehearsal after any edit).

## Invariants

- 3 banks (`alpha`, `meridian`, `union`), ~3.5M rows each, ≥10M total (submission claims this —
  keep it true)
- Schema (all banks identical): `txn_id, ts, src_account, dst_account, dst_bank, amount,
  currency, channel, narration` — `dst_bank != self` marks a boundary edge (where solo traces die)
- Planted patterns, each tagged in a private `ground_truth` table (never exposed to agents):
  1. **golden ring** — victim at alpha → 3 mule hops in alpha → boundary → 2 hops in meridian →
     boundary → cash-out cluster in union (fan-in ≥ 6 accounts, so k-thresholds still reveal it)
  2. **red-herring ring** — fully inside meridian (proves solo detection works and isn't the demo)
  3. structuring noise (just-under-threshold bursts), velocity noise, benign bulk traffic
- Accounts are synthetic (faker-style, Nigerian-flavored names/narrations are fine); no real
  person or institution names; bank names only Alpha/Meridian/Union

## Workflow

1. Edit generator config (`data/generator/config.yaml`): volumes, seed, ring topology
2. `make seed` — regenerates locally, loads to the 3 BQ datasets + `ground_truth`, prints row
   counts and ring summary
3. Sanity SQL (in `data/generator/checks/`): ring exists, dies at boundaries under
   single-dataset access, red herring resolvable solo
4. If topology changed: run /demo-day rehearsal and re-check beat timings

## Gotchas

- Keep the golden ring's cash-out fan-in above the largest policy `k` (currently 25) or the
  joint query will lawfully hide the finale of our own demo
- BQ load uses each bank's own SA — if a load fails with 403, that's the IAM sovereignty
  invariant working; use the loader SA, don't widen bank SAs
