#!/usr/bin/env bash
# Async backbone: per-bank Pub/Sub topics + pull subs (local dev), Firestore + publisher roles.
# Cloud Run push subscriptions are created at deploy time (infra/setup_deploy.sh).
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
PROJECT=concordat-hack

for b in alpha meridian union; do
  gcloud pubsub topics create "case-events-$b" --project="$PROJECT" 2>/dev/null || echo "topic case-events-$b exists"
  gcloud pubsub subscriptions create "case-events-$b-local" --topic="case-events-$b" \
    --ack-deadline=120 --project="$PROJECT" 2>/dev/null || echo "sub case-events-$b-local exists"
  SA="sa-bank-$b@$PROJECT.iam.gserviceaccount.com"
  gcloud pubsub topics add-iam-policy-binding "case-events-$b" \
    --member="serviceAccount:$SA" --role=roles/pubsub.publisher --project="$PROJECT" -q >/dev/null
  gcloud pubsub subscriptions add-iam-policy-binding "case-events-$b-local" \
    --member="serviceAccount:$SA" --role=roles/pubsub.subscriber --project="$PROJECT" -q >/dev/null
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$SA" --role=roles/datastore.user -q >/dev/null
  echo "async wiring done for $b"
done
