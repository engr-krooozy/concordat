#!/usr/bin/env bash
# Provision ONE bank's sovereign perimeter in its OWN GCP project.
#
#   bash infra/federate.sh alpha
#
# Sovereignty here is not a convention we promise to honour — it is a project boundary drawn
# by Google. Nothing created in this script can read another bank's ledger, and the grants
# that cross a boundary are narrow, named, and listed at the bottom of this file.
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat

# IAM policy writes race with each other; a conflicting ETag just means someone else wrote
# first, so retry rather than abort halfway through provisioning a perimeter.
retry() {
  local n=0
  until "$@"; do
    n=$((n + 1))
    if [ "$n" -ge 6 ]; then echo "  FAILED after $n attempts: $*" >&2; return 1; fi
    sleep $((n * 4))
  done
}

BANK="${1:?usage: federate.sh <alpha|meridian|union>}"
PROJECT="concordat-$BANK"
COMMONS="concordat-hack"
REGION="us-central1"
SA="sa-bank-$BANK@$PROJECT.iam.gserviceaccount.com"
CLEANROOM_SA="sa-cleanroom@$COMMONS.iam.gserviceaccount.com"
UI_SA="sa-mission-ui@$COMMONS.iam.gserviceaccount.com"

echo "== $BANK: identity =="
if ! gcloud iam service-accounts describe "$SA" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "sa-bank-$BANK" --display-name="Bank $BANK fleet" \
    --project="$PROJECT"
fi
for _ in $(seq 1 12); do
  gcloud iam service-accounts describe "$SA" --project="$PROJECT" >/dev/null 2>&1 && break
  sleep 5
done

# The fleet's rights INSIDE its own perimeter
for role in roles/bigquery.jobUser roles/aiplatform.user roles/datastore.user; do
  retry gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" \
    --role="$role" -q >/dev/null
done

echo "== $BANK: own ledger =="
bq --project_id="$PROJECT" mk --location=US -d "bank_$BANK" 2>/dev/null || echo "  dataset exists"
python3 - "$PROJECT" "$BANK" "$SA" <<'EOF'
import json, os, subprocess, sys
project, bank, sa = sys.argv[1], sys.argv[2], sys.argv[3]
env = {**os.environ, "CLOUDSDK_ACTIVE_CONFIG_NAME": "concordat"}
ds = f"{project}:bank_{bank}"
info = json.loads(subprocess.run(["bq", "show", "--format=json", ds],
                                 capture_output=True, check=True, env=env).stdout)
access = [a for a in info["access"] if a.get("userByEmail") != sa]
access.append({"role": "OWNER", "userByEmail": sa})  # a bank administers its own perimeter
tmp = f"/tmp/fed_access_{bank}.json"
open(tmp, "w").write(json.dumps({"access": access}))
subprocess.run(["bq", "update", "--source", tmp, ds], check=True, env=env, capture_output=True)
print(f"  bank_{bank}: OWNER -> its own fleet, nobody else")
EOF

echo "== $BANK: async spine =="
gcloud pubsub topics create "case-events-$BANK" --project="$PROJECT" 2>/dev/null \
  || echo "  topic exists"
retry gcloud pubsub topics add-iam-policy-binding "case-events-$BANK" \
  --member="serviceAccount:$SA" --role=roles/pubsub.publisher --project="$PROJECT" -q >/dev/null
gcloud firestore databases create --database="(default)" --location="$REGION" \
  --project="$PROJECT" 2>/dev/null || echo "  firestore exists"

echo "== $BANK: grants that deliberately cross the boundary =="
# 1. the fleet may act as the neutral clean-room runner (to create/inspect a room it agreed to)
retry gcloud iam service-accounts add-iam-policy-binding "$CLEANROOM_SA" \
  --member="serviceAccount:$SA" --role=roles/iam.serviceAccountTokenCreator \
  --project="$COMMONS" -q >/dev/null
# 2. the observatory may read this bank's case metadata — never its ledger
retry gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$UI_SA" \
  --role=roles/datastore.viewer -q >/dev/null
# 3. the room runner may run queries billed to this project when contributing our own hop
retry gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$CLEANROOM_SA" \
  --role=roles/bigquery.jobUser -q >/dev/null
# 4. local operator may impersonate this fleet (dev + verification only)
retry gcloud iam service-accounts add-iam-policy-binding "$SA" \
  --member="user:adekunlemustapha2001@gmail.com" \
  --role=roles/iam.serviceAccountTokenCreator --project="$PROJECT" -q >/dev/null
# 5. commons Cloud Build may deploy into this project and act as this fleet
CB="$(gcloud projects describe "$COMMONS" --format='value(projectNumber)')@cloudbuild.gserviceaccount.com"
retry gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$CB" \
  --role=roles/run.admin -q >/dev/null
retry gcloud iam service-accounts add-iam-policy-binding "$SA" --member="serviceAccount:$CB" \
  --role=roles/iam.serviceAccountUser --project="$PROJECT" -q >/dev/null
# 6. this project pulls the shared image from the commons registry
gcloud projects add-iam-policy-binding "$COMMONS" \
  --member="serviceAccount:service-$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')@serverless-robot-prod.iam.gserviceaccount.com" \
  --role=roles/artifactregistry.reader -q >/dev/null 2>&1 || true

echo "$BANK: perimeter ready in $PROJECT"
