-- The checkpoint proof: tracing the golden ring using ONLY bank_alpha's ledger must end at
-- boundary rows (dst_bank != 'alpha'). Expect exactly ALP-G3 and ALP-G4 -> meridian.
WITH h1 AS (
  SELECT * FROM `concordat-hack.bank_alpha.transactions`
  WHERE src_account = 'ALP-9000001' AND amount >= 2000000
    AND ts BETWEEN '2026-08-12' AND '2026-08-13'
), h2 AS (
  SELECT t.* FROM `concordat-hack.bank_alpha.transactions` t
  JOIN h1 ON t.src_account = h1.dst_account
  WHERE t.ts > h1.ts AND t.ts < TIMESTAMP_ADD(h1.ts, INTERVAL 2 HOUR) AND t.amount > 500000
), h3 AS (
  SELECT t.* FROM `concordat-hack.bank_alpha.transactions` t
  JOIN h2 ON t.src_account = h2.dst_account
  WHERE t.ts > h2.ts AND t.ts < TIMESTAMP_ADD(h2.ts, INTERVAL 2 HOUR) AND t.amount > 500000
)
SELECT DISTINCT txn_id, src_account, dst_account, dst_bank, ROUND(amount) AS amount
FROM h3 ORDER BY txn_id
