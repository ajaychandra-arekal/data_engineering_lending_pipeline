"""
Glue Python shell job: Bronze -> Silver, version 2.

Reads raw Parquet written by the extract job, cleans each month, validates it and
writes it to processed/ as Parquet, one folder per issue_month.

How it finds its work (no input path needed):
1. Read the last month the extract job wrote to raw  (_state/extract_tracker.txt).
2. Read the last month this job processed            (_state/silver_tracker.txt).
3. Process every month in between, oldest first, and move the Silver tracker
   forward after each month is safely written.
If the two trackers are equal, there is nothing new and the job stops.

Input:  s3://<bucket>/lending-data-monthly/raw/loans_YYYY-MM.parquet
Output: s3://<bucket>/lending-data-monthly/processed/issue_month=YYYY-MM/loans.parquet

Job details in Glue:
- Type: Python shell, Python 3.9, 'Load common analytics libraries' ticked, 1/16 DPU
- IAM role: the Glue job role, with read/write access to the bucket
- Timeout: 10 minutes
- No connection and no job parameters (S3 access comes from the IAM role)

Before the first run:
- _state/silver_tracker.txt must exist and hold the last month already in processed/

Version 1 (see Git history) read one raw CSV given by --input_file_path,
started by a Lambda on S3 upload.
"""

# ---------- IMPORTS ----------
from io import BytesIO

import boto3
import numpy as np
import pandas as pd


# ---------- SETTINGS ----------
BUCKET = "lending-data-de-project"
RAW_PREFIX = "lending-data-monthly/raw/"
PROCESSED_PREFIX = "lending-data-monthly/processed/"   # one sub-folder per issue_month

# Trackers: extract job writes the first, this job owns the second
EXTRACT_TRACKER_KEY = "lending-data-monthly/_state/extract_tracker.txt"
SILVER_TRACKER_KEY = "lending-data-monthly/_state/silver_tracker.txt"

# Raw Lending Club names -> readable snake_case names
RENAME = {
    # dates
    "issue_d": "issue_date",
    "earliest_cr_line": "earliest_credit_line",
    "last_pymnt_d": "last_payment_date",
    "last_credit_pull_d": "last_credit_pull_date",
    # loan terms
    "loan_amnt": "loan_amount",
    "term": "term_months",
    "int_rate": "interest_rate",
    # borrower
    "emp_title": "job_title",
    "emp_length": "employment_length_years",
    "annual_inc": "annual_income",
    "addr_state": "state",
    # credit profile
    "delinq_2yrs": "delinquencies_2yrs",
    "open_acc": "open_accounts",
    "pub_rec": "public_records",
    "revol_bal": "revolving_balance",
    "revol_util": "revolving_utilization",
    "total_acc": "total_accounts",
    "mort_acc": "mortgage_accounts",
    # payments and recoveries
    "out_prncp": "outstanding_principal",
    "total_pymnt": "total_payment",
    "total_rec_prncp": "principal_received",
    "total_rec_int": "interest_received",
}

# Dates arrive as text like 'Jan-2015'
DATE_COLS = ["issue_date", "earliest_credit_line", "last_payment_date", "last_credit_pull_date"]
DATE_FORMAT = "%b-%Y"

# Money and decimal values
DECIMAL_COLS = [
    "loan_amount", "installment", "annual_income", "revolving_balance",
    "outstanding_principal", "total_payment", "principal_received",
    "interest_received", "recoveries",
    "interest_rate", "revolving_utilization", "dti",
]

# Percentages that may contain a '%' sign in some files
PERCENT_COLS = ["interest_rate", "revolving_utilization"]

# Whole-number counts (may contain blanks, so they use the nullable Int64 type)
COUNT_COLS = ["delinquencies_2yrs", "open_accounts", "public_records", "total_accounts", "mortgage_accounts"]

# Category codes stored in upper case
UPPER_COLS = ["grade", "sub_grade", "state", "home_ownership"]

# Categories stored in lower case (to match STATUS_MAP keys)
LOWER_COLS = ["purpose", "loan_status", "verification_status"]

# Text employment length -> years (anything else, like 'n/a', becomes null)
EMP_MAP = {
    "< 1 year": 0,
    "1 year": 1,
    "2 years": 2,
    "3 years": 3,
    "4 years": 4,
    "5 years": 5,
    "6 years": 6,
    "7 years": 7,
    "8 years": 8,
    "9 years": 9,
    "10+ years": 10,
}

# Placeholder codes in the source, not real debt-to-income ratios
DTI_SENTINELS = [-1, 999]

# Rare, unclear categories merged into OTHER
HOME_OWNERSHIP_MAP = {"ANY": "OTHER", "NONE": "OTHER"}

# loan_status (lower case) -> reporting category
STATUS_MAP = {
    "current": "current",
    "fully paid": "fully_paid",
    "in grace period": "early_late",
    "late (16-30 days)": "early_late",
    "late (31-120 days)": "late",
    "default": "default",
    "charged off": "charged_off",
}

# Categories counted as a 'bad' loan for bad-rate analysis
BAD_CATEGORIES = ["late", "default", "charged_off"]

# title duplicates purpose, zip_code is masked ('123xx')
DROP_COLS = ["title", "zip_code"]


# ---------- S3 CLIENT ----------
# No keys: in Glue, boto3 uses the job's IAM role
s3 = boto3.client("s3")


# ---------- TRANSFORMATIONS ----------
def rename_columns(df):
    """Give the raw Lending Club columns readable snake_case names."""
    df = df.rename(columns=RENAME)
    return df


def parse_dates(df):
    """Convert 'Mon-YYYY' text to dates. Null last_payment_date if it is before issue_date."""
    for col in DATE_COLS:
        df[col] = pd.to_datetime(df[col], format=DATE_FORMAT, errors="coerce")

    # A payment can't happen before the loan is issued, so these dates are source errors
    bad_payment_date = df["last_payment_date"] < df["issue_date"]
    df.loc[bad_payment_date, "last_payment_date"] = pd.NaT
    print(f"[parse_dates] last_payment_date before issue_date, set to null: {bad_payment_date.sum()}")

    return df


def convert_numbers(df):
    """Strip '%' where present, then convert decimal and count columns to numbers."""
    # Some files store percentages as text like '13.5%'. regex=False: plain text, not a pattern
    for col in PERCENT_COLS:
        df[col] = df[col].str.replace("%", "", regex=False).str.strip()

    for col in DECIMAL_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)

    for col in COUNT_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    return df


def clean_text(df):
    """Trim spaces and standardise casing so the same value always looks the same."""
    for col in UPPER_COLS:
        df[col] = df[col].str.strip().str.upper()

    for col in LOWER_COLS:
        df[col] = df[col].str.strip().str.lower()

    # 'teacher', 'TEACHER ' and 'Teacher' should all group together
    df["job_title"] = (
        df["job_title"]
        .str.strip()
        .str.title()
        .fillna("Not Specified")
        .replace("", "Not Specified")
    )
    return df


def fix_values(df):
    """Fix specific source formats and placeholder values."""
    # ' 36 months' -> 36
    df["term_months"] = df["term_months"].str.strip().str.split(" ").str[0].astype(int)

    # '10+ years' -> 10. Anything not in EMP_MAP (blank, 'n/a') becomes null: unknown, not zero
    df["employment_length_years"] = df["employment_length_years"].map(EMP_MAP).astype("Int64")

    df["dti"] = df["dti"].replace(DTI_SENTINELS, np.nan)

    df["home_ownership"] = df["home_ownership"].replace(HOME_OWNERSHIP_MAP)

    return df


def add_derived(df, raw):
    """Add partition columns, risk categories, flags and a stable row key."""
    df["issue_month"] = df["issue_date"].dt.strftime("%Y-%m")
    df["issue_year"] = df["issue_date"].dt.year

    df["loan_status_category"] = df["loan_status"].map(STATUS_MAP)
    df["is_bad"] = df["loan_status_category"].isin(BAD_CATEGORIES).astype(int)

    # Flag, don't delete: the rows are real loans, reports decide whether to exclude them
    df["flag_zero_income"] = (df["annual_income"] == 0).astype(int)
    df["flag_revol_util_over_100"] = (df["revolving_utilization"] > 100).astype(int)

    # Hash of the untouched raw row: the same loan gets the same key on every run
    df["loan_key"] = pd.util.hash_pandas_object(raw, index=False).astype(str)

    return df


def finalize(df):
    """Drop columns not needed in Silver and remove exact duplicate rows."""
    df = df.drop(columns=DROP_COLS)

    before = len(df)
    df = df.drop_duplicates()
    print(f"[finalize] Duplicate rows removed: {before - len(df)}")

    return df


def to_silver(raw):
    """Turn one month of raw Bronze loans (all text) into the cleaned Silver table."""
    df = raw.copy()
    df = rename_columns(df)
    df = parse_dates(df)
    df = convert_numbers(df)
    df = clean_text(df)
    df = fix_values(df)
    df = add_derived(df, raw)
    df = finalize(df)
    return df


# ---------- VALIDATION ----------
def validate_silver(df, raw):
    """Stop with a clear error if the Silver output breaks a rule."""
    month = df["issue_month"].iloc[0] if len(df) else "unknown"

    # 1. Nothing invented: Silver can't have more rows than Bronze
    if len(df) > len(raw):
        raise ValueError(f"{month}: Silver has more rows ({len(df)}) than raw ({len(raw)})")

    # 2. Every issue_date parsed
    if df["issue_date"].isna().any():
        raise ValueError(f"{month}: some issue_date values could not be parsed")

    # 3. One month per file
    if df["issue_month"].nunique() != 1:
        raise ValueError(f"{month}: file contains more than one issue_month")

    # 4. Every loan_status is in STATUS_MAP
    if df["loan_status_category"].isna().any():
        unknown = df.loc[df["loan_status_category"].isna(), "loan_status"].unique().tolist()
        raise ValueError(f"{month}: loan_status not in STATUS_MAP: {unknown}")

    # 5. Term is only 36 or 60
    if not df["term_months"].isin([36, 60]).all():
        raise ValueError(f"{month}: unexpected term_months values")

    # 6. Grade is A to G, and sub_grade starts with the grade
    if not df["grade"].isin(list("ABCDEFG")).all():
        raise ValueError(f"{month}: unexpected grade values")
    if (df["sub_grade"].str[0] != df["grade"]).any():
        raise ValueError(f"{month}: sub_grade does not match grade")

    # 7. loan_key is unique
    if not df["loan_key"].is_unique:
        raise ValueError(f"{month}: duplicate loan_key values")

    print(f"[validate_silver] {month}: OK, {len(df):,} rows, bad rate {df['is_bad'].mean():.2%}")


# ---------- TRACKERS ----------
def read_tracker(key):
    """Return the month stored in a tracker file, e.g. '2018-11'."""
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    return obj["Body"].read().decode("utf-8").strip()


def update_tracker(key, month):
    s3.put_object(Bucket=BUCKET, Key=key, Body=month.encode("utf-8"))
    print(f"[update_tracker] {key} set to {month}")


def next_month(month):
    """'2018-11' -> '2018-12', '2018-12' -> '2019-01'."""
    year, mon = map(int, month.split("-"))
    if mon == 12:
        return f"{year + 1}-01"
    return f"{year}-{mon + 1:02d}"


def months_to_process(last_processed, last_extracted):
    """Every month after last_processed, up to and including last_extracted."""
    months = []
    month = next_month(last_processed)
    while month <= last_extracted:
        months.append(month)
        month = next_month(month)
    return months


# ---------- S3 READ AND WRITE ----------
def read_raw(month):
    """Download one raw Parquet file from S3 as a DataFrame (all text)."""
    key = f"{RAW_PREFIX}loans_{month}.parquet"
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    raw = pd.read_parquet(BytesIO(obj["Body"].read()))
    print(f"[read_raw] {month}: {len(raw):,} rows from s3://{BUCKET}/{key}")
    return raw


def write_processed(df):
    """Upload one month of Silver data as Parquet into its issue_month folder."""
    month = df["issue_month"].iloc[0]
    key = f"{PROCESSED_PREFIX}issue_month={month}/loans.parquet"

    buffer = BytesIO()
    df.to_parquet(buffer, index=False)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buffer.getvalue())

    size_mb = len(buffer.getvalue()) / 1024 / 1024
    print(f"[write_processed] {month}: {len(df):,} rows, {size_mb:.1f} MB -> s3://{BUCKET}/{key}")


# ---------- JOB ----------
def process_month(month):
    """Read one raw month, transform it to Silver, validate, and write Parquet."""
    raw = read_raw(month)
    silver = to_silver(raw)
    validate_silver(silver, raw)
    write_processed(silver)
    return len(silver)


def main():
    last_extracted = read_tracker(EXTRACT_TRACKER_KEY)
    last_processed = read_tracker(SILVER_TRACKER_KEY)
    print(f"[main] Last extracted: {last_extracted} | last processed: {last_processed}")

    months = months_to_process(last_processed, last_extracted)
    if not months:
        print("[main] Nothing new in raw. Silver is up to date.")
        return

    print(f"[main] {len(months)} month(s) to process: {months[0]} to {months[-1]}")
    for month in months:
        rows = process_month(month)
        update_tracker(SILVER_TRACKER_KEY, month)   # only after the month is safely written
        print(f"[main] {month} done: {rows:,} rows")


if __name__ == "__main__":
    main()