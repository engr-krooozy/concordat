#!/usr/bin/env bash
# Judge mode: replay a real investigation against the live deployment, with no GCP account,
# no credentials, no clone-and-install. Everything below is a plain HTTPS request to the
# public mission-control API.
#
#   bash scripts/judge_replay.sh            # walk the newest completed case
#   bash scripts/judge_replay.sh <case-id>  # walk a specific one
#   APPROVE=1 bash scripts/judge_replay.sh  # also exercise the human approval gate
#
# Requires curl and python3. Nothing else.
set -euo pipefail
UI="${UI:-https://mission-control-fa7ntw3nkq-uc.a.run.app}"
CASE="${1:-}"

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }

if [ -z "$CASE" ]; then
  CASE=$(curl -sf "$UI/api/cases" | python3 -c "
import json,sys
cases = json.load(sys.stdin)
done = [c for c in cases if c['status'] in ('awaiting_approval','closed')]
print((done or cases)[0]['case_id'])")
fi

say "Concordat — case $CASE"
echo "  live at $UI"

curl -sf "$UI/api/cases/$CASE" > /tmp/concordat-case.json

say "1. Alpha investigates alone, and fails"
python3 - <<'PY'
import json
case = json.load(open("/tmp/concordat-case.json"))
for entry in case["audit"]:
    if entry["action"] in ("query:large_outflows", "hop", "hop_empty") or "dead_end" in entry["action"]:
        print(f"   {entry['actor']:20s} {entry['action']:22s} {entry['detail'][:60]}")
PY

say "2. It opens a negotiation, and the peers push back"
python3 - <<'PY'
import json
case = json.load(open("/tmp/concordat-case.json"))
for turn in case.get("negotiation_transcript", []):
    msg = turn.get("message", {})
    kind = msg.get("kind", "")
    if kind not in ("investigation_request", "counter_proposal", "policy_verdict", "concordat_signed"):
        continue
    arrow = "->" if turn.get("direction") == "sent" else "<-"
    detail = ""
    if "k_threshold" in msg:
        detail = f"k={msg['k_threshold']} ttl={msg.get('ttl_hours','?')}h"
    if msg.get("verdict"):
        detail = msg["verdict"].upper() + (f" {msg.get('violated_rules')}" if msg.get("violated_rules") else "")
    if msg.get("note"):
        detail += f"  {msg['note'][:70]}"
    print(f"   {arrow} {turn.get('peer',''):10s} {kind:22s} {detail}")
PY

say "3. Nobody could see this alone"
python3 - <<'PY'
import json
case = json.load(open("/tmp/concordat-case.json"))
finding = case.get("finding")
if not finding:
    print("   (this case has no joint finding yet)")
else:
    chain = " -> ".join(h["bank"] for h in finding["hops"])
    print(f"   {finding['mule_accounts']} mule accounts across {chain}")
    print(f"   {finding['total_ngn']:,.0f} NGN concentrated at {finding['cashout_cluster']}")
    for hop in finding["hops"]:
        print(f"     {hop['bank']:10s} {hop['accounts']:3d} accounts  {hop['total_ngn']:>14,.0f} NGN")
    agreement = case.get("concordat") or {}
    print(f"   computed under: k={agreement.get('k_threshold')} "
          f"ttl={agreement.get('ttl_hours')}h parties={agreement.get('parties')}")
PY

say "4. Every payload that crossed a perimeter was gated"
python3 - <<'PY'
import json
case = json.load(open("/tmp/concordat-case.json"))
gates = [e for e in case["audit"] if e["action"] == "perimeter_gate"]
for entry in gates[:4]:
    print(f"   {entry['detail'][:96]}")
print(f"   ... {len(gates)} outbound payloads screened in this case")
PY

STATUS=$(python3 -c "import json;print(json.load(open('/tmp/concordat-case.json'))['status'])")
say "5. A human decides — status is now: $STATUS"
if [ "${APPROVE:-0}" = "1" ] && [ "$STATUS" = "awaiting_approval" ]; then
  echo "   approving as judge@devpost ..."
  curl -sf -X POST "$UI/api/cases/$CASE/approve?approver=judge@devpost" | python3 -m json.tool
  echo "   watch it close at $UI"
else
  python3 - <<'PY'
import json
case = json.load(open("/tmp/concordat-case.json"))
actions = case.get("enforcement", [])
if actions:
    print(f"   {len(actions)} actions, all inside alpha's own perimeter:")
    for a in actions[:3]:
        print(f"     {a}")
    print(f"     ... and {actions[-2]}, {actions[-1]}")
else:
    print("   nothing enforced yet — re-run with APPROVE=1 to exercise the gate yourself")
PY
fi

say "The perimeters, if you want to check them yourself"
cat <<'TXT'
   bq ls --project_id=concordat-hack            # the commons holds no bank's ledger
   gcloud run services list --project=concordat-hack   # and runs no bank's code
   Each fleet lives in concordat-alpha | -meridian | -union, under its own identity.
TXT
