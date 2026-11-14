# 00 Source setup: the loan data in MySQL

This stage prepares the source system for the pipeline. The Kaggle Lending Club file is
explored, loaded into MySQL month by month, and then moved to Amazon RDS MySQL. The
pipeline reads its data from RDS, the way a real pipeline reads from a company's
live database.

**Dataset:** [Lending Club Loan Data (CSV) on Kaggle](https://www.kaggle.com/datasets/adarshsng/lending-club-loan-data-csv)

## Flow

```mermaid
flowchart TD
    A["loan.csv<br/>Kaggle Lending Club file<br/>2.26M loans, 145 columns"] --> B["Explore the data<br/>keep 33 columns<br/>keep loans issued from 2015<br/>1.79M loans"]
    B --> C["Load into MySQL<br/>one month at a time"]
    C --> D[("Local MySQL<br/>lending_db.loans")]
    D --> E["Copy to AWS<br/>mysqldump export and import"]
    E --> F[("Amazon RDS MySQL<br/>lending_db.loans<br/>1,794,323 loans")]
```

## Steps

1. **Explore the data**
   Kept the 33 columns needed for the analysis and only loans issued from January 2015
   onwards. Issue dates are stored per month (for example `Jan-2015`), so the data is
   handled one month at a time.

2. **Load into MySQL**
   Loaded the loans into MySQL one month at a time, oldest month first, so the database
   fills up the way data would arrive over time. The load remembers the last month loaded,
   so it can continue from where it stopped and never loads a month twice.

3. **Move to Amazon RDS**
   Copied the table to RDS MySQL with `mysqldump`. RDS is reachable only from my laptop
   and from Glue (security group rules).

4. **Prepare a test month**
   Held back December 2018 in a side table, so the extract job could be tested with
   "no new data" first and then "new data arriving" (`rds_setup.sql`).

## Result

| Check | Value |
|---|---|
| Loans in `loan.csv` (all years) | 2,260,668 |
| Loans from 2015 onwards | 1,794,323 |
| Months | 48 (2015-01 to 2018-12) |
| Rows in RDS `lending_db.loans` | 1,794,323 (matches the file) |

## Files

| File | Purpose |
|---|---|
| `load_monthly_to_mysql.py` | Loads the loans into MySQL one month at a time |
| `rds_setup.sql` | Copy check, hold back and release December 2018 |

`loan.csv` (about 1.2 GB) is not stored in this repository. Download it from
[Kaggle](https://www.kaggle.com/datasets/adarshsng/lending-club-loan-data-csv).
The `.env` file with passwords is not stored here either.