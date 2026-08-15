#!/usr/bin/env bash
# Mission-control identity. It reads case state and may call the approval endpoint, and
# nothing else: no BigQuery, no bank dataset, no ability to act inside a perimeter.
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
PROJECT=concordat-hack
REGION=us-central1

# create only if missing, and let real errors surface — "|| echo exists" once hid an
# invalid-name failure and produced a confusing cascade of NOT_FOUND downstream
if ! gcloud iam service-accounts describe "sa-mission-ui@$PROJECT.iam.gserviceaccount.com" \
     --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create sa-mission-ui --display-name="Mission control" \
    --project="$PROJECT"
fi
for _ in $(seq 1 12); do
  gcloud iam service-accounts describe "sa-mission-ui@$PROJECT.iam.gserviceaccount.com" \
    --project="$PROJECT" >/dev/null 2>&1 && break
  sleep 5
done

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:sa-mission-ui@$PROJECT.iam.gserviceaccount.com" \
  --role=roles/datastore.viewer -q >/dev/null

PN=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding "sa-mission-ui@$PROJECT.iam.gserviceaccount.com" \
  --member="serviceAccount:$PN@cloudbuild.gserviceaccount.com" \
  --role=roles/iam.serviceAccountUser --project="$PROJECT" -q >/dev/null

if [[ "${1:-}" == "--invokers" ]]; then
  for b in alpha meridian union; do
    gcloud run services add-iam-policy-binding "bank-$b" --region="$REGION" \
      --member="serviceAccount:sa-mission-ui@$PROJECT.iam.gserviceaccount.com" \
      --role=roles/run.invoker --project="$PROJECT" -q >/dev/null
  done
  echo "mission control may invoke the fleets"
fi
echo "ui identity ready"
