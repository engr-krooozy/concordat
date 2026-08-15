#!/usr/bin/env bash
# One-time data-plane setup: bank service accounts, IAM sovereignty, Firestore DB.
# Dataset READER is granted per-bank ONLY on that bank's own dataset (invariant #1).
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
PROJECT=concordat-hack

for b in alpha meridian union; do
  gcloud iam service-accounts create "sa-bank-$b" --display-name="Bank $b fleet" \
    --project="$PROJECT" 2>/dev/null || echo "sa-bank-$b exists"
done

# IAM propagation: wait until each SA is describable before binding roles
for b in alpha meridian union; do
  SA="sa-bank-$b@$PROJECT.iam.gserviceaccount.com"
  for _ in $(seq 1 12); do
    gcloud iam service-accounts describe "$SA" --project="$PROJECT" >/dev/null 2>&1 && break
    sleep 5
  done
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$SA" --role=roles/bigquery.jobUser --quiet >/dev/null
done

for ds in bank_alpha bank_meridian bank_union ground_truth; do
  bq --project_id="$PROJECT" mk --location=US -d "$ds" 2>/dev/null || echo "$ds exists"
done

python3 - <<'EOF'
import json, subprocess, os
env = {**os.environ, "CLOUDSDK_ACTIVE_CONFIG_NAME": "concordat"}
P = "concordat-hack"
for b in ("alpha", "meridian", "union"):
    ds, sa = f"{P}:bank_{b}", f"sa-bank-{b}@{P}.iam.gserviceaccount.com"
    info = json.loads(subprocess.run(["bq", "show", "--format=json", ds],
                                     capture_output=True, check=True, env=env).stdout)
    access = info["access"]
    entry = {"role": "OWNER", "userByEmail": sa}  # each bank administers its OWN perimeter only
    if entry not in access:
        access.append(entry)
        tmp = f"/tmp/access_{b}.json"
        with open(tmp, "w") as f:
            json.dump({"access": access}, f)
        subprocess.run(["bq", "update", "--source", tmp, ds], check=True, env=env)
        print(f"granted READER on bank_{b} to {sa}")
    else:
        print(f"bank_{b} ACL already set")
EOF

gcloud firestore databases create --database="(default)" --location=us-central1 \
  --project="$PROJECT" 2>/dev/null || echo "firestore db exists"
echo "data-plane setup complete"
