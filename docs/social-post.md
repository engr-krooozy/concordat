# Social post (Devpost bonus, up to 0.6 pts)

Post publicly, attach `docs/gallery/01-cover.png`, then paste the post URL into Devpost.
The profile must be public or a judge opening the link sees nothing.

Hashtag: **#AllThingsAgenticHackathon**

---

## LinkedIn (primary)

A woman loses ₦2.4M to a transfer she never made. Her bank can follow that money for about
thirty seconds. Then every trail walks out of the building into two other banks, who each hold
a piece of the same ring and are forbidden by privacy law from comparing notes.

So nobody assembles the picture, and the ring keeps working.

I spent two weeks building Concordat to test whether agents could do a third thing. Not pool
everyone's data into one central provider, which is the arrangement privacy teams resist
hardest. Not give up either. Negotiate.

Three rival banks each run their own fleet of agents, inside their own walls. When a trace dies
at the boundary, the fleet opens talks over Google's A2A protocol:

Alpha opened by asking for a privacy floor of 10 accounts.
Meridian, the strict one, countered with 25.
Union wanted 15.
Alpha conceded to the strictest terms on the table, and all three countersigned.

That agreement then compiled itself into a temporary BigQuery clean room. The joint query found
what none of them could see alone: 30 mule accounts spanning all three institutions, with
₦2,316,720 converging on a single cash-out point in Lagos.

An analyst clicked approve. Alpha froze 30 of its own accounts, opened a reimbursement claim for
the victim, and filed with the regulator. It never learned the name of a single Meridian
customer.

Two claims here you do not have to take my word for, because Google answers both and my code
does not come into it:

Sovereignty is a 403. Each bank runs in its own Google Cloud project, under its own service
account. Bank Alpha querying a peer's ledger gets Access Denied. I built this in a single
project first and it worked fine, but inside one project all you can ever show is that you chose
not to grant access. Across projects, the access does not exist to grant.

The privacy floor is not mine to lift. Ask the clean room for one row and BigQuery refuses,
because a data owner set a policy on it. A bug in my code cannot override that. Set it next to
"our service is careful with your data" and you can see why I kept chasing it.

Built with Gemini 3.5 Flash, the Google ADK, A2A, Vertex AI Agent Engine, Model Armor and Cloud
Run. Every transaction is synthetic, because a system built to avoid pooling customer data
should not begin by pooling customer data.

Live dashboard, no login needed:
https://mission-control-fa7ntw3nkq-uc.a.run.app

#AllThingsAgenticHackathon

---

## X / Twitter (fits 280)

Rival banks' AI agents, negotiating the terms of a joint fraud investigation.

3 banks. 0 records shared. 30 mule accounts found that none of them could see alone.

Sovereignty here isn't a promise, it's a 403 from Google.

#AllThingsAgenticHackathon
https://mission-control-fa7ntw3nkq-uc.a.run.app

---

## X thread continuation (optional)

2/ Alpha asked for a privacy floor of 10 accounts. Meridian countered 25. Union wanted 15.
Alpha conceded to the strictest terms on the table and all three signed. The verdicts come from
deterministic policy code, never from a model. No phrasing talks a policy round.

3/ The signed agreement compiles itself into a temporary BigQuery clean room. Every contribution
carries an aggregation threshold at the agreed k. Ask it for a single row and BigQuery refuses.
Not my code refusing. The database.

4/ Then it dissolves. Each bank revokes its own contribution, and the only thing that leaves is
an aggregate nobody could have computed alone.
