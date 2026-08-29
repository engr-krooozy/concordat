#!/usr/bin/env bash
# Model Armor at the perimeter — two templates per bank, inside each bank's OWN project.
#
# The templates are deliberately asymmetric, because the two directions are different jobs:
#
#   concordat-outbound  Sensitive Data Protection over text we are about to send. It runs
#                       AFTER our deterministic rules and after Gemma, so it is a third
#                       opinion on already-scrubbed text — Google's detector agreeing with
#                       ours, which is the version a counterparty's risk team can check.
#                       Basic SDP config does not fire on a person's name, which is exactly
#                       the leak our regexes cannot catch, so it points at a DLP inspect
#                       template naming the infoTypes we actually care about.
#
#   concordat-inbound   Prompt injection and jailbreak detection over free text a PEER sent
#                       us, before it reaches our agents. Rival banks are the threat model of
#                       this entire project; their prose is untrusted input. Confidence is
#                       MEDIUM_AND_ABOVE: LOW fires on ordinary negotiation language
#                       ("we request that you..."), which is a counterparty, not an attack.
#
# Templates live per project, so no bank can read or alter another's filter settings.
#
# Note the x-goog-user-project header on every REST call. Without it these APIs attribute the
# request to whatever project the caller's credentials default to — which is not the project
# named in the URL, and the call fails with a confusing SERVICE_DISABLED for a project id you
# have never seen.
set -euo pipefail
export CLOUDSDK_ACTIVE_CONFIG_NAME=concordat
REGION=us-central1
BANKS=(alpha meridian union)
TOKEN=$(gcloud auth print-access-token)

api() {  # api <method> <url> <project> [body]
  curl -s -X "$1" "$2" \
    -H "Authorization: Bearer $TOKEN" \
    -H "x-goog-user-project: $3" \
    -H "Content-Type: application/json" \
    ${4:+-d "$4"}
}

for b in "${BANKS[@]}"; do
  PROJECT="concordat-$b"
  SA="sa-bank-$b@$PROJECT.iam.gserviceaccount.com"
  echo "== $PROJECT =="

  gcloud services enable modelarmor.googleapis.com dlp.googleapis.com --project="$PROJECT" >/dev/null
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$SA" --role=roles/modelarmor.user -q >/dev/null
  echo "  modelarmor.user granted to $SA"

  # The infoTypes our deterministic rules provably cannot catch. Account ids, emails, digit
  # runs, exact amounts and precise timestamps are already handled by regex in rules.py — a
  # customer's NAME is the one that needs a detector.
  api POST "https://dlp.googleapis.com/v2/projects/$PROJECT/locations/$REGION/inspectTemplates" \
    "$PROJECT" '{
      "templateId":"concordat-pii",
      "inspectTemplate":{"displayName":"Concordat outbound PII","inspectConfig":{
        "infoTypes":[{"name":"EMAIL_ADDRESS"},{"name":"PERSON_NAME"},{"name":"PHONE_NUMBER"},
                     {"name":"CREDIT_CARD_NUMBER"},{"name":"IBAN_CODE"},{"name":"STREET_ADDRESS"}],
        "minLikelihood":"POSSIBLE","includeQuote":false}}}' >/dev/null
  echo "  dlp inspect template concordat-pii"

  INSPECT="projects/$PROJECT/locations/$REGION/inspectTemplates/concordat-pii"
  OUTBOUND="{\"filter_config\":{\"sdp_settings\":{\"advanced_config\":{\"inspect_template\":\"$INSPECT\"}}}}"
  api POST "https://modelarmor.$REGION.rep.googleapis.com/v1/projects/$PROJECT/locations/$REGION/templates?template_id=concordat-outbound" \
    "$PROJECT" "$OUTBOUND" >/dev/null
  api PATCH "https://modelarmor.$REGION.rep.googleapis.com/v1/projects/$PROJECT/locations/$REGION/templates/concordat-outbound?updateMask=filterConfig" \
    "$PROJECT" "$OUTBOUND" >/dev/null
  echo "  armor template concordat-outbound -> sdp advanced"

  INBOUND='{"filter_config":{"pi_and_jailbreak_filter_settings":{"filter_enforcement":"ENABLED","confidence_level":"MEDIUM_AND_ABOVE"},"sdp_settings":{"basic_config":{"filter_enforcement":"ENABLED"}}}}'
  api POST "https://modelarmor.$REGION.rep.googleapis.com/v1/projects/$PROJECT/locations/$REGION/templates?template_id=concordat-inbound" \
    "$PROJECT" "$INBOUND" >/dev/null
  api PATCH "https://modelarmor.$REGION.rep.googleapis.com/v1/projects/$PROJECT/locations/$REGION/templates/concordat-inbound?updateMask=filterConfig" \
    "$PROJECT" "$INBOUND" >/dev/null
  echo "  armor template concordat-inbound -> prompt injection + jailbreak"
done

echo
echo "model armor is live in all three perimeters. Verify with:"
echo "  .venv/bin/python -m scripts.test_armor"
