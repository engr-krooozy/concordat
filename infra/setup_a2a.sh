#!/usr/bin/env bash
# A2A plane: registry SA, cross-bank invoker grants (banks may call each other's A2A
# endpoints + the registry), and card registration.
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
PROJECT=concordat-hack
REGION=us-central1

gcloud iam service-accounts create sa-registry --display-name="Agent-card registry" \
  --project="$PROJECT" 2>/dev/null || echo "sa-registry exists"
sleep 5
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:sa-registry@$PROJECT.iam.gserviceaccount.com" \
  --role=roles/datastore.user -q >/dev/null

# Cloud Build deploys the registry too
PN=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding \
  "sa-registry@$PROJECT.iam.gserviceaccount.com" \
  --member="serviceAccount:$PN@cloudbuild.gserviceaccount.com" \
  --role=roles/iam.serviceAccountUser --project="$PROJECT" -q >/dev/null

# Peer-to-peer: every bank may invoke every other bank + the registry
if [[ "${1:-}" == "--invokers" ]]; then
  for target in alpha meridian union; do
    for caller in alpha meridian union; do
      [[ "$target" == "$caller" ]] && continue
      gcloud run services add-iam-policy-binding "bank-$target" --region="$REGION" \
        --member="serviceAccount:sa-bank-$caller@$PROJECT.iam.gserviceaccount.com" \
        --role=roles/run.invoker --project="$PROJECT" -q >/dev/null
    done
    gcloud run services add-iam-policy-binding registry --region="$REGION" \
      --member="serviceAccount:sa-bank-$target@$PROJECT.iam.gserviceaccount.com" \
      --role=roles/run.invoker --project="$PROJECT" -q >/dev/null
    echo "invoker grants done for $target"
  done
fi

# Register each bank's card with the registry (run after deploy)
if [[ "${1:-}" == "--register" ]]; then
  REG_URL=$(gcloud run services describe registry --region="$REGION" --project="$PROJECT" \
    --format='value(status.url)')
  TOK=$(gcloud auth print-identity-token)
  for b in alpha meridian union; do
    URL=$(gcloud run services describe "bank-$b" --region="$REGION" --project="$PROJECT" \
      --format='value(status.url)')
    curl -sf -X POST "$REG_URL/register" -H "Authorization: Bearer $TOK" \
      -H "Content-Type: application/json" \
      -d "{\"bank\": \"$b\", \"card_url\": \"$URL/.well-known/agent-card.json\"}" >/dev/null
    echo "registered $b -> $URL"
  done
  curl -s "$REG_URL/cards" -H "Authorization: Bearer $TOK" | python3 -m json.tool
fi
