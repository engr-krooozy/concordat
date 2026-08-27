-- Every planted txn must exist in at least one ledger.
WITH all_txns AS (
  SELECT txn_id FROM `concordat-alpha.bank_alpha.transactions`
  UNION DISTINCT SELECT txn_id FROM `concordat-meridian.bank_meridian.transactions`
  UNION DISTINCT SELECT txn_id FROM `concordat-union.bank_union.transactions`
)
SELECT g.pattern, COUNT(*) AS planted, COUNTIF(t.txn_id IS NOT NULL) AS present
FROM `concordat-hack.ground_truth.txns` g
LEFT JOIN all_txns t USING (txn_id)
GROUP BY g.pattern ORDER BY g.pattern
