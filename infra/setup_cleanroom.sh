#!/usr/bin/env bash
# Room-runner identity. It deliberately gets NO dataset access anywhere: its only reach into
# bank data is the per-case contribution views each bank grants it, and those refuse raw reads.
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
PROJECT=concordat-hack

gcloud iam service-accounts create sa-cleanroom --display-name="Clean room runner" \
  --project="$PROJECT" 2>/dev/null || echo "sa-cleanroom exists"
for _ in $(seq 1 12); do
  gcloud iam service-accounts describe "sa-cleanroom@$PROJECT.iam.gserviceaccount.com" \
    --project="$PROJECT" >/dev/null 2>&1 && break
  sleep 5
done

# jobUser (run queries) + dataEditor scoped to nothing yet; room datasets are created by it
for role in roles/bigquery.jobUser roles/bigquery.user; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:sa-cleanroom@$PROJECT.iam.gserviceaccount.com" \
    --role="$role" -q >/dev/null
done

# local dev + bank fleets may act as the room runner
gcloud iam service-accounts add-iam-policy-binding \
  "sa-cleanroom@$PROJECT.iam.gserviceaccount.com" \
  --member="user:adekunlemustapha2001@gmail.com" \
  --role=roles/iam.serviceAccountTokenCreator --project="$PROJECT" -q >/dev/null
for b in alpha meridian union; do
  gcloud iam service-accounts add-iam-policy-binding \
    "sa-cleanroom@$PROJECT.iam.gserviceaccount.com" \
    --member="serviceAccount:sa-bank-$b@$PROJECT.iam.gserviceaccount.com" \
    --role=roles/iam.serviceAccountTokenCreator --project="$PROJECT" -q >/dev/null
done
echo "clean room runner ready"
