-- Row counts per ledger. These read across all four projects because they run as the
-- operator seeding the data, never as a bank: no bank's service account can do this.
SELECT 'bank_alpha' AS ledger, COUNT(*) AS row_count FROM `concordat-alpha.bank_alpha.transactions`
UNION ALL SELECT 'bank_meridian', COUNT(*) FROM `concordat-meridian.bank_meridian.transactions`
UNION ALL SELECT 'bank_union', COUNT(*) FROM `concordat-union.bank_union.transactions`
UNION ALL SELECT 'ground_truth', COUNT(*) FROM `concordat-hack.ground_truth.txns`
ORDER BY ledger
