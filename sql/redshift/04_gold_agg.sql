-- Gold aggregate: vintage performance by issue month and grade.
-- Ready-made table for the Power BI vintage report.

CREATE TABLE gold.agg_vintage AS (
    SELECT TO_CHAR(f.issue_date, 'YYYY-MM')                  AS issue_month,
           g.grade,
           COUNT(*)                                         AS loans,
           CAST(SUM(f.loan_amount) AS DECIMAL(15,2))        AS funded_amount,
           SUM(f.is_bad)                                    AS bad_loans,
           CAST(AVG(f.is_bad::FLOAT) * 100 AS DECIMAL(5,2)) AS bad_rate_pct,
           CAST(AVG(f.interest_rate) AS DECIMAL(5,2))       AS avg_interest_rate
    FROM gold.fact_loan AS f
    JOIN gold.dim_grade AS g ON f.grade_id = g.grade_id
    GROUP BY 1, 2
);

-- Check: no month missing between the first and last issue month
WITH months AS (
    SELECT DISTINCT TO_DATE(issue_month, 'YYYY-MM') AS m FROM gold.agg_vintage
),
gaps AS (
    SELECT m, LAG(m) OVER (ORDER BY m) AS prev_m FROM months
)
SELECT m, prev_m
FROM gaps
WHERE prev_m IS NOT NULL
  AND DATEDIFF(month, prev_m, m) <> 1;   -- expect 0 rows
