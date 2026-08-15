#!/usr/bin/env bash
# One-time deploy-plane setup: Artifact Registry repo, Cloud Build perms,
# Pub/Sub push subscriptions -> Cloud Run (OIDC), per bank.
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
PROJECT=concordat-hack
REGION=us-central1
PN=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')

gcloud artifacts repositories create concordat --repository-format=docker \
  --location="$REGION" --project="$PROJECT" 2>/dev/null || echo "AR repo exists"

# Cloud Build default SA needs to deploy Cloud Run + act as the bank SAs
CB_SA="$PN@cloudbuild.gserviceaccount.com"
for role in roles/run.admin roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$CB_SA" \
    --role="$role" -q >/dev/null
done
for b in alpha meridian union; do
  gcloud iam service-accounts add-iam-policy-binding \
    "sa-bank-$b@$PROJECT.iam.gserviceaccount.com" \
    --member="serviceAccount:$CB_SA" --role=roles/iam.serviceAccountUser \
    --project="$PROJECT" -q >/dev/null
done
echo "cloud build perms done"

# Push subscriptions (created after first deploy so service URLs exist): run with --push
if [[ "${1:-}" == "--push" ]]; then
  # invoker SA for Pub/Sub push OIDC
  gcloud iam service-accounts create sa-pubsub-push --display-name="Pub/Sub push invoker" \
    --project="$PROJECT" 2>/dev/null || true
  PUSH_SA="sa-pubsub-push@$PROJECT.iam.gserviceaccount.com"
  for b in alpha meridian union; do
    URL=$(gcloud run services describe "bank-$b" --region="$REGION" --project="$PROJECT" \
      --format='value(status.url)')
    gcloud run services add-iam-policy-binding "bank-$b" --region="$REGION" \
      --member="serviceAccount:$PUSH_SA" --role=roles/run.invoker --project="$PROJECT" -q >/dev/null
    gcloud pubsub subscriptions create "case-events-$b-push" --topic="case-events-$b" \
      --push-endpoint="$URL/pubsub" \
      --push-auth-service-account="$PUSH_SA" \
      --ack-deadline=600 --project="$PROJECT" 2>/dev/null || echo "push sub $b exists"
    echo "push wiring done for $b -> $URL"
  done
fi
