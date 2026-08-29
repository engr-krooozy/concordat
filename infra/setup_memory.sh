#!/usr/bin/env bash
# One Agent Engine Memory Bank per bank, inside that bank's OWN project.
#
# A shared memory would undo the work: Alpha's investigative history — which rings it chased,
# which clusters it found, how a counterparty negotiates — is exactly the kind of thing a
# rival would like to read, and putting it on neutral ground would hand it over after all the
# trouble taken to keep the ledgers apart. So each bank remembers in its own perimeter.
#
# Memory Bank embeds every fact to make it searchable, and it does that as the Reasoning
# Engine service agent rather than as the caller — so that agent, not the bank's fleet, is
# the identity that needs access to the embedding model. Missing this grant fails with a
# confusing 403 naming a Google-owned project you have never heard of.
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
BANKS=(alpha meridian union)

for b in "${BANKS[@]}"; do
  PROJECT="concordat-$b"
  NUM=$(gcloud projects describe "$PROJECT" --format="value(projectNumber)")
  echo "== $PROJECT =="
  gcloud services enable aiplatform.googleapis.com --project="$PROJECT" >/dev/null

  for AGENT in "service-$NUM@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
               "service-$NUM@gcp-sa-aiplatform.iam.gserviceaccount.com"; do
    gcloud projects add-iam-policy-binding "$PROJECT" \
      --member="serviceAccount:$AGENT" --role=roles/aiplatform.user -q >/dev/null 2>&1 || true
  done
  echo "  reasoning-engine service agents may embed"

  # The fleet writes and reads its own memories.
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:sa-bank-$b@$PROJECT.iam.gserviceaccount.com" \
    --role=roles/aiplatform.user -q >/dev/null
  echo "  sa-bank-$b may remember and recall"
done

echo
echo "creating the memory engines ..."
.venv/bin/python -m scripts.setup_memory_engines
