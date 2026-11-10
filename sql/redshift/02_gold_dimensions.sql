-- Gold dimensions, built from silver.loans.
-- Each dimension gets a surrogate key from ROW_NUMBER, ordered so the IDs are stable.

CREATE SCHEMA IF NOT EXISTS gold;

-- Grade and sub-grade (A1 ... G5)
CREATE TABLE gold.dim_grade AS (
    SELECT ROW_NUMBER() OVER (ORDER BY grade, sub_grade) AS grade_id,
           grade,
           sub_grade
    FROM (SELECT DISTINCT grade, sub_grade FROM silver.loans) AS g
);

-- Loan purpose (debt_consolidation, credit_card, ...)
CREATE TABLE gold.dim_purpose AS (
    SELECT ROW_NUMBER() OVER (ORDER BY purpose) AS purpose_id,
           purpose
    FROM (SELECT DISTINCT purpose FROM silver.loans) AS p
);

-- Borrower state
CREATE TABLE gold.dim_geography AS (
    SELECT ROW_NUMBER() OVER (ORDER BY state) AS geography_id,
           state
    FROM (SELECT DISTINCT state FROM silver.loans) AS s
);

-- Loan status with its reporting category. is_bad is taken from Silver,
-- so the bad-loan rule lives in one place (the Silver job).
CREATE TABLE gold.dim_loan_status AS (
    SELECT ROW_NUMBER() OVER (ORDER BY loan_status, loan_status_category) AS status_id,
           loan_status,
           loan_status_category,
           is_bad
    FROM (SELECT DISTINCT loan_status, loan_status_category, is_bad FROM silver.loans) AS s
);

-- Month calendar covering every issue and last payment month
CREATE TABLE gold.dim_date AS (
    SELECT month_start,
           EXTRACT(year FROM month_start)    AS year,
           EXTRACT(quarter FROM month_start) AS quarter,
           EXTRACT(month FROM month_start)   AS month_num,
           TO_CHAR(month_start, 'Mon')       AS month_name,
           TO_CHAR(month_start, 'YYYY-MM')   AS year_month
    FROM (
        SELECT DISTINCT issue_date::DATE AS month_start FROM silver.loans
        UNION
        SELECT DISTINCT last_payment_date::DATE AS month_start FROM silver.loans
    ) AS t
    WHERE t.month_start IS NOT NULL
);
