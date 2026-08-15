#!/usr/bin/env bash
# Wire the federation together AFTER the fleets are deployed:
#   - each bank's Pub/Sub push subscription -> its own Cloud Run service (same project)
#   - peer-to-peer invoke rights, which now cross project boundaries
#   - agent cards registered in the commons registry
#
#   bash infra/wire_federation.sh
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
COMMONS=concordat-hack
REGION=us-central1
BANKS=(alpha meridian union)

retry() {
  local n=0
  until "$@"; do
    n=$((n + 1))
    if [ "$n" -ge 6 ]; then echo "  FAILED after $n attempts: $*" >&2; return 1; fi
    sleep $((n * 4))
  done
}

url_of() { gcloud run services describe "bank-$1" --region="$REGION" \
             --project="concordat-$1" --format='value(status.url)'; }

echo "== push subscriptions (each inside its own project) =="
for b in "${BANKS[@]}"; do
  P="concordat-$b"
  PUSH_SA="sa-push-$b@$P.iam.gserviceaccount.com"
  if ! gcloud iam service-accounts describe "$PUSH_SA" --project="$P" >/dev/null 2>&1; then
    gcloud iam service-accounts create "sa-push-$b" --display-name="Pub/Sub push invoker" \
      --project="$P"
  fi
  for _ in $(seq 1 12); do
    gcloud iam service-accounts describe "$PUSH_SA" --project="$P" >/dev/null 2>&1 && break
    sleep 5
  done
  URL=$(url_of "$b")
  retry gcloud run services add-iam-policy-binding "bank-$b" --region="$REGION" \
    --member="serviceAccount:$PUSH_SA" --role=roles/run.invoker --project="$P" -q >/dev/null
  # Pub/Sub's own agent must be allowed to mint tokens as the push identity
  PN=$(gcloud projects describe "$P" --format='value(projectNumber)')
  retry gcloud projects add-iam-policy-binding "$P" \
    --member="serviceAccount:service-$PN@gcp-sa-pubsub.iam.gserviceaccount.com" \
    --role=roles/iam.serviceAccountTokenCreator -q >/dev/null
  gcloud pubsub subscriptions create "case-events-$b-push" --topic="case-events-$b" \
    --push-endpoint="$URL/pubsub" --push-auth-service-account="$PUSH_SA" \
    --ack-deadline=600 --project="$P" 2>/dev/null || echo "  push sub $b exists"
  echo "  $b -> $URL"
done

echo "== peer invoke rights (these grants cross project boundaries) =="
for target in "${BANKS[@]}"; do
  for caller in "${BANKS[@]}"; do
    [[ "$target" == "$caller" ]] && continue
    retry gcloud run services add-iam-policy-binding "bank-$target" --region="$REGION" \
      --project="concordat-$target" \
      --member="serviceAccount:sa-bank-$caller@concordat-$caller.iam.gserviceaccount.com" \
      --role=roles/run.invoker -q >/dev/null
  done
  # the observatory may call the approval endpoint, and nothing else
  retry gcloud run services add-iam-policy-binding "bank-$target" --region="$REGION" \
    --project="concordat-$target" \
    --member="serviceAccount:sa-mission-ui@$COMMONS.iam.gserviceaccount.com" \
    --role=roles/run.invoker -q >/dev/null
  # every fleet may read the commons registry
  retry gcloud run services add-iam-policy-binding registry --region="$REGION" \
    --project="$COMMONS" \
    --member="serviceAccount:sa-bank-$target@concordat-$target.iam.gserviceaccount.com" \
    --role=roles/run.invoker -q >/dev/null
  echo "  $target: peers + observatory + registry wired"
done

echo "== register agent cards =="
REG_URL=$(gcloud run services describe registry --region="$REGION" --project="$COMMONS" \
  --format='value(status.url)')
TOK=$(gcloud auth print-identity-token)
for b in "${BANKS[@]}"; do
  URL=$(url_of "$b")
  curl -sf -X POST "$REG_URL/register" -H "Authorization: Bearer $TOK" \
    -H "Content-Type: application/json" \
    -d "{\"bank\": \"$b\", \"card_url\": \"$URL/.well-known/agent-card.json\"}" >/dev/null
  echo "  registered $b -> $URL"
done
echo "federation wired"
