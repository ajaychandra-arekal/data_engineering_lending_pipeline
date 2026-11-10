create database lending_lake;

-- Row counts
SELECT COUNT(*) AS raw_rows FROM raw;              -- 1,794,323
SELECT COUNT(*) AS processed_rows FROM processed;  -- 1,794,323

-- Partitions the crawler found
SHOW PARTITIONS processed;   -- 48 rows, issue_month=2015-01 to issue_month=2018-12

-- Reconciliation: raw vs processed per month
WITH raw_counts AS (
    SELECT date_format(date_parse(issue_d, '%b-%Y'), '%Y-%m') AS month,
           COUNT(*) AS raw_rows
    FROM raw
    GROUP BY 1
),
processed_counts AS (
    SELECT issue_month AS month,
           COUNT(*) AS processed_rows
    FROM processed
    GROUP BY 1
)
SELECT COALESCE(r.month, p.month) AS month,
       r.raw_rows,
       p.processed_rows,
       CASE WHEN r.raw_rows = p.processed_rows THEN 'MATCH' ELSE 'MISMATCH' END AS status
FROM raw_counts r
FULL OUTER JOIN processed_counts p
    ON r.month = p.month
ORDER BY month;

-- Mismatches only (the version the Workflow will use)
WITH raw_counts AS (
    SELECT date_format(date_parse(issue_d, '%b-%Y'), '%Y-%m') AS month, COUNT(*) AS raw_rows
    FROM raw GROUP BY 1
),
processed_counts AS (
    SELECT issue_month AS month, COUNT(*) AS processed_rows
    FROM processed GROUP BY 1
)
SELECT COALESCE(r.month, p.month) AS month, r.raw_rows, p.processed_rows
FROM raw_counts r
FULL OUTER JOIN processed_counts p ON r.month = p.month
WHERE r.raw_rows IS NULL
   OR p.processed_rows IS NULL
   OR r.raw_rows <> p.processed_rows;
   
   -- Did the cleaning work? Raw text vs processed values (December 2018)
   SELECT 'raw' AS layer,
       COUNT(*) AS loans,
       AVG(TRY_CAST(loan_amnt AS DOUBLE)) AS avg_loan_amount,
       AVG(TRY_CAST(REPLACE(TRIM(int_rate), '%', '') AS DOUBLE)) AS avg_interest_rate
FROM raw
WHERE issue_d = 'Dec-2018'
UNION ALL
SELECT 'processed',
       COUNT(*),
       AVG(loan_amount),
       AVG(interest_rate)
FROM processed
WHERE issue_month = '2018-12';

-- Data quality summary per month
SELECT issue_month,
       COUNT(*) AS loans,
       ROUND(AVG(is_bad) * 100, 2) AS bad_rate_pct,
       SUM(flag_zero_income) AS zero_income,
       SUM(flag_revol_util_over_100) AS revol_util_over_100,
       SUM(CASE WHEN dti IS NULL THEN 1 ELSE 0 END) AS dti_missing,
       SUM(CASE WHEN employment_length_years IS NULL THEN 1 ELSE 0 END) AS emp_length_missing
FROM processed
GROUP BY issue_month
ORDER BY issue_month;

-- Partition pruning (good for the showcase)
SELECT COUNT(*) FROM processed;                              -- reads all 48 folders
SELECT COUNT(*) FROM processed WHERE issue_month = '2018-12'; -- reads one folder