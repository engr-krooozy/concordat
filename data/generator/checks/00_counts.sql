SELECT 'bank_alpha' AS ledger, COUNT(*) AS rows FROM `concordat-hack.bank_alpha.transactions`
UNION ALL SELECT 'bank_meridian', COUNT(*) FROM `concordat-hack.bank_meridian.transactions`
UNION ALL SELECT 'bank_union', COUNT(*) FROM `concordat-hack.bank_union.transactions`
UNION ALL SELECT 'ground_truth', COUNT(*) FROM `concordat-hack.ground_truth.txns`
ORDER BY ledger
