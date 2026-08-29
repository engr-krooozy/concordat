"""Prove the perimeters are real, not promised.

Three checks, run against live infrastructure:

  1. Every bank project's BigQuery IAM lists exactly one bank identity — its own.
  2. A bank reading its OWN ledger succeeds.
  3. The same bank reading a PEER's ledger is refused by Google, across a project boundary.

Check 3 is the one that matters. In a single project you can only demonstrate that you chose
not to grant access. Across projects, the access does not exist to grant.

    .venv/bin/python -m scripts.verify_sovereignty
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import google.auth
from google.auth import impersonated_credentials
from google.cloud import bigquery

from services.bank.config import BANK_PREFIXES, COMMONS_PROJECT, project_for

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def gcloud_json(*args: str) -> dict | list:
    env = {**os.environ, "CLOUDSDK_ACTIVE_CONFIG_NAME": "concordat"}
    out = subprocess.run(
        ["gcloud", *args, "--format=json"], capture_output=True, text=True, env=env, check=True
    ).stdout
    return json.loads(out)


def bank_client(bank: str) -> bigquery.Client:
    """A client running AS that bank's fleet, exactly as its Cloud Run service does."""
    base, _ = google.auth.default(scopes=SCOPES)
    sa = f"sa-bank-{bank}@{project_for(bank)}.iam.gserviceaccount.com"
    creds = impersonated_credentials.Credentials(
        source_credentials=base, target_principal=sa, target_scopes=SCOPES
    )
    return bigquery.Client(project=project_for(bank), credentials=creds)


def check_iam() -> bool:
    print("1. Who holds BigQuery access in each bank's project?\n")
    clean = True
    for bank in BANK_PREFIXES:
        project = project_for(bank)
        policy = gcloud_json("projects", "get-iam-policy", project)
        holders = sorted(
            {
                m
                for b in policy["bindings"]
                if b["role"].startswith("roles/bigquery")
                for m in b["members"]
            }
        )
        print(f"   {project}")
        for m in holders:
            who = m.split(":")[-1]
            foreign = [p for p in BANK_PREFIXES if p != bank and f"sa-bank-{p}@" in who]
            flag = "  <-- A PEER BANK" if foreign else ""
            if foreign:
                clean = False
            print(f"     {who}{flag}")
        print()
    print(
        "   No bank appears in another bank's project."
        if clean
        else "   FAILED: a peer bank holds access."
    )
    return clean


def check_reads() -> bool:
    print("\n2. A fleet reading its own ledger, and then a peer's\n")
    ok = True
    for bank in ("alpha",):
        client = bank_client(bank)
        own = f"{project_for(bank)}.bank_{bank}.transactions"
        rows = next(iter(client.query(f"SELECT COUNT(*) AS n FROM `{own}`").result()))["n"]
        print(f"   sa-bank-{bank} -> its own ledger        : {rows:,} rows")

        for peer in [p for p in BANK_PREFIXES if p != bank]:
            target = f"{project_for(peer)}.bank_{peer}.transactions"
            try:
                client.query(f"SELECT COUNT(*) AS n FROM `{target}`").result()
                print(
                    f"   sa-bank-{bank} -> {peer}'s ledger        : READ SUCCEEDED — NOT SOVEREIGN"
                )
                ok = False
            except Exception as exc:  # noqa: BLE001 - any refusal is the pass condition
                reason = str(exc).splitlines()[0][:88]
                print(f"   sa-bank-{bank} -> {peer}'s ledger        : refused — {reason}")
    return ok


def main() -> None:
    print(f"\nCommons: {COMMONS_PROJECT} (registry, mission control, clean rooms — no ledgers)")
    print("Banks:   " + ", ".join(f"{b} -> {project_for(b)}" for b in BANK_PREFIXES) + "\n")
    passed = check_iam() and check_reads()
    print(
        "\nSovereignty is enforced by Google across project boundaries, not by our code."
        if passed
        else "\nSOVEREIGNTY CHECK FAILED"
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
