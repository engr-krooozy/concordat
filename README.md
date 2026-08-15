# Concordat

> Sovereign AI agent fleets, owned by rival banks, that **negotiate** privacy-safe joint fraud
> investigations — then compile the agreement into an ephemeral BigQuery clean room, catch the
> cross-bank ring, act only inside their own perimeters, and dissolve the room.

Entry for the **All Things Agentic Hackathon** (Devpost, Aug 2026) — *Fortified Enterprise
Fleet* track. Built solo, Aug 2026.

**Docs:** [SPEC.md](SPEC.md) · [PLAN.md](PLAN.md) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
[SUBMISSION.md](SUBMISSION.md)

---

## The problem

The same mule network hits five banks at once. Each bank sees one fragment of the trail, and
privacy law forbids them from pooling raw customer data — so cross-institution rings are
systematically under-detected. Existing consortia solve this by shipping everything to one
central provider, which is the arrangement privacy teams resist most.

## What Concordat does

Each bank runs its own fleet inside its own perimeter. When a trace dies at a boundary, the
fleet doesn't give up — it **parleys**:

1. **Discovers** counterpart fleets through an A2A agent-card registry.
2. **Negotiates** the terms of a joint investigation. Gemini drafts the ask; a deterministic
   policy engine on each side decides. Banks counter-offer, and the strictest terms win.
3. **Compiles** the signed agreement into an ephemeral BigQuery clean room where every
   contribution carries an `aggregation_threshold_policy` — BigQuery itself refuses to return
   a row, so no party can read another's ledger even by accident.
4. **Acts** only inside its own walls, behind a human approval gate.
5. **Dissolves** the room. Each bank revokes its own contribution; only the audit trail survives.

A verified run: Alpha traced ₦2.4M through 30 mule accounts to its boundary and stopped.
Meridian countered its opening terms (k 10 → 25, TTL 72h → 48h); Union countered too; all three
signed at the strictest terms. The room revealed **30 mule accounts across all three banks,
₦2,316,720 concentrated at a single ATM cluster** — a finding no bank could reach alone. An
analyst approved, and Alpha froze 30 of *its own* accounts. Peers' customers were never named.

## Stack

Gemini 3.5 Flash (Vertex AI) · Google ADK · A2A protocol · **Gemma 3 4B running locally in each
bank's container** · Cloud Run · Pub/Sub · Firestore · BigQuery with aggregation-threshold
privacy policies.

## Try it

Prerequisites: `gcloud` authenticated, Python 3.12, and four GCP projects with billing —
one commons plus one per bank. The project boundary *is* the security model.

```bash
python3 -m venv .venv && .venv/bin/pip install -e .   # or: uv venv && uv pip install -e .
make test                                             # 32 tests, no cloud needed

# commons: neutral ground only (registry, mission control, clean rooms)
bash infra/setup_deploy.sh          # artifact registry + build permissions
bash infra/setup_cleanroom.sh       # the neutral room-runner identity
bash infra/setup_ui.sh              # the observatory identity

# one sovereign perimeter per bank, each in its OWN project
for bank in alpha meridian union; do bash infra/federate.sh $bank; done

make seed        # 11.2M synthetic rows; each ledger loads into its own project
make deploy      # one image -> three projects, plus registry and mission control
bash infra/setup_deploy.sh --push               # Pub/Sub push subscriptions per project
bash infra/setup_a2a.sh --invokers --register   # peer IAM + publish agent cards
make demo        # run the golden path end to end and print the case as it unfolds
```

Two more things worth running:

```bash
.venv/bin/python -m scripts.verify_sovereignty  # prove the perimeters, incl. the 403s
.venv/bin/python -m scripts.demo_rejection      # ask a peer for too much; watch it refuse
.venv/bin/python -m scripts.eval_gemma_gate models/gemma-3-4b-it-Q4_K_M.gguf
```

All data is synthetic and generated locally from a fixed seed (`data/generator/`). No real
transaction data exists anywhere in this project.

## The perimeters are real

Each bank is a **separate GCP project** — `concordat-alpha`, `concordat-meridian`,
`concordat-union` — with its own ledger, service account, event topic and case store. The
commons project holds only neutral ground: the agent-card registry, mission control, and the
clean rooms. It holds no bank's ledger.

```
$ .venv/bin/python -m scripts.verify_sovereignty

   concordat-alpha      sa-bank-alpha@concordat-alpha  +  sa-cleanroom@concordat-hack
   concordat-meridian   sa-bank-meridian@...           +  sa-cleanroom@concordat-hack
   concordat-union      sa-bank-union@...              +  sa-cleanroom@concordat-hack
   No bank appears in another bank's project.

   sa-bank-alpha -> its own ledger    : 3,743,998 rows
   sa-bank-alpha -> meridian's ledger : refused — 403 Access Denied (concordat-meridian)
   sa-bank-alpha -> union's ledger    : refused — 403 Access Denied (concordat-union)
```

In one project you can only show that you *chose* not to grant access. Across projects, the
access does not exist to grant.

## How the privacy guarantee is enforced

Not by our code either, which is the point:

```
$ SELECT account_hash FROM bank_meridian.contribution_<digest> LIMIT 5
400 You must use SELECT WITH AGGREGATION_THRESHOLD for this query
    because a privacy policy has been set by a data owner.
```

On top of that, each bank's service account can read only its own dataset (IAM, not
convention), every outbound message passes a local redaction gate before it can cross a
boundary, and hashed account sets are withheld unless they contain at least *k* members — so a
probe can never single anyone out.

## Repository layout

```
services/bank/       one fleet, deployed three times (config, agents, policy, a2a, redaction)
services/cleanroom/  room compiler, k-thresholded contributions, dissolver
services/registry/   agent-card catalog — the fleet directory
services/ui/         mission control
data/generator/      synthetic ledgers with planted rings + BigQuery loader
infra/               idempotent setup scripts and Cloud Build pipeline
scripts/             demo drivers, evals, and verification runs
```
