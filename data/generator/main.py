"""Synthetic ledger generator: 3 bank ledgers + ground truth, deterministic from config seed.

Usage:
    python -m data.generator.main               # generate parquet to data/generator/output/
    python -m data.generator.main --load        # ... and load to BigQuery (bq CLI, concordat config)
    python -m data.generator.main --check       # run sanity checks against BigQuery
    python -m data.generator.main --scale 0.01  # scaled-down volumes (tests)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).parent
OUT = ROOT / "output"

CHANNELS = np.array(["transfer", "pos", "ussd", "web"])
NARRATIONS = np.array(
    ["transfer", "school fees", "invoice 4421", "salary aug", "pos purchase",
     "airtime topup", "loan repayment", "gift", "rent", "supplies"]
)
SCHEMA = pa.schema(
    [
        ("txn_id", pa.string()),
        ("ts", pa.timestamp("us")),
        ("src_account", pa.string()),
        ("dst_account", pa.string()),
        ("src_bank", pa.string()),
        ("dst_bank", pa.string()),
        ("amount", pa.float64()),
        ("currency", pa.string()),
        ("channel", pa.string()),
        ("narration", pa.string()),
    ]
)


def load_cfg(path: Path, scale: float) -> dict:
    cfg = yaml.safe_load(path.read_text())
    for key in ("accounts_per_bank", "benign_rows_per_bank"):
        cfg[key] = max(100, int(cfg[key] * scale))
    for key in ("structuring_accounts_per_bank", "velocity_accounts_per_bank"):
        cfg[key] = max(2, int(cfg[key] * min(1.0, scale * 10)))
    return cfg


class Ledgers:
    """Per-bank Arrow chunks (bulk) + row lists (hand-written patterns).

    Bulk data goes straight to Arrow tables so 10M+ rows never exist as Python objects.
    Cross-bank rows are mirrored into the receiving bank's ledger (both sides see the wire).
    """

    def __init__(self, banks: dict[str, str]):
        self.banks = banks
        self.chunks: dict[str, list[pa.Table]] = {b: [] for b in banks}
        self.rows: dict[str, list[dict]] = {b: [] for b in banks}
        self.ground_truth: list[tuple[str, str, str, str]] = []  # pattern, txn_id, src_bank, note

    def add_bulk(self, bank: str, arrays: dict[str, np.ndarray]) -> None:
        self.chunks[bank].append(pa.table(arrays, schema=SCHEMA))

    def add_txn(self, txn_id, ts, src_acct, dst_acct, src_bank, dst_bank, amount,
                channel="transfer", narration="transfer", pattern=None, note=""):
        if isinstance(ts, np.datetime64):
            ts = ts.astype("datetime64[us]").item()
        row = dict(txn_id=txn_id, ts=ts, src_account=src_acct, dst_account=dst_acct,
                   src_bank=src_bank, dst_bank=dst_bank, amount=float(amount),
                   currency="NGN", channel=channel, narration=narration)
        self.rows[src_bank].append(row)
        if dst_bank in self.banks and dst_bank != src_bank:
            self.rows[dst_bank].append(row)
        if pattern:
            self.ground_truth.append((pattern, txn_id, src_bank, note))

    def table(self, bank: str) -> pa.Table:
        parts = list(self.chunks[bank])
        if self.rows[bank]:
            cols = {f.name: [r[f.name] for r in self.rows[bank]] for f in SCHEMA}
            parts.append(pa.table(cols, schema=SCHEMA))
        return pa.concat_tables(parts)


def accounts(prefix: str, n: int) -> np.ndarray:
    return np.char.add(f"{prefix}-", np.arange(n).astype(str))


def gen_benign(rng, bank, prefix, accts, other_banks, cfg, ledgers: Ledgers) -> None:
    n = cfg["benign_rows_per_bank"]
    start = np.datetime64(cfg["window_start"])
    ts = (start + rng.integers(0, cfg["window_days"] * 86400, n).astype("timedelta64[s]")).astype("datetime64[us]")
    src = rng.choice(accts, n)
    cross = rng.random(n) < cfg["cross_bank_fraction"]
    dst_bank = np.where(cross, rng.choice([b for b, _ in other_banks], n), bank)
    # own-bank dst by default; cross rows overwritten per receiving bank below
    dst = rng.choice(accts, n).astype("U16")
    for ob, oprefix in other_banks:
        m = dst_bank == ob
        dst[m] = np.char.add(f"{oprefix}-", rng.integers(0, cfg["accounts_per_bank"], int(m.sum())).astype(str))
    amount = np.round(np.exp(rng.normal(9.2, 1.4, n)), 2)  # lognormal, median ~10k NGN
    arrays = dict(
        txn_id=np.char.add(f"{prefix}-B", np.arange(n).astype(str)),
        ts=ts,
        src_account=src, dst_account=dst,
        src_bank=np.full(n, bank), dst_bank=dst_bank,
        amount=amount, currency=np.full(n, "NGN"),
        channel=rng.choice(CHANNELS, n), narration=rng.choice(NARRATIONS, n),
    )
    ledgers.add_bulk(bank, arrays)
    for ob, _ in other_banks:
        m = dst_bank == ob
        ledgers.add_bulk(ob, {k: v[m] for k, v in arrays.items()})


def gen_structuring(rng, bank, prefix, accts, cfg, ledgers: Ledgers) -> None:
    start = np.datetime64(cfg["window_start"])
    for i, acct in enumerate(rng.choice(accts, cfg["structuring_accounts_per_bank"], replace=False)):
        base = start + rng.integers(0, cfg["window_days"] * 86400).item() * np.timedelta64(1, "s")
        for j in range(int(rng.integers(6, 13))):
            ledgers.add_txn(
                f"{prefix}-S{i}-{j}", base + np.timedelta64(int(rng.integers(0, 172800)), "s"),
                str(acct), str(rng.choice(accts)), bank, bank,
                round(float(rng.uniform(480000, 499999)), 2),
                narration="transfer", pattern="structuring", note=f"burst account {acct}",
            )


def gen_velocity(rng, bank, prefix, accts, cfg, ledgers: Ledgers) -> None:
    start = np.datetime64(cfg["window_start"])
    for i, acct in enumerate(rng.choice(accts, cfg["velocity_accounts_per_bank"], replace=False)):
        base = start + rng.integers(0, cfg["window_days"] * 86400).item() * np.timedelta64(1, "s")
        for j in range(int(rng.integers(100, 140))):
            ledgers.add_txn(
                f"{prefix}-V{i}-{j}", base + np.timedelta64(int(rng.integers(0, 3600)), "s"),
                str(acct), str(rng.choice(accts)), bank, bank,
                round(float(rng.uniform(500, 5000)), 2),
                channel="ussd", pattern="velocity", note=f"velocity account {acct}",
            )


def gen_golden_ring(cfg, ledgers: Ledgers) -> None:
    """Victim at alpha -> mules in alpha -> boundary -> meridian -> boundary -> union cash-out fan-in."""
    t0 = datetime.fromisoformat(cfg["golden_ring"]["t0"])
    amt = cfg["golden_ring"]["victim_amount"]

    def at(minutes: float) -> datetime:
        return t0 + timedelta(minutes=minutes)

    g = "golden_ring"
    ledgers.add_txn("ALP-G0", at(0), "ALP-9000001", "ALP-9000002", "alpha", "alpha", amt,
                    channel="web", narration="invoice 4421", pattern=g, note="victim debit")
    ledgers.add_txn("ALP-G1", at(8), "ALP-9000002", "ALP-9000003", "alpha", "alpha", amt * 0.497,
                    pattern=g, note="alpha hop split 1")
    ledgers.add_txn("ALP-G2", at(9), "ALP-9000002", "ALP-9000004", "alpha", "alpha", amt * 0.497,
                    pattern=g, note="alpha hop split 2")
    ledgers.add_txn("ALP-G3", at(25), "ALP-9000003", "MER-9000101", "alpha", "meridian", amt * 0.492,
                    pattern=g, note="boundary alpha->meridian")
    ledgers.add_txn("ALP-G4", at(31), "ALP-9000004", "MER-9000102", "alpha", "meridian", amt * 0.492,
                    pattern=g, note="boundary alpha->meridian")
    ledgers.add_txn("MER-G5", at(50), "MER-9000101", "MER-9000103", "meridian", "meridian", amt * 0.487,
                    pattern=g, note="meridian hop")
    ledgers.add_txn("MER-G6", at(55), "MER-9000102", "MER-9000104", "meridian", "meridian", amt * 0.487,
                    pattern=g, note="meridian hop")
    n_cash = cfg["golden_ring"]["cashout_accounts"]
    per = amt * 0.96 / n_cash
    for i in range(n_cash):
        src = "MER-9000103" if i < n_cash // 2 else "MER-9000104"
        ledgers.add_txn(f"MER-G7-{i}", at(80 + i * 1.5), src, f"UNI-90002{i:02d}", "meridian", "union",
                        round(per, 2), pattern=g, note="boundary meridian->union fan-out")
    for i in range(n_cash):
        ledgers.add_txn(f"UNI-G8-{i}", at(130 + i * 4), f"UNI-90002{i:02d}", "CASH", "union", "external",
                        round(per * 0.99, 2), channel="atm", narration="ATM-LAG-014",
                        pattern=g, note="cash-out cluster ATM-LAG-014")


def gen_red_herring(cfg, ledgers: Ledgers) -> None:
    """Fully intra-meridian ring: proves solo detection works; not the demo centerpiece."""
    t0 = datetime.fromisoformat(cfg["golden_ring"]["t0"]) - timedelta(days=3)

    def at(minutes: float) -> datetime:
        return t0 + timedelta(minutes=minutes)

    r = "red_herring_ring"
    ledgers.add_txn("MER-R0", at(0), "MER-9000901", "MER-9000902", "meridian", "meridian", 850000,
                    channel="web", pattern=r, note="victim debit")
    ledgers.add_txn("MER-R1", at(12), "MER-9000902", "MER-9000903", "meridian", "meridian", 845000,
                    pattern=r, note="hop")
    ledgers.add_txn("MER-R2", at(30), "MER-9000903", "MER-9000904", "meridian", "meridian", 840000,
                    pattern=r, note="hop")
    ledgers.add_txn("MER-R3", at(65), "MER-9000904", "CASH", "meridian", "external", 830000,
                    channel="atm", narration="ATM-IKJ-002", pattern=r, note="cash-out")


def generate(cfg: dict) -> dict[str, pa.Table]:
    rng = np.random.default_rng(cfg["seed"])
    banks = cfg["banks"]
    ledgers = Ledgers(banks)
    pools = {b: accounts(p, cfg["accounts_per_bank"]) for b, p in banks.items()}
    for bank, prefix in banks.items():
        others = [(b, p) for b, p in banks.items() if b != bank]
        gen_benign(rng, bank, prefix, pools[bank], others, cfg, ledgers)
        gen_structuring(rng, bank, prefix, pools[bank], cfg, ledgers)
        gen_velocity(rng, bank, prefix, pools[bank], cfg, ledgers)
    gen_golden_ring(cfg, ledgers)
    gen_red_herring(cfg, ledgers)

    tables = {bank: ledgers.table(bank) for bank in banks}
    gt = ledgers.ground_truth
    tables["ground_truth"] = pa.table(
        {
            "pattern": [g[0] for g in gt],
            "txn_id": [g[1] for g in gt],
            "src_bank": [g[2] for g in gt],
            "note": [g[3] for g in gt],
        }
    )
    return tables


def write_parquet(tables: dict[str, pa.Table]) -> None:
    OUT.mkdir(exist_ok=True)
    for name, table in tables.items():
        dest = OUT / f"{'ground_truth' if name == 'ground_truth' else 'bank_' + name}.parquet"
        pq.write_table(table, dest)
        print(f"  wrote {dest.name}: {table.num_rows:,} rows")


def bq(args: list[str], cfg: dict, quiet: bool = False) -> None:
    env = {**os.environ, "CLOUDSDK_ACTIVE_CONFIG_NAME": "concordat"}
    subprocess.run(["bq", f"--project_id={cfg['project']}", *args],
                   check=not quiet, env=env, capture_output=quiet)


def load(cfg: dict) -> None:
    datasets = [f"bank_{b}" for b in cfg["banks"]] + ["ground_truth"]
    for ds in datasets:
        bq(["mk", f"--location={cfg['location']}", "-d", ds], cfg, quiet=True)  # ignore "exists"
    for ds in datasets:
        table = "txns" if ds == "ground_truth" else "transactions"
        print(f"  loading {ds}.{table} ...")
        bq(["load", "--replace", "--source_format=PARQUET", f"{ds}.{table}", str(OUT / f"{ds}.parquet")], cfg)


def check(cfg: dict) -> None:
    for sql_file in sorted((ROOT / "checks").glob("*.sql")):
        print(f"\n=== {sql_file.name} ===")
        bq(["query", "--use_legacy_sql=false", sql_file.read_text()], cfg)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--load", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cfg = load_cfg(Path(args.config), args.scale)
    if not args.check or args.load:
        print(f"generating (seed={cfg['seed']}, scale={args.scale}) ...")
        tables = generate(cfg)
        write_parquet(tables)
        total = sum(t.num_rows for n, t in tables.items() if n != "ground_truth")
        print(f"total ledger rows: {total:,}")
        if total < 10_000_000 and args.scale >= 1.0:
            print("WARNING: submission claims 10M+ rows", file=sys.stderr)
    if args.load:
        load(cfg)
    if args.check:
        check(cfg)


if __name__ == "__main__":
    main()
