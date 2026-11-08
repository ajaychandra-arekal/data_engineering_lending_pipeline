"""
Load loan.csv into MySQL month by month, in one run.

- Reads loan.csv once (33 columns, all text), keeps loans issued from START_MONTH onwards.
- Appends one month at a time to the MySQL table, oldest first.
- Remembers the last month loaded in a tracker file, so a re-run continues where it stopped.
- Safe to re-run: before appending a month, any rows already in MySQL for that month are deleted.

Run from the project root:
    python3 data_ingestion/load_monthly_to_mysql.py            # load everything not yet loaded
    python3 data_ingestion/load_monthly_to_mysql.py --reset    # drop the table and start again

Needs data_ingestion/.env with MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_DB
"""

# 1. IMPORTS
import argparse
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

# 2. SETTINGS
BASE_DIR = Path(__file__).parent
RAW_FILE = BASE_DIR / "loan.csv"
TRACKER_FILE = BASE_DIR / "mysql_load_tracker.txt"
TABLE_NAME = "loans"
START_MONTH = "2015-01"
HELPER_COLS = ["issue_date", "issue_month"]
KEEP_COLS = [
    # dates
    "issue_d", "earliest_cr_line", "last_pymnt_d", "last_credit_pull_d",
    # loan terms
    "loan_amnt", "term", "int_rate", "installment", "grade", "sub_grade",
    "purpose", "title", "loan_status",
    # borrower
    "emp_title", "emp_length", "home_ownership", "annual_inc",
    "verification_status", "zip_code", "addr_state",
    # credit profile
    "dti", "delinq_2yrs", "open_acc", "pub_rec", "revol_bal",
    "revol_util", "total_acc", "mort_acc",
    # payments and recoveries
    "out_prncp", "total_pymnt", "total_rec_prncp", "total_rec_int", "recoveries",
]

load_dotenv(BASE_DIR / ".env")


# 3. DATABASE
def get_engine():
    """Create a connection to MySQL using details from .env."""
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    db = os.getenv("MYSQL_DB")
    return create_engine(f"mysql+pymysql://{user}:{password}@{host}:3306/{db}")


def check_connection(engine):
    """Fail fast if MySQL can't be reached, before the slow CSV load."""
    with engine.connect() as conn:
        db = conn.execute(text("SELECT DATABASE()")).scalar()
    print(f"[check_connection] Connected to database: {db}")


def table_exists(engine):
    return inspect(engine).has_table(TABLE_NAME)


def count_rows(engine):
    if not table_exists(engine):
        return 0
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}")).scalar()


def drop_table(engine):
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
    print(f"[drop_table] Dropped table {TABLE_NAME}")


# 4. TRACKER
def month_before(month):
    """'2015-01' -> '2014-12'."""
    return (pd.Period(month, freq="M") - 1).strftime("%Y-%m")


def read_tracker():
    """Return the last month loaded. If there is no tracker yet, start before START_MONTH."""
    if TRACKER_FILE.exists():
        last = TRACKER_FILE.read_text().strip()
    else:
        last = month_before(START_MONTH)
    print(f"[read_tracker] Last month loaded: {last}")
    return last


def update_tracker(month):
    TRACKER_FILE.write_text(month)


# 5. DATA
def load_loans():
    """Read the raw CSV, keeping only KEEP_COLS, everything as text."""
    print(f"[load_loans] Reading {RAW_FILE} ({len(KEEP_COLS)} columns)...")
    df = pd.read_csv(RAW_FILE, usecols=KEEP_COLS, dtype=str)
    print(f"[load_loans] Loaded {len(df):,} rows")
    return df


def add_month_label(df):
    """Add helper columns: issue_date (real date) and issue_month ('YYYY-MM')."""
    df["issue_date"] = pd.to_datetime(df["issue_d"], format="%b-%Y", errors="coerce")
    bad = df["issue_date"].isna().sum()
    if bad > 0:
        raise ValueError(f"{bad:,} issue_d values could not be parsed. Check the format.")
    df["issue_month"] = df["issue_date"].dt.strftime("%Y-%m")
    return df


def months_to_load(df, last_month):
    """Sorted list of months in the data that come after last_month (and from START_MONTH on)."""
    months = df["issue_month"].unique()
    return sorted(m for m in months if m > last_month and m >= START_MONTH)


def load_one_month(df, month, engine):
    """Replace any existing rows for this month in MySQL, then append the month. Return row count."""
    one_month = df[df["issue_month"] == month].drop(columns=HELPER_COLS)

    # Safe re-run: if a previous run crashed half way through this month, remove its rows first.
    if table_exists(engine):
        source_value = one_month["issue_d"].iloc[0]          # e.g. 'Jan-2015', as stored in MySQL
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {TABLE_NAME} WHERE issue_d = :m"), {"m": source_value})

    one_month.to_sql(TABLE_NAME, engine, if_exists="append", index=False, chunksize=10_000)
    return len(one_month)


# 6. MAIN
def main():
    parser = argparse.ArgumentParser(description="Load loan.csv into MySQL month by month.")
    parser.add_argument("--reset", action="store_true", help="drop the table and start from START_MONTH")
    args = parser.parse_args()

    engine = get_engine()
    check_connection(engine)

    if args.reset:
        drop_table(engine)
        TRACKER_FILE.unlink(missing_ok=True)
        print("[main] Tracker reset")

    last_month = read_tracker()

    df = add_month_label(load_loans())
    months = months_to_load(df, last_month)
    if not months:
        print("[main] Nothing to load. All months are already in MySQL.")
        return
    print(f"[main] {len(months)} months to load: {months[0]} to {months[-1]}")

    start = time.time()
    total = 0
    for i, month in enumerate(months, start=1):
        rows = load_one_month(df, month, engine)
        update_tracker(month)          # only after the month is safely in MySQL
        total += rows
        print(f"[main] {i}/{len(months)} {month}: {rows:,} rows  (running total {total:,})")

    expected = (df["issue_month"] >= START_MONTH).sum()
    in_db = count_rows(engine)
    print(f"[main] Done in {time.time() - start:,.0f}s. Loaded {total:,} rows this run.")
    print(f"[main] Rows in MySQL: {in_db:,} | expected from CSV: {expected:,} | "
          f"{'MATCH' if in_db == expected else 'MISMATCH, check before continuing'}")


if __name__ == "__main__":
    main()