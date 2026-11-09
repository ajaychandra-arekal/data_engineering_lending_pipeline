"""
Glue Python shell job: extract the next month of loans from RDS MySQL into S3 raw (Bronze).

How it works:
1. Read the last extracted month from the tracker file in S3 (e.g. '2018-11').
2. Work out the next month ('2018-12') and its source format ('Dec-2018').
3. Query that month from RDS.
4. Write the rows as one Parquet file to raw/loans_YYYY-MM.parquet.
5. Update the tracker, only after the write succeeded.

If the month has no rows yet, nothing is written and the tracker is not changed,
so the next run simply tries the same month again.

Job details in Glue:
- Type: Python shell, Python 3.9, 'Load common analytics libraries' ticked, 1/16 DPU
- IAM role: the Glue job role, with read/write access to the bucket
- Timeout: 10 minutes
- Connection: lending-rds-conn (puts the job inside the VPC so it can reach RDS)
- Job parameters: --db_host, --db_name, --db_user, --db_password
  (the password lives in the job settings, never in this file or on GitHub)

Before the first run:
- _state/extract_tracker.txt must exist in the bucket and hold the last month
  already in raw (e.g. 2018-11), otherwise the job fails with NoSuchKey

Network it depends on:
- Security group lending-mysql-sg with a self-referencing All TCP rule,
  so Glue can reach RDS from inside the VPC
- S3 gateway endpoint

# ---------- IMPORTS ----------
import sys
from datetime import date
from io import BytesIO

import boto3
import pandas as pd
import pymysql
from awsglue.utils import getResolvedOptions


# ---------- SETTINGS ----------
BUCKET = "lending-data-de-project"
TRACKER_KEY = "lending-data-monthly/_state/extract_tracker.txt"
RAW_PREFIX = "lending-data-monthly/raw"
SOURCE_TABLE = "loans"

# No keys: in Glue, boto3 uses the job's IAM role
s3 = boto3.client("s3")


# ---------- TRACKER ----------
def read_tracker():
    """Return the last month extracted, e.g. '2018-11'."""
    obj = s3.get_object(Bucket=BUCKET, Key=TRACKER_KEY)
    last = obj["Body"].read().decode("utf-8").strip()
    print(f"[read_tracker] Last month extracted: {last}")
    return last


def update_tracker(month):
    s3.put_object(Bucket=BUCKET, Key=TRACKER_KEY, Body=month.encode("utf-8"))
    print(f"[update_tracker] Tracker set to {month}")


# ---------- MONTHS ----------
def next_month(month):
    """'2018-11' -> '2018-12', '2018-12' -> '2019-01'."""
    year, mon = map(int, month.split("-"))
    if mon == 12:
        return f"{year + 1}-01"
    return f"{year}-{mon + 1:02d}"


def to_source_format(month):
    """'2018-12' -> 'Dec-2018', the way issue_d is stored in MySQL."""
    return date(int(month[:4]), int(month[5:7]), 1).strftime("%b-%Y")


# ---------- EXTRACT ----------
def get_connection(args):
    """Open a MySQL connection using the job parameters."""
    return pymysql.connect(
        host=args["db_host"],
        user=args["db_user"],
        password=args["db_password"],
        database=args["db_name"],
        port=3306,
        connect_timeout=10,
    )


def read_month(conn, issue_d):
    """Return all rows for one month as a DataFrame (all text, like the source)."""
    # %s is filled in safely by pymysql, not by Python string formatting
    sql = f"SELECT * FROM {SOURCE_TABLE} WHERE issue_d = %s"
    with conn.cursor() as cur:
        cur.execute(sql, (issue_d,))
        rows = cur.fetchall()
        columns = [col[0] for col in cur.description]
    return pd.DataFrame(rows, columns=columns)


# ---------- LOAD ----------
def write_raw(df, month):
    """Upload the month as one Parquet file into the raw folder."""
    key = f"{RAW_PREFIX}/loans_{month}.parquet"

    buffer = BytesIO()
    df.to_parquet(buffer, index=False)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buffer.getvalue())

    return f"s3://{BUCKET}/{key}"


# ---------- MAIN ----------
def main():
    # Glue passes job parameters on the command line, e.g. --db_host lending-mysql...
    args = getResolvedOptions(sys.argv, ["db_host", "db_name", "db_user", "db_password"])

    last = read_tracker()
    month = next_month(last)
    issue_d = to_source_format(month)
    print(f"[main] Extracting {month} (issue_d = '{issue_d}') from {SOURCE_TABLE}")

    conn = get_connection(args)
    try:
        df = read_month(conn, issue_d)
    finally:
        conn.close()

    if df.empty:
        print(f"[main] No rows for {month} yet. Nothing written, tracker unchanged.")
        return

    path = write_raw(df, month)
    print(f"[main] Wrote {len(df):,} rows to {path}")

    update_tracker(month)  # only after the write succeeded


if __name__ == "__main__":
    main()