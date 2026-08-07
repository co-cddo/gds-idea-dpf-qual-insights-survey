import csv
import datetime
import email
import json
import logging
from io import StringIO
import os
import re
from typing import Any, Dict, Optional

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def extract_email_data(s3_bucket: str, s3_key: str, email_content_type: str) -> Optional[Dict[str, Any]]:
    """
    Extract data from an email stored in S3.
    Checks for 'EXAMPLE TEST EZCOMMS EMAIL' in the subject line.
    Returns a dictionary with the timestamp, sender email, and email content.
    """
    try:
        # Add timestamp in Athena-compatible format (to seconds precision)
        current_timestamp = datetime.datetime.now(datetime.timezone.utc)

        # Get the email from S3
        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        email_content = response["Body"].read().decode("utf-8", errors="replace")

        # Parse the email
        msg = email.message_from_string(email_content)

        # Check if this is an example test email by looking at the subject
        subject = msg.get("Subject", "")
        if "EXAMPLE TEST EZCOMMS EMAIL" not in subject.upper():
            logger.info(
                "Email does not contain 'EXAMPLE TEST EMAIL' in subject - skipping processing"
            )
            return None

        logger.info(
            "Found 'EXAMPLE TEST EMAIL' in subject - proceeding with processing"
        )

        def content_to_extract(msg, email_content_type):
            for part in msg.walk():
                if part.get_content_type() == email_content_type:
                    data=part.get_payload(decode=True).decode('utf-8')

            return data

        def process_text_email(msg):
                    # Extract the sender's email
                from_email = msg.get("From", "")
                # Clean up the email address - extract just the address part
                if "<" in from_email and ">" in from_email:
                    from_email = re.search(r"<([^>]+)>", from_email).group(1)

                logger.info(f"Extracted sender email: {from_email}")

                # Extract the received headers to capture routing information
                received_headers = []
                for header in msg.get_all("Received", []):
                    received_headers.append(header)

                # Extract the email content
                email_body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            email_body = part.get_payload(decode=True).decode("utf-8")
                            break
                else:
                    email_body = msg.get_payload(decode=True).decode("utf-8")

                logger.info(f"Excerpt email body (first 200 chars): {email_body[:200]}")

                # Generate a unique ID using timestamp and email
                timestamp_str = current_timestamp.strftime("%Y%m%d%H%M%S")
                email_part = from_email.replace("@", "_at_").replace(".", "_")
                unique_id = f"{timestamp_str}_{email_part}"

                # Prepare the result with all required fields for the Athena table
                result = {
                    "timestamp": current_timestamp,
                    "unique_id": unique_id,
                    "user_email": from_email,
                    "email_content": email_body,
                }

                return result

        def process_csv_email(csv_content):
        # Parse the CSV data into a dictionary
            csv_reader = csv.DictReader(StringIO(csv_content))
            rows = list(csv_reader)

            if not rows:
                logger.warning("CSV attachment was empty or invalid")
                return None
                
            # Expect one row of data
            form_data = rows[0]
            logger.info(f"Successfully extracted {len(form_data)} fields from CSV")

            email_content = ", ".join(f"{k}: {v}" for k, v in form_data.items())
            # Construct the structured response
            result = {
                "timestamp": current_timestamp,
                "unique_id": form_data.get("Reference"),
                "user_email": form_data.get("What's your email address?"),
                "email_content": email_content
                }
            
            return result

        def process_email(msg, email_content_type):
            email_content = content_to_extract(msg, email_content_type)
            if email_content_type == "text/plain":
                return process_text_email(msg)
            elif email_content_type == "text/csv":
                return process_csv_email(email_content)
            else:
                raise ValueError(f"Unsupported content type: {email_content_type}")
            
        return process_email(msg, email_content_type)

    except Exception as e:
        logger.error(f"Error extracting email data: {str(e)}")
        logger.error(f"Full error: {str(e)}", exc_info=True)
        raise


def write_to_parquet(data: Dict[str, Any], bucket: str, table_name: str) -> str:
    """
    Write extracted email data to a Parquet file in S3.
    The file location is based on the Athena table structure.
    """
    try:
        # Convert datetime directly to PyArrow timestamp
        timestamp_val = pa.scalar(data["timestamp"], type=pa.timestamp("s"))

        # Create PyArrow table with the correct schema matching the Athena table
        table = pa.Table.from_pydict(
            {
                "timestamp": [timestamp_val.as_py()],
                "unique_id": [data["unique_id"]],
                "user_email": [data["user_email"]],
                "email_content": [data["email_content"]],
            },
            schema=pa.schema(
                [
                    ("timestamp", pa.timestamp("s")),
                    ("unique_id", pa.string()),
                    ("user_email", pa.string()),
                    ("email_content", pa.string()),
                ]
            ),
        )

        # Write to buffer
        buffer = pa.BufferOutputStream()
        pq.write_table(table, buffer, compression="snappy", version="2.6")

        file_name = f"{table_name}/{data['unique_id']}.parquet"

        logger.info(f"Writing parquet file to {bucket}/{file_name}")
        s3 = boto3.client("s3")
        s3.put_object(Bucket=bucket, Key=file_name, Body=buffer.getvalue().to_pybytes())
        return file_name

    except Exception as e:
        logger.error(f"Error writing parquet file: {str(e)}")
        raise


def handler(event, context):
    """
    Main Lambda handler function.
    Processes S3 event notifications for new emails, extracts data from emails
    with 'EXAMPLE TEST EZCOMMS EMAIL' in the subject, and writes the data to Athena.
    """
    try:
        # Get environment variables ready for upload later
        email_content_type = os.environ["EMAIL_CONTENT_TYPE"]
        athena_bucket = os.environ["ATHENA_OUTPUT_BUCKET"]
        emails_table_name = os.environ["ATHENA_TABLE"]
        project = os.environ["PROJECT"]

        logger.info(
            f"Starting email processing for project {project} with "
            f"S3 destination: {athena_bucket}/{emails_table_name}"
        )

        processed_count = 0
        skipped_count = 0

        # Process each record from the S3 event from EventBridge
        if (
            "detail" in event
            and "bucket" in event["detail"]
            and "object" in event["detail"]
        ):
            # Extract bucket and key from EventBridge event
            bucket_name = event["detail"]["bucket"]["name"]
            object_key = event["detail"]["object"]["key"]

            logger.info(
                f"Processing EventBridge event for S3 object: {bucket_name}/{object_key}"
            )

            # Only process files in the incoming/ prefix
            if object_key.startswith("incoming/"):
                # Extract data from the email
                result = extract_email_data(bucket_name, object_key, email_content_type)

                if result is None:
                    skipped_count += 1
                    logger.info(f"Skipped non-example test email: {object_key}")
                else:
                    file_name = write_to_parquet(
                        result, athena_bucket, emails_table_name
                    )
                    processed_count += 1
                    logger.info(
                        f"Successfully processed example test email to {file_name}"
                    )
            else:
                logger.info(f"Skipping file {object_key} - not in incoming/ prefix")
        else:
            logger.warning("Received event is not a recognized EventBridge event")
            logger.info(f"Event structure: {json.dumps(event)}")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Example email processing complete",
                    "processed_count": processed_count,
                    "skipped_count": skipped_count,
                    "project": project,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error in handler: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
