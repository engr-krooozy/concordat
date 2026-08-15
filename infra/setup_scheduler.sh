#!/usr/bin/env bash
# Keeps the dashboard alive during judging: one fresh investigation a day, left parked at the
# approval gate so whoever opens the URL finds a live case with a decision waiting for them.
#
# The message carries no case_id on purpose — the fleet mints one per run, so successive days
# accumulate as separate cases instead of overwriting one another.
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
PROJECT=concordat-hack
REGION=us-central1
SA="sa-scheduler-cc@$PROJECT.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$SA" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create sa-scheduler-cc --display-name="Daily demo seeder" \
    --project="$PROJECT"
fi
for _ in $(seq 1 12); do
  gcloud iam service-accounts describe "$SA" --project="$PROJECT" >/dev/null 2>&1 && break
  sleep 5
done

gcloud pubsub topics add-iam-policy-binding case-events-alpha \
  --member="serviceAccount:$SA" --role=roles/pubsub.publisher --project="$PROJECT" -q >/dev/null

BODY_FILE=$(mktemp)
cat >"$BODY_FILE" <<'JSON'
{"type": "case.kickoff", "bank": "alpha", "report": "Customer fraud report: account holder of ALP-9000001 reports approximately 2.4 million naira stolen via a web transfer they did not authorize on 2026-08-12 (afternoon, WAT). Investigate and trace where the funds went."}
JSON

gcloud scheduler jobs delete concordat-daily-demo --location="$REGION" --project="$PROJECT" -q \
  2>/dev/null || true
gcloud scheduler jobs create pubsub concordat-daily-demo \
  --location="$REGION" --project="$PROJECT" \
  --schedule="0 6 * * *" --time-zone="UTC" \
  --topic="projects/$PROJECT/topics/case-events-alpha" \
  --message-body-from-file="$BODY_FILE" \
  --description="Seeds one investigation a day so the judging dashboard is never empty"
rm -f "$BODY_FILE"

echo "daily seeder scheduled for 06:00 UTC"
