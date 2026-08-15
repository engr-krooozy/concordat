"""The golden path, end to end, against the deployed fleets.

    make demo                 # full run, auto-approves at the gate
    make demo -- --no-approve # stop at the approval gate (for the video's manual click)

Publishes one kickoff event and follows the case: solo trace -> dead end -> discovery ->
negotiation with a counter-round -> clean room -> joint finding -> approval -> enforcement.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid

import httpx

PROJECT = "concordat-hack"
BANK_URL = "https://bank-alpha-fa7ntw3nkq-uc.a.run.app"
REPORT = (
    "Customer fraud report: account holder of ALP-9000001 reports approximately 2.4 million "
    "naira stolen via a web transfer they did not authorize on 2026-08-12 (afternoon, WAT). "
    "Investigate and trace where the funds went."
)
TERMINAL = {"closed", "rejected"}


def gcloud(*args: str) -> str:
    import os

    env = {**os.environ, "CLOUDSDK_ACTIVE_CONFIG_NAME": "concordat"}
    return subprocess.run(
        ["gcloud", *args], capture_output=True, text=True, env=env, check=True
    ).stdout.strip()


def call(path: str, method: str = "GET") -> dict:
    token = gcloud("auth", "print-identity-token")
    resp = httpx.request(
        method, f"{BANK_URL}{path}", timeout=90, headers={"Authorization": f"Bearer {token}"}
    )
    resp.raise_for_status()
    return resp.json()


def publish(case_id: str) -> None:
    payload = json.dumps(
        {"type": "case.kickoff", "bank": "alpha", "case_id": case_id, "report": REPORT}
    )
    gcloud(
        "pubsub",
        "topics",
        "publish",
        "case-events-alpha",
        f"--project={PROJECT}",
        f"--message={payload}",
    )


def show(case: dict, seen: set[str]) -> None:
    for entry in case.get("audit", []):
        key = f"{entry['ts']}{entry['action']}"
        if key in seen:
            continue
        seen.add(key)
        detail = entry["detail"][:90].replace("\n", " ")
        print(f"  {entry['actor']:<20} {entry['action']:<30} {detail}")


def wait_for(case_id: str, statuses: set[str], seen: set[str], timeout: int = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            case = call(f"/cases/{case_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            time.sleep(5)  # case doc not written yet
            continue
        show(case, seen)
        if case["status"] in statuses:
            return case
        time.sleep(5)
    raise TimeoutError(f"case {case_id} never reached {statuses}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-approve", action="store_true", help="stop at the approval gate")
    args = ap.parse_args()

    case_id = f"case-{uuid.uuid4().hex[:8]}"
    print(f"=== Concordat demo: {case_id} ===\n[1] analyst files the fraud report")
    publish(case_id)

    seen: set[str] = set()
    case = wait_for(case_id, {"awaiting_approval", "rejected", "closed"}, seen)

    if case.get("concordat"):
        c = case["concordat"]
        print(
            f"\n[2] concordat signed: parties={c['parties']} k={c['k_threshold']} "
            f"ttl={c['ttl_hours']}h"
        )
    if case.get("finding"):
        f = case["finding"]
        chain = " -> ".join(h["bank"] for h in f["hops"])
        print(
            f"[3] JOINT FINDING: {f['mule_accounts']} mule accounts across {chain}; "
            f"{f['total_ngn']:,.0f} NGN at {f['cashout_cluster']}"
        )

    if case["status"] != "awaiting_approval":
        print(f"\ncase ended as {case['status']}")
        return
    if args.no_approve:
        print("\n[4] awaiting analyst approval (run with approval to continue)")
        return

    print("\n[4] analyst approves enforcement")
    call(f"/cases/{case_id}/approve?approver=analyst@alpha", method="POST")
    case = wait_for(case_id, TERMINAL, seen)
    print(f"\n[5] {case['status']}: {len(case.get('enforcement', []))} actions inside alpha")
    for action in case.get("enforcement", [])[:5]:
        print(f"      {action}")
    if case["status"] != "closed":
        sys.exit(1)


if __name__ == "__main__":
    main()
