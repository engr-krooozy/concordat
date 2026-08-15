# I taught rival banks' AI agents to negotiate with each other

*Building Concordat for the All Things Agentic Hackathon — and what four failures taught me
about putting models in charge of things.*

`#AllThingsAgenticHackathon`

---

A fraud ring doesn't respect institutional boundaries, and that's exactly why it works.

The same mule network hits five banks at once. Each bank sees a fragment — money arrives,
moves twice, leaves — and privacy law forbids pooling raw customer data to see the rest. So
the fragments never get assembled. The ring keeps operating, and everyone's fraud team knows
it's happening.

The industry's usual answer is to ship everyone's data to one central provider. That's the
arrangement privacy teams resist hardest, and they're right to: it swaps many small risks for
one enormous one.

I wanted to know whether agents could do something better than either extreme. Not share the
data. Not give up. **Negotiate.**

## What "negotiate" actually means here

Concordat gives each bank a sovereign agent fleet living inside its own perimeter. When a
trace dies at a boundary, the fleet doesn't stop — it opens talks with its counterparts.

Here's a real transcript from a run on Cloud Run, three deployed fleets talking over the A2A
protocol:

```
Alpha    → investigation_request   round 1  k=10  ttl=72h
Meridian ← counter_proposal        round 2  k=25  ttl=48h
Union    ← counter_proposal        round 2  k=15  ttl=72h
Alpha    → investigation_request   round 2  k=25  ttl=48h
Meridian ← policy_verdict          ACCEPT
Union    ← policy_verdict          ACCEPT
         → concordat_signed        parties=[alpha, meridian, union]
```

Alpha opened at a privacy floor of 10 accounts. Meridian — the strict one — demanded 25 and a
shorter term. Union wanted 15. Alpha conceded to the strictest terms on the table, everyone
accepted, and all three countersigned.

Then the agreement got *compiled into infrastructure*: an ephemeral BigQuery clean room where
each bank published a view carrying an `aggregation_threshold_policy` at the agreed k=25. The
joint trace revealed what no single bank could see — 30 mule accounts spanning all three
institutions, ₦2,316,720 concentrated at one cash-out cluster — and then the room dissolved.

An analyst clicked approve. Alpha froze 30 of *its own* accounts. No peer's customer was ever
named to it.

## The part I'm actually proud of

The privacy guarantee isn't enforced by my code:

```
SELECT account_hash FROM bank_meridian.contribution_a3f9 LIMIT 5

400 You must use SELECT WITH AGGREGATION_THRESHOLD for this query
    because a privacy policy has been set by a data owner.
```

That refusal comes from BigQuery itself. A bug in my code can't lift it. That's a categorically
different claim from "our service is careful with your data."

## Four times I was wrong

The interesting part of this build wasn't the happy path. It was the four times the system
told me something I didn't want to hear.

### 1. The privacy floor hid our own fraud ring

At k=25, the clean room returned nothing. The planted cash-out cluster had 8 accounts — below
the threshold the banks had just agreed to — so BigQuery suppressed it. My own demo was
censored by my own privacy guarantee.

The fix was to make the ring 30 accounts wide, which is closer to how real mule networks
operate anyway. And the failure produced the strongest line in the pitch: **a ring is
revealed only because it's bigger than the privacy floor the parties agreed to.** Small groups
genuinely stay hidden. That's not a caveat — that's the feature working.

### 2. A policy that could never be satisfied

Two fleets got stuck in a loop, exchanging counter-offers until they hit the round limit and
gave up.

Meridian's policy capped probes at 20 hashed accounts while demanding aggregates over at
least 25. No proposal could satisfy both rules. The policy was mathematically unsatisfiable
and I'd shipped it without noticing, because each rule looked reasonable alone.

Policies now fail loudly at load time if they're incoherent, and the negotiation detects a
round where nothing moved and stops with a stated reason instead of grinding. If you build
negotiating agents, assume someone will hand them impossible terms — and make impossible
*loud*, not slow.

### 3. I nearly shipped a coin flip as a safety layer

Every outbound message passes a perimeter gate: deterministic redaction rules, then a Gemma
model running locally inside the bank's own container as a second opinion. (Locally on
purpose — asking a hosted model "is this safe to send?" requires sending it first.)

I started with Gemma 3 270M. It scored 8/16 on my eval. Then 1B: also 8/16. On a balanced
set, 8/16 looks like 50% — a weak-but-working classifier.

It wasn't. The 270M model answers **LEAK to everything**. The 1B model answers **SAFE to
everything**. Both are degenerate; a balanced test set flatters them into looking mediocre
instead of broken. Gemma 3 4B scored 16/16 with zero false alarms.

A gate that blocks legitimate traffic half the time is worse than no gate. The eval lives in
the repo now, and the model choice is defended by a number rather than a vibe.

### 4. BigQuery kept saying no, and the design kept improving

You can't filter on a privacy-unit column. Joins between protected views must be on the
privacy unit. `MIN`/`MAX` are banned in threshold queries — they'd leak individual values.

Every one of those refusals forced a better design. The filtering constraint is why peers
now probe by *counterparty* rather than by account, which means a peer structurally cannot
target one of your customers even if it wanted to.

The last one was my favourite: the clean-room runner got a 403 trying to tear down a bank's
contribution. Correct — it has no rights inside anyone's dataset. So dissolution became
*cooperative*: the runner drops the room, and each bank revokes its own view. A better story
than a central teardown, discovered by being told no.

## The lesson I'll keep

The hard problem in multi-agent systems isn't getting agents to cooperate. It's getting them
to cooperate **under constraints they can't talk their way out of.**

Every temptation in this build was to let the model decide. Let Gemini judge whether a request
is reasonable. Let it decide whether text is safe to send. Let it weigh whether terms are
acceptable.

Every one of those belonged in deterministic code. The model drafts the words; the policy
engine holds the veto; the database enforces the floor. Gemini is genuinely good at the
judgement calls I left it — which transaction in a haystack matches a customer's story, how to
phrase a request to a rival institution, how to write a regulator-facing report. It just
shouldn't be the thing standing between a customer's data and the outside world.

## Honest novelty

A2A exists. BigQuery clean rooms exist. Central fraud consortia exist. What I couldn't find
anywhere was the layer between them: agents from different institutions negotiating the terms
of a collaboration, compiling that agreement into ephemeral infrastructure, and dissolving it
afterwards.

Call it data diplomacy. It seems like a reasonable new job for an agent fleet.

---

*Built with Google ADK, the A2A protocol, Gemini 3.5 Flash on Vertex AI, Gemma 3 4B running
locally, Cloud Run, Pub/Sub, Firestore, and BigQuery. All data is synthetic — 11.2 million
generated transactions across three ledgers. A system built to avoid pooling customer data
shouldn't start by pooling customer data.*
