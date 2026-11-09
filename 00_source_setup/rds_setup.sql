-- RDS setup: copy the source table to Amazon RDS MySQL and prepare the extract test.
-- Run the SQL in MySQL Workbench on the RDS connection.
--
-- Copying the table was done from a terminal, not in SQL:
--
--   mysqldump -u root -p --single-transaction --set-gtid-purged=OFF lending_db loans > loans_dump.sql
--   mysql -h <rds-endpoint> -u admin -p lending_db < loans_dump.sql
--
-- --single-transaction : consistent copy without locking the local table
-- --set-gtid-purged=OFF: skips replication settings that RDS rejects
-- loans_dump.sql (525 MB) is not stored in this repository.
--
-- Workbench note: queries longer than 30 seconds are cut off by default.

USE lending_db;

-- 1. Check the copy matches the local table (expected 1,794,323)
SELECT COUNT(*) FROM loans;

-- 2. Hold back the last month to test "new data arriving"
CREATE TABLE loans_holdback AS
SELECT * FROM loans WHERE issue_d = 'Dec-2018';

SET SQL_SAFE_UPDATES = 0;   -- Workbench blocks a DELETE without a key otherwise
DELETE FROM loans WHERE issue_d = 'Dec-2018';

SELECT COUNT(*) FROM loans;            -- 1,754,189
SELECT COUNT(*) FROM loans_holdback;   -- 40,134

-- 3. Release the month (simulates new loans arriving in the source system)
INSERT INTO loans SELECT * FROM loans_holdback;
SELECT COUNT(*) FROM loans WHERE issue_d = 'Dec-2018';   -- 40,134