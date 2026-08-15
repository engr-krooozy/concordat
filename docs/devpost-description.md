# Concordat — Devpost submission text

Paste into the Devpost fields. Keep the claims exactly as written: every number here was
measured, and the honesty is part of the pitch.

---

## Inspiration

A fraud ring does not respect institutional boundaries, and that is precisely why it works.
The same mule network hits five banks at once. Each bank sees one fragment of the trail —
money arrives, moves twice, and leaves — and privacy law forbids them from pooling raw
customer data to see the rest. So the fragments are never assembled, and the ring keeps
operating.

The industry's answer has been to ship everyone's data to one central provider. That is the
arrangement privacy and legal teams resist hardest, and for good reason: it replaces many
small risks with one enormous one.

I wanted to know whether agents could do something better than either extreme — not share
the data, and not give up either, but **negotiate**.

## What it does

Concordat gives each bank a sovereign agent fleet that lives inside its own perimeter. When
a trace dies at an institutional boundary, the fleet does not stop. It parleys.

1. **Discovers** counterpart fleets through an A2A agent-card registry.
2. **Negotiates** the terms of a joint investigation. Gemini drafts the request; a
   deterministic policy engine on each side decides. Banks counter-offer, and the strictest
   terms win.
3. **Compiles** the signed agreement into an ephemeral BigQuery clean room where every
   contribution carries an `aggregation_threshold_policy` at the negotiated k.
4. **Acts** only inside its own walls, and only after a human approves.
5. **Dissolves** the room. Each bank revokes its own contribution; only the audit trail lives on.

Here is a real run, end to end on Cloud Run, from a single published event:

- Bank Alpha traced ₦2.4M through 30 mule accounts and stopped dead at its boundary.
- It opened negotiations at k=10, 72-hour term. **Meridian countered** (k=25, 48h). **Union
  countered** (k=15, 72h). Alpha conceded to the strictest terms; both accepted; all three
  countersigned.
- The clean room revealed what no bank could see alone: **30 mule accounts spanning all
  three institutions, ₦2,316,720 concentrated at a single cash-out cluster.**
- An analyst approved. Alpha froze 30 of **its own** accounts and filed its own report. No
  peer's customer was ever named to it.

## How I built it

**Gemini 3.5 Flash** (Vertex AI) reasons inside every agent, built on the **Google ADK**.
Fleets talk to each other over the **A2A protocol** — real agent cards at
`/.well-known/agent-card.json`, real JSON-RPC. **Cloud Run** hosts one container image
deployed three times, once per bank, each under its own service account. **Pub/Sub** drives
every state transition and **Firestore** holds case state, so any service can die mid-case
and the next event resumes it. **BigQuery** holds three isolated ledgers.

**Gemma 3 4B runs locally inside each bank's container** as a perimeter gate. This is the one
model that never calls a cloud API, deliberately: asking a hosted model "is this text safe to
send?" would require sending it first.

## Data sources

All data is synthetic and generated locally from a fixed seed — **11.2 million transactions**
across three bank ledgers, with a cross-bank mule network planted inside them, plus an
intra-bank ring as a red herring and structuring and velocity noise as background. No real
transaction data exists anywhere in this project. That is not a limitation of the demo; it is
the point of it. A system whose purpose is to avoid pooling customer data should not begin by
pooling customer data.

## Challenges I ran into

**The privacy floor hid our own finding.** At the negotiated k=25, the original 8-account
cash-out cluster was suppressed — by the very agreement the banks had signed. I widened the
ring to 30 accounts per layer, which is truer to how real mule networks operate, and the
demo's strongest line came out of the fix: a ring is revealed *only* because it is bigger
than the privacy floor the parties agreed to. Smaller groups genuinely stay hidden.

**BigQuery pushed back, and the architecture got better.** You cannot filter on a
privacy-unit column, joins between protected views must be on the privacy unit, and
`MIN`/`MAX` are banned in threshold queries. Each constraint forced a better design: peers
now probe by *counterparty*, so they can never target one of your customers.

**A shipped policy was mathematically unsatisfiable.** Meridian capped probes at 20 hashed
accounts while demanding aggregates over at least 25 — no proposal could satisfy both, and
two fleets exchanged counter-offers until they hit the round limit. Policies now fail loudly
at load time if they are incoherent, and the negotiation detects a no-progress round and
stops with a stated reason.

**Small Gemmas cannot do this job, and I nearly shipped one anyway.** On a balanced 16-case
eval, Gemma 270M scored 8/16 and Gemma 1B scored 8/16 — which looks like 50% until you see
that the first answers "LEAK" to everything and the second answers "SAFE" to everything.
Both are degenerate; the balanced set flatters them. Gemma 4B scored 16/16 with zero false
alarms. A gate that blocks legitimate traffic half the time is worse than no gate, so the
eval is in the repo and the model choice is defended by it rather than by intuition.

**Dissolution turned out to be cooperative.** The room runner got a 403 trying to delete a
bank's contribution — correctly, since it has no rights inside anyone's dataset. Now each
bank revokes its own, which is a better story than a central teardown would have been.

## Accomplishments I'm proud of

The privacy guarantee is not enforced by my code, which is the whole point:

```
SELECT account_hash FROM bank_meridian.contribution_<digest> LIMIT 5
400 You must use SELECT WITH AGGREGATION_THRESHOLD for this query
    because a privacy policy has been set by a data owner.
```

That refusal comes from BigQuery. A bug in my code cannot lift it.

## What I learned

That the interesting problem in multi-agent systems is not getting agents to cooperate — it
is getting them to cooperate **under constraints they cannot talk their way out of**. Every
temptation in this build was to let the model decide: let Gemini judge whether a request is
reasonable, whether text is safe to send, whether terms are acceptable. Every one of those
belonged in deterministic code, with the model drafting the words and the policy holding the
veto.

## What's next

Real deployment across genuinely separate organizations and GCP projects; private set
intersection in place of the per-case salt; and a negotiation protocol rich enough to bargain
over the *shape* of a computation, not only its thresholds.

## Honest novelty statement

A2A exists. BigQuery clean rooms exist. Central fraud consortia exist. What did not exist,
as far as I can find, is the layer between them: agents from different institutions
negotiating the terms of a collaboration, compiling the agreement into ephemeral
infrastructure, and dissolving it afterwards. That layer is what Concordat is.
