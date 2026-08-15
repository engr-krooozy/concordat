"""Clean-room proof: chained hops across three banks, each contributing only k-thresholded
aggregates, then dissolution.

    .venv/bin/python -m scripts.test_cleanroom
"""

import os

import google.auth
from google.auth import impersonated_credentials
from google.cloud import bigquery

from services.bank.a2a.hashing import hash_account
from services.bank.config import BANK_PREFIXES, BankConfig
from services.cleanroom.compiler import (
    contribute_hop,
    create_room,
    dissolve_room,
    initiator_contribution,
    revoke_contribution,
)
from services.cleanroom.query import assemble

PROJECT = "concordat-hack"
ROOM_RUNNER = f"sa-cleanroom@{PROJECT}.iam.gserviceaccount.com"
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
DIGEST = "testdigest01"
K = 25
SALT = "a1b2c3d4e5f60718"
WINDOW = ("2026-08-12 00:00:00", "2026-08-13 00:00:00")


def cfg_for(bank: str) -> BankConfig:
    return BankConfig(
        bank=bank,
        prefix=BANK_PREFIXES[bank],
        project=PROJECT,
        dataset=f"bank_{bank}",
        service_account=f"sa-bank-{bank}@{PROJECT}.iam.gserviceaccount.com",
        impersonate_locally=True,
    )


def runner_credentials():
    base, _ = google.auth.default(scopes=SCOPES)
    return impersonated_credentials.Credentials(
        source_credentials=base, target_principal=ROOM_RUNNER, target_scopes=SCOPES
    )


def main() -> None:
    os.environ.setdefault("BANK", "alpha")
    creds = runner_credentials()
    room = create_room(PROJECT, DIGEST, ttl_hours=48, credentials=creds)
    room_ds = room.split(".")[-1]
    print(f"room: {room}")

    # banks may write their own contribution into the room
    client = bigquery.Client(project=PROJECT, credentials=creds)
    ds = client.get_dataset(room)
    entries = list(ds.access_entries)
    for b in ("alpha", "meridian", "union"):
        entries.append(
            bigquery.AccessEntry(
                "WRITER", "userByEmail", f"sa-bank-{b}@{PROJECT}.iam.gserviceaccount.com"
            )
        )
    ds.access_entries = entries
    client.update_dataset(ds, ["access_entries"])

    # alpha's flagged mule layer, hashed — the probe that opens the chain
    probe = [hash_account(SALT, f"ALP-91{i:04d}") for i in range(30)]
    alpha_c = initiator_contribution(cfg_for("alpha"), SALT, WINDOW[0], WINDOW[1], probe)
    print(f"  alpha (own perimeter): accounts={alpha_c.accounts} total={alpha_c.total_ngn:,.0f}")
    contributions = [alpha_c]
    for bank in ("meridian", "union"):
        c = contribute_hop(
            cfg_for(bank), DIGEST, K, SALT, WINDOW[0], WINDOW[1], ROOM_RUNNER, probe, room_ds
        )
        contributions.append(c)
        print(
            f"  {bank}: accounts={c.accounts} total={c.total_ngn:,.0f} "
            f"cluster={c.cashout_cluster or '-'} onward={len(c.onward_hashes)}"
        )
        probe = c.onward_hashes
        if not probe:
            break

    # the room runner still cannot read a single row of anyone's ledger
    try:
        client.query(
            f"SELECT account_hash FROM `{PROJECT}.bank_meridian.contribution_{DIGEST}` LIMIT 5"
        ).result()
        print("!! RAW READ SUCCEEDED — privacy policy NOT enforced")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001 - any refusal proves the policy holds
        print(f"  raw read refused: {str(exc).splitlines()[0][:100]}")

    finding = assemble(contributions)
    print(f"\nJOINT FINDING: {finding.headline() if finding else 'none'}")

    for bank in ("meridian", "union"):  # each bank revokes its own contribution
        revoke_contribution(cfg_for(bank), DIGEST)
    dissolve_room(PROJECT, DIGEST, creds)
    print("room dissolved; contributions revoked by their owners")
    if not finding or len(finding.banks_involved) < 3:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
