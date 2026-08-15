"""Compile a signed concordat into an ephemeral BigQuery clean room, and dissolve it.

Enforcement is BigQuery's own: each bank's contribution is a view carrying an
`aggregation_threshold_policy` at the negotiated k, created BY that bank's service account
inside that bank's dataset. Raw `SELECT` against such a view is refused by BigQuery itself
(not by our code), so no party — including the room runner — can read rows. Only
`SELECT WITH AGGREGATION_THRESHOLD` aggregates are possible, and groups below k vanish.

The room dataset holds no data of its own: it exists to scope the joint query and to carry
a TTL, and it is dropped on dissolution.
"""

from __future__ import annotations

import logging
import re

from google.cloud import bigquery
from pydantic import BaseModel

from services.bank.auth import bank_credentials
from services.bank.config import BankConfig

log = logging.getLogger("concordat.cleanroom")


def contribution_view_id(cfg: BankConfig, terms_digest: str) -> str:
    return f"{cfg.project}.{cfg.dataset}.contribution_{terms_digest}"


class Contribution(BaseModel):
    """What one bank puts into the room for one hop of the trace."""

    bank: str
    view_id: str
    aggregate_table: str
    accounts: int  # distinct mule accounts this bank saw (>= k, or the row vanished)
    total_ngn: float
    onward_hashes: list[str]  # hashed counterparties for the next bank to probe
    cashout_cluster: str = ""
    onward_bank: str = ""  # where this hop sent the money — tells the fleet who to ask next


def publish_contribution(
    cfg: BankConfig,
    terms_digest: str,
    k_threshold: int,
    case_salt: str,
    window_start: str,
    window_end: str,
    room_runner: str,
) -> str:
    """Create THIS bank's contribution view (own dataset, own SA, k-policy) and grant the
    room runner read access to the view only. Returns the view id.

    Identifiers are salted-hashed with the case salt so they join inside the room while
    remaining meaningless outside it.
    """
    # BigQuery forbids query parameters in view bodies, so these are inlined — validate
    # strictly first. All three are machine-generated (hex salt, ISO timestamps); anything
    # else is a bug or an injection attempt and must not reach SQL.
    if not re.fullmatch(r"[0-9a-f]{16,64}", case_salt):
        raise ValueError("case_salt must be lowercase hex (16-64 chars)")
    for ts in (window_start, window_end):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", ts):
            raise ValueError(f"window bound not an ISO timestamp: {ts!r}")
    if not isinstance(k_threshold, int) or not 1 <= k_threshold <= 10000:
        raise ValueError("k_threshold out of range")

    client = bigquery.Client(project=cfg.project, credentials=bank_credentials(cfg))
    view_id = contribution_view_id(cfg, terms_digest)
    policy = (
        '{"aggregation_threshold_policy": '
        f'{{"threshold": {k_threshold}, "privacy_unit_column": "account_hash"}}}}'
    )
    # Account-centric: one row per (our account, counterparty, direction). `account_hash` is
    # always OUR customer and is the privacy unit — BigQuery forbids filtering on it, so peers
    # probe us by `counterparty_hash` instead and can never target one of our customers.
    src_h = f"TO_HEX(SHA256(CONCAT('{case_salt}', ':', src_account)))"
    dst_h = f"TO_HEX(SHA256(CONCAT('{case_salt}', ':', dst_account)))"
    window = f"ts BETWEEN TIMESTAMP('{window_start}') AND TIMESTAMP('{window_end}')"
    table = f"`{cfg.project}.{cfg.dataset}.transactions`"
    sql = f"""
    CREATE OR REPLACE VIEW `{view_id}`
    OPTIONS(privacy_policy = \"\"\"{policy}\"\"\")
    AS
    SELECT {src_h} AS account_hash, {dst_h} AS counterparty_hash, 'out' AS direction,
           dst_bank AS other_bank, amount,
           IF(channel = 'atm', narration, NULL) AS cashout_cluster
    FROM {table} WHERE src_bank = '{cfg.bank}' AND {window}
    UNION ALL
    SELECT {dst_h} AS account_hash, {src_h} AS counterparty_hash, 'in' AS direction,
           src_bank AS other_bank, amount, NULL AS cashout_cluster
    FROM {table} WHERE dst_bank = '{cfg.bank}' AND {window}
    """
    client.query(sql).result()

    # authorize the view over its own dataset, then grant the room runner access to the
    # VIEW ONLY — never to the underlying table
    dataset = client.get_dataset(f"{cfg.project}.{cfg.dataset}")
    entries = list(dataset.access_entries)
    ref = bigquery.TableReference.from_string(view_id)
    view_entry = bigquery.AccessEntry(None, "view", ref.to_api_repr())
    if view_entry not in entries:
        entries.append(view_entry)
        dataset.access_entries = entries
        client.update_dataset(dataset, ["access_entries"])

    view_table = client.get_table(view_id)
    policy_obj = client.get_iam_policy(view_table)
    binding = {"role": "roles/bigquery.dataViewer", "members": {f"serviceAccount:{room_runner}"}}
    if binding not in policy_obj.bindings:
        policy_obj.bindings.append(binding)
        client.set_iam_policy(view_table, policy_obj)

    log.info("%s published contribution %s (k=%d)", cfg.bank, view_id, k_threshold)
    return view_id


def initiator_contribution(
    cfg: BankConfig,
    case_salt: str,
    window_start: str,
    window_end: str,
    own_account_hashes: list[str],
) -> Contribution:
    """The initiator's own hop. No aggregation threshold applies: these are its own
    customers in its own ledger, and a bank needs no privacy protection against itself.
    What leaves the perimeter is only the hashed account set handed to the next bank.
    """
    client = bigquery.Client(project=cfg.project, credentials=bank_credentials(cfg))
    sql = f"""
    SELECT COUNT(DISTINCT src_account) AS accounts, ROUND(SUM(amount)) AS total_ngn,
           ANY_VALUE(dst_bank) AS dst_bank
    FROM `{cfg.project}.{cfg.dataset}.transactions`
    WHERE TO_HEX(SHA256(CONCAT('{case_salt}', ':', src_account))) IN UNNEST(@probe)
      AND src_bank = '{cfg.bank}' AND dst_bank != src_bank
      AND ts BETWEEN TIMESTAMP('{window_start}') AND TIMESTAMP('{window_end}')
    """
    row = next(
        iter(
            client.query(
                sql,
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ArrayQueryParameter("probe", "STRING", own_account_hashes)
                    ]
                ),
            ).result()
        )
    )
    log.info(
        "%s (initiator): %s accounts, %.0f NGN -> %s",
        cfg.bank,
        row["accounts"],
        row["total_ngn"] or 0,
        row["dst_bank"],
    )
    return Contribution(
        bank=cfg.bank,
        view_id="",
        aggregate_table="",
        accounts=row["accounts"] or 0,
        total_ngn=float(row["total_ngn"] or 0),
        onward_hashes=own_account_hashes,
        onward_bank=row["dst_bank"] or "",
    )


def contribute_hop(
    cfg: BankConfig,
    terms_digest: str,
    k_threshold: int,
    case_salt: str,
    window_start: str,
    window_end: str,
    room_runner: str,
    probe_hashes: list[str],
    room_dataset: str,
) -> Contribution:
    """Run this bank's hop of the joint trace, entirely inside its own perimeter.

    Two outputs, with different privacy characters:
      * the aggregate written into the room comes from a `SELECT WITH AGGREGATION_THRESHOLD`
        over our k-policy view — BigQuery itself guarantees it describes >= k accounts;
      * the onward hashes handed to the next bank are read from our own ledger (our data,
        our right) but are refused unless the set itself is >= k, so no individual is ever
        singled out by a probe.
    """
    view_id = publish_contribution(
        cfg, terms_digest, k_threshold, case_salt, window_start, window_end, room_runner
    )
    client = bigquery.Client(project=cfg.project, credentials=bank_credentials(cfg))
    params = [bigquery.ArrayQueryParameter("probe", "STRING", probe_hashes)]

    # Probe on counterparty_hash (never the privacy unit); join on account_hash (the only
    # join BigQuery permits between privacy-protected rows). Any group under k disappears.
    agg_sql = f"""
    SELECT WITH AGGREGATION_THRESHOLD
      IFNULL(o.other_bank, '') AS dst_bank,
      IFNULL(o.cashout_cluster, '') AS cashout_cluster,
      COUNT(DISTINCT i.account_hash) AS accounts,
      ROUND(SUM(o.amount)) AS total_ngn
    FROM `{view_id}` i
    JOIN `{view_id}` o ON o.account_hash = i.account_hash
    WHERE i.direction = 'in' AND i.counterparty_hash IN UNNEST(@probe)
      AND o.direction = 'out'
    GROUP BY dst_bank, cashout_cluster
    ORDER BY total_ngn DESC
    """
    # the aggregate lands in the commons room; the view it came from never leaves us
    agg_table = f"{cfg.commons}.{room_dataset.split('.')[-1]}.contribution_{cfg.bank}"
    rows = list(
        client.query(
            agg_sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=params,
                destination=agg_table,
                write_disposition="WRITE_TRUNCATE",
            ),
        ).result()
    )
    if not rows:
        log.warning("%s: hop suppressed by its own k=%d floor", cfg.bank, k_threshold)
        return Contribution(
            bank=cfg.bank,
            view_id=view_id,
            aggregate_table=agg_table,
            accounts=0,
            total_ngn=0.0,
            onward_hashes=[],
        )
    top = rows[0]

    onward_sql = f"""
    SELECT DISTINCT TO_HEX(SHA256(CONCAT('{case_salt}', ':', dst_account))) AS h
    FROM `{cfg.project}.{cfg.dataset}.transactions`
    WHERE TO_HEX(SHA256(CONCAT('{case_salt}', ':', src_account))) IN UNNEST(@probe)
      AND ts BETWEEN TIMESTAMP('{window_start}') AND TIMESTAMP('{window_end}')
      AND dst_bank != src_bank
    """
    onward = [
        r["h"]
        for r in client.query(
            onward_sql, job_config=bigquery.QueryJobConfig(query_parameters=params)
        ).result()
    ]
    if 0 < len(onward) < k_threshold:
        log.warning(
            "%s: onward set of %d < k=%d — withholding (would single out accounts)",
            cfg.bank,
            len(onward),
            k_threshold,
        )
        onward = []

    log.info(
        "%s hop: %d accounts, %.0f NGN -> %s (%d onward hashes)",
        cfg.bank,
        top["accounts"],
        top["total_ngn"],
        top["dst_bank"],
        len(onward),
    )
    return Contribution(
        bank=cfg.bank,
        view_id=view_id,
        aggregate_table=agg_table,
        accounts=top["accounts"],
        total_ngn=float(top["total_ngn"]),
        onward_hashes=onward,
        cashout_cluster=top["cashout_cluster"],
        onward_bank=top["dst_bank"],
    )


def create_room(project: str, terms_digest: str, ttl_hours: int, credentials) -> str:
    """Create the ephemeral room dataset carrying the negotiated TTL."""
    client = bigquery.Client(project=project, credentials=credentials)
    room_id = f"{project}.room_{terms_digest}"
    dataset = bigquery.Dataset(room_id)
    dataset.location = "US"
    dataset.default_table_expiration_ms = ttl_hours * 3600 * 1000
    dataset.description = f"Concordat clean room {terms_digest}; TTL {ttl_hours}h"
    client.create_dataset(dataset, exists_ok=True)
    log.info("room %s created (ttl=%dh)", room_id, ttl_hours)
    return room_id


def revoke_contribution(cfg: BankConfig, terms_digest: str) -> None:
    """A bank withdraws its own contribution view.

    Only the owning bank can do this: the room runner has no delete rights inside anyone's
    dataset, which is why dissolution is a cooperative act rather than a central one.
    """
    client = bigquery.Client(project=cfg.project, credentials=bank_credentials(cfg))
    client.delete_table(contribution_view_id(cfg, terms_digest), not_found_ok=True)
    log.info("%s revoked its contribution for %s", cfg.bank, terms_digest)


def dissolve_room(project: str, terms_digest: str, credentials) -> None:
    """Drop the room itself. Contributions are revoked separately, by their owners."""
    client = bigquery.Client(project=project, credentials=credentials)
    client.delete_dataset(f"{project}.room_{terms_digest}", delete_contents=True, not_found_ok=True)
    log.info("room %s dissolved", terms_digest)
