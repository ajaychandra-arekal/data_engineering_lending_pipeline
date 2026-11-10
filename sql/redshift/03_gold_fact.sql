-- Gold fact table: one row per loan, with keys to the dimensions and the loan measures.

CREATE TABLE gold.fact_loan
SORTKEY (issue_date)
AS (
    SELECT
        -- keys
        l.loan_key,
        grd.grade_id,
        p.purpose_id,
        geo.geography_id,
        st.status_id,
        -- dates (join to gold.dim_date.month_start)
        l.issue_date::DATE        AS issue_date,
        l.last_payment_date::DATE AS last_payment_date,
        -- loan terms
        l.term_months,
        l.loan_amount,
        l.installment,
        l.interest_rate,
        -- borrower and credit profile
        l.annual_income,
        l.employment_length_years,
        l.home_ownership,
        l.verification_status,
        l.dti,
        l.revolving_balance,
        l.revolving_utilization,
        -- payments and recoveries
        l.outstanding_principal,
        l.total_payment,
        l.principal_received,
        l.interest_received,
        l.recoveries,
        -- risk measure and flags
        l.is_bad,
        l.flag_zero_income,
        l.flag_revol_util_over_100
    FROM silver.loans AS l
    LEFT JOIN gold.dim_grade       AS grd ON l.grade = grd.grade AND l.sub_grade = grd.sub_grade
    LEFT JOIN gold.dim_purpose     AS p   ON l.purpose = p.purpose
    LEFT JOIN gold.dim_geography   AS geo ON l.state = geo.state
    LEFT JOIN gold.dim_loan_status AS st  ON l.loan_status = st.loan_status
);

SELECT COUNT(*) FROM gold.fact_loan;   -- 1,794,323
