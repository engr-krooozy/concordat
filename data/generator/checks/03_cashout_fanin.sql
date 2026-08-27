-- Cash-out fan-in at ATM-LAG-014 must exceed the largest policy k (see /synthetic-ledger gotchas).
SELECT narration, COUNT(DISTINCT src_account) AS distinct_accounts, ROUND(SUM(amount)) AS total
FROM `concordat-union.bank_union.transactions`
WHERE channel = "atm" AND narration = "ATM-LAG-014"
GROUP BY narration
