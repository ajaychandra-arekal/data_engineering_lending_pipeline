-- Gold dimensions, built from silver.loans.

CREATE SCHEMA IF NOT EXISTS gold;

-- The four ID dimensions use an IDENTITY column: Redshift numbers new rows itself.
-- IDs are unique and never change, but they are not guaranteed to be in
-- alphabetical order or without gaps. That is fine: an ID only has to be unique.
-- New values are added each month by the Gold job (03_warehouse/loans_gold_job.py).

-- Grade and sub-grade (A1 ... G5)
CREATE TABLE gold.dim_grade (
    grade_id   BIGINT IDENTITY(1, 1),
    grade      VARCHAR(4),
    sub_grade  VARCHAR(4),
    PRIMARY KEY (grade_id)
);
INSERT INTO gold.dim_grade (grade, sub_grade)
SELECT DISTINCT grade, sub_grade FROM silver.loans;

-- Loan purpose (debt_consolidation, credit_card, ...)
CREATE TABLE gold.dim_purpose (
    purpose_id  BIGINT IDENTITY(1, 1),
    purpose     VARCHAR(64),
    PRIMARY KEY (purpose_id)
);
INSERT INTO gold.dim_purpose (purpose)
SELECT DISTINCT purpose FROM silver.loans;

-- Borrower state
CREATE TABLE gold.dim_geography (
    geography_id  BIGINT IDENTITY(1, 1),
    state         VARCHAR(4),
    PRIMARY KEY (geography_id)
);
INSERT INTO gold.dim_geography (state)
SELECT DISTINCT state FROM silver.loans;

-- Loan status with its reporting category. is_bad is taken from Silver,
-- so the bad-loan rule lives in one place (the Silver job).
CREATE TABLE gold.dim_loan_status (
    status_id             BIGINT IDENTITY(1, 1),
    loan_status           VARCHAR(64),
    loan_status_category  VARCHAR(32),
    is_bad                BIGINT,
    PRIMARY KEY (status_id)
);
INSERT INTO gold.dim_loan_status (loan_status, loan_status_category, is_bad)
SELECT DISTINCT loan_status, loan_status_category, is_bad FROM silver.loans;

-- Month calendar covering every issue and last payment month.
-- No ID column: the month itself is the key.
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