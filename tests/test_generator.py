from data.generator.main import ROOT, generate, load_cfg


def small():
    return load_cfg(ROOT / "config.yaml", 0.001)


def test_tables_and_patterns():
    tables = generate(small())
    assert set(tables) == {"alpha", "meridian", "union", "ground_truth"}
    gt = tables["ground_truth"].to_pydict()
    assert {"golden_ring", "red_herring_ring", "structuring", "velocity"} <= set(gt["pattern"])


def test_golden_ring_crosses_boundaries_and_mirrors():
    tables = generate(small())
    alpha = tables["alpha"].to_pydict()
    meridian = tables["meridian"].to_pydict()
    union = tables["union"].to_pydict()
    # boundary txn appears in BOTH ledgers (each bank sees its side of the wire)
    assert "ALP-G3" in alpha["txn_id"] and "ALP-G3" in meridian["txn_id"]
    # solo alpha trace dead-ends: the boundary rows leave alpha
    i = alpha["txn_id"].index("ALP-G3")
    assert alpha["dst_bank"][i] == "meridian"
    # cash-out fan-in cluster present in union with shared ATM narration
    atm = [n for c, n in zip(union["channel"], union["narration"]) if c == "atm" and n == "ATM-LAG-014"]
    assert len(atm) == 8


def test_deterministic():
    cfg = small()
    a, b = generate(cfg), generate(cfg)
    for name in a:
        assert a[name].equals(b[name]), name
