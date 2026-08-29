#!/usr/bin/env bash
# Register each bank's fleet in Vertex AI Agent Engine — the catalog of record.
#
# Seventh cross-boundary grant, and the reason it is safe: each bank's service account gets
# read-only Vertex AI access in the COMMONS, not in any peer. What it can read there is the
# list of registered fleets — which banks exist, which identifier scheme they speak, and the
# URL of their public agent card. That is the same information the A2A cards already publish
# to anyone holding run.invoker. No ledger, no case state, no customer.
#
# The runtime deliberately does NOT move to Agent Engine. A managed runtime in a shared
# project would put three rival banks' investigators in one blast radius, which is the exact
# arrangement this project exists to argue against. Catalog is neutral; execution is not.
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
COMMONS=concordat-hack
BANKS=(alpha meridian union)

gcloud services enable aiplatform.googleapis.com --project="$COMMONS" >/dev/null

for b in "${BANKS[@]}"; do
  SA="sa-bank-$b@concordat-$b.iam.gserviceaccount.com"
  gcloud projects add-iam-policy-binding "$COMMONS" \
    --member="serviceAccount:$SA" --role=roles/aiplatform.viewer -q >/dev/null
  echo "  $b may read the commons catalog"
done

echo "publishing catalog entries ..."
.venv/bin/python -m scripts.register_agent_engine
