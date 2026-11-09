   """
   Lambda: trigger_loans_silver (Python 3.12)  [RETIRED]

   Version 1 of the Silver trigger. An S3 upload event on raw/*.csv started the
   loans_silver_job Glue job with the new file's path as --input_file_path.

   Retired because raw is now Parquet written by the Glue extract job, and the
   jobs will be chained by a Glue Workflow instead of an S3 event.
   Kept as a record of how the first version worked.
   """

import boto3
from urllib.parse import unquote_plus

glue = boto3.client("glue")

GLUE_JOB_NAME = "loans_silver_job"      # must match your Glue job's exact name


def lambda_handler(event, context):
    """Start the Glue job for each new raw file that S3 tells us about."""
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        input_path = f"s3://{bucket}/{key}"

        response = glue.start_job_run(
            JobName=GLUE_JOB_NAME,
            Arguments={"--input_file_path": input_path},
        )
        print(f"Started {GLUE_JOB_NAME} run {response['JobRunId']} for {input_path}")

    return {"status": "ok"}