"""
Glue Python shell job: data lake check with Athena, between Silver and Gold.

Runs one Athena query that compares, for every month, the number of loans in
raw (Bronze) with the number in processed (Silver). If any month is missing on
one side, or the counts differ, the job fails, so the Gold job does not run.

How it works:
1. Start the reconciliation query in Athena (database lending_lake).
2. Wait until Athena has finished.
3. Read the result: the query only returns months that do NOT match.
   No rows means every month matches.
4. Fail with the list of problem months, or finish with "all months match".

The crawler must run before this job, so the newest processed month is
registered as a partition. Otherwise that month shows up as a mismatch.

Job details in Glue:
- Type: Python shell, Python 3.9, 'Load common analytics libraries' ticked, 1/16 DPU
- IAM role: the Glue job role, with Athena permissions, Glue Data Catalog read
  and S3 access (read the lake, write query results)
- Timeout: 10 minutes
- No connection, no job parameters
"""

# ---------- IMPORTS ----------
import time

import boto3


# ---------- SETTINGS ----------
DATABASE = "lending_lake"
WORKGROUP = "primary"
RESULTS_LOCATION = "s3://lending-data-de-project/athena-results/"

POLL_SECONDS = 3   # wait between "is the query finished yet?" checks

# Months where raw and processed do not match. No rows means everything matches.
MISMATCH_SQL = """
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
       p.processed_rows
FROM raw_counts r
FULL OUTER JOIN processed_counts p ON r.month = p.month
WHERE r.raw_rows IS NULL
   OR p.processed_rows IS NULL
   OR r.raw_rows <> p.processed_rows
ORDER BY 1
"""

# No keys: in Glue, boto3 uses the job's IAM role
athena = boto3.client("athena")


# ---------- ATHENA ----------
def run_query(sql):
    """Start a query, wait for it, and return its result rows (without the header row)."""
    start = time.time()
    resp = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        WorkGroup=WORKGROUP,
        ResultConfiguration={"OutputLocation": RESULTS_LOCATION},
    )
    query_id = resp["QueryExecutionId"]

    # Athena runs the query in the background, so keep asking until it has finished
    while True:
        status = athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Athena query {state}: {status.get('StateChangeReason')}")
        time.sleep(POLL_SECONDS)

    result = athena.get_query_results(QueryExecutionId=query_id)
    rows = result["ResultSet"]["Rows"]
    print(f"[run_query] Athena query {query_id} finished in {time.time() - start:.0f}s")

    # The first row is the column names. Each cell is {"VarCharValue": "..."}, or {} when null
    data_rows = rows[1:]
    return [[cell.get("VarCharValue", "missing") for cell in row["Data"]] for row in data_rows]


# ---------- MAIN ----------
def main():
    mismatches = run_query(MISMATCH_SQL)

    if mismatches:
        for month, raw_rows, processed_rows in mismatches:
            print(f"[main] MISMATCH {month}: raw {raw_rows} | processed {processed_rows}")
        raise RuntimeError(f"{len(mismatches)} month(s) do not match between raw and processed")

    print("[main] All months match between raw and processed")


if __name__ == "__main__":
    main()