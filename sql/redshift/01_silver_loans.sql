-- Silver layer in Redshift: one row per loan, loaded from S3 processed/ (Parquet).
-- Columns are listed in the same order as the Parquet files, because COPY ... FORMAT AS PARQUET
-- matches columns by position, not by name.

CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE silver.loans (
    loan_amount              DOUBLE PRECISION,
    term_months              BIGINT,
    interest_rate            DOUBLE PRECISION,
    installment              DOUBLE PRECISION,
    grade                    VARCHAR(4),
    sub_grade                VARCHAR(4),
    job_title                VARCHAR(512),
    employment_length_years  BIGINT,
    home_ownership           VARCHAR(16),
    annual_income            DOUBLE PRECISION,
    verification_status      VARCHAR(32),
    issue_date               TIMESTAMP,
    loan_status              VARCHAR(64),
    purpose                  VARCHAR(64),
    state                    VARCHAR(4),
    dti                      DOUBLE PRECISION,
    delinquencies_2yrs       BIGINT,
    earliest_credit_line     TIMESTAMP,
    open_accounts            BIGINT,
    public_records           BIGINT,
    revolving_balance        DOUBLE PRECISION,
    revolving_utilization    DOUBLE PRECISION,
    total_accounts           BIGINT,
    outstanding_principal    DOUBLE PRECISION,
    total_payment            DOUBLE PRECISION,
    principal_received       DOUBLE PRECISION,
    interest_received        DOUBLE PRECISION,
    recoveries               DOUBLE PRECISION,
    last_payment_date        TIMESTAMP,
    last_credit_pull_date    TIMESTAMP,
    mortgage_accounts        BIGINT,
    issue_month              VARCHAR(7),
    issue_year               INTEGER,
    loan_status_category     VARCHAR(32),
    is_bad                   BIGINT,
    flag_zero_income         BIGINT,
    flag_revol_util_over_100 BIGINT,
    loan_key                 VARCHAR(32)
)
DISTSTYLE AUTO
SORTKEY (issue_date);

-- History load: all 48 months at once (1,794,323 rows).
-- IAM_ROLE DEFAULT uses the role attached to the Redshift Serverless namespace.
COPY silver.loans
FROM 's3://lending-data-de-project/lending-data-monthly/processed/'
IAM_ROLE DEFAULT
FORMAT AS PARQUET;

SELECT COUNT(*) FROM silver.loans;   -- 1,794,323
