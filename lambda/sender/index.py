import json
import logging
import os

import awswrangler as wr
import boto3
from email_template import generate_email_template
from notifications_python_client.notifications import NotificationsAPIClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# def read_parquet_from_s3(bucket, key):
#     """Helper function to read both the query table and response table"""
#     s3_client = boto3.client('s3')
#     logger.info(f"Reading parquet file from s3://{bucket}/{key}")
#     obj = s3_client.get_object(Bucket=bucket, Key=key)
#     parquet_buffer = BytesIO(obj['Body'].read())
#     table = pq.read_table(parquet_buffer)
#     return table


def get_secret(secret_name: str, region: str) -> str:
    """Retrieve secret from AWS Secrets Manager

    Args:
        secret_name: Name of the secret in Secrets Manager
        region: AWS region where the secret is stored

    Returns:
        Secret value as a string
    """
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return response["SecretString"]


def send_email_ses(
    recipient_email: str,
    email_subject: str,
    email_content: dict,
    sender_email_address: str,
):
    """Send email using Amazon SES

    Args:
        recipient_email: Email address of the recipient
        email_subject: Subject line for the email
        email_content: Dictionary with 'text' and 'html' keys containing email body
        sender_email_address: Email address of the sender

    Returns:
        True if successful, False otherwise
    """
    try:
        ses_client = boto3.client("ses")

        logger.info(f"Sending email via SES to {recipient_email}...")
        email_response = ses_client.send_email(
            Source=sender_email_address,
            Destination={
                "ToAddresses": [recipient_email],
            },
            Message={
                "Subject": {"Data": email_subject},
                "Body": {
                    "Text": {"Data": email_content["text"]},
                    "Html": {"Data": email_content["html"]},
                },
            },
        )

        logger.info(
            f"Email sent successfully via SES! Message ID: {email_response['MessageId']}"
        )
        return True
    except Exception as e:
        logger.error(f"Error sending email via SES: {str(e)}")
        return False


def send_email_notify(
    recipient_email: str,
    query: str,
    response_text: str,
    api_key_name: str,
    template_id: str,
    secret_region: str,
):
    """Send email using GOV.UK Notify

    Args:
        recipient_email: Email address of the recipient
        query: User's original query
        response_text: LLM response to the query
        api_key_name: Name of the Notify API key in Secrets Manager
        template_id: GOV.UK Notify template ID to use
        secret_region: AWS region where the secret is stored

    Returns:
        True if successful, False otherwise
    """
    try:
        # Retrieve the Notify API key value
        api_key = get_secret(secret_name=api_key_name, region=secret_region)

        # Initialise Notify client
        notifications_client = NotificationsAPIClient(api_key)

        # Prepare personalisation data for the template
        personalisation = {
            "question": query,
            "response": response_text,
        }

        logger.info(f"Sending email via GOV.UK Notify to {recipient_email}...")
        email_content = notifications_client.send_email_notification(
            email_address=recipient_email,
            template_id=template_id,
            personalisation=personalisation,
        )

        logger.info(
            f"Email sent successfully via Notify! Message ID: {email_content['id']}"
        )
        return True
    except Exception as e:
        logger.error(f"Error sending email via Notify: {str(e)}")
        return False


def process_parquet_and_send_email(bucket_name, parquet_key_llm_response):
    """Read a parquet file and send a single email with its contents

    Supports two sending modes:
    - 'ses': Uses Amazon SES to send emails
    - 'notify': Uses GOV.UK Notify to send emails

    Args:
        bucket_name: S3 bucket containing the parquet file
        parquet_key_llm_response: S3 key for the parquet file

    Returns:
        True if successful, False otherwise
    """
    # Get environment variables
    sender_mode = os.environ.get("SENDER_MODE", "ses").lower()
    followup_email_address = os.environ["FOLLOWUP_EMAIL_ADDRESS"]
    bucket_name = os.environ["ATHENA_OUTPUT_BUCKET"]

    # SES-specific variables
    sender_email_address = os.environ.get("SENDER_EMAIL_ADDRESS", "")
    email_subject = os.environ.get("EMAIL_SUBJECT", "")

    # Notify-specific variables
    api_key_name = os.environ.get("API_KEY_NAME", "")
    secret_region = os.environ.get("SECRET_REGION", "")
    notify_template_id = os.environ.get("NOTIFY_TEMPLATE_ID", "")

    try:
        # Fetch parquet file from S3
        table_llm_responses = wr.s3.read_parquet(
            f"s3://{bucket_name}/{parquet_key_llm_response}"
        )
        logger.info(
            f"Fetching parquet file from s3://{bucket_name}/{parquet_key_llm_response}"
        )

        # Check for required columns
        required_columns = ["user_email", "email_content", "llm_response"]
        missing_columns = [
            col for col in required_columns if col not in table_llm_responses.columns
        ]
        if missing_columns:
            logger.error(
                f"Missing required columns: {missing_columns}. Available columns: {table_llm_responses.columns.tolist()}"
            )

        # Extract data from the parquet file
        recipient_email = table_llm_responses["user_email"].iloc[0]
        query = table_llm_responses["email_content"].iloc[0]
        response_text = table_llm_responses["llm_response"].iloc[0]

        logger.info("\nData from Parquet:")
        logger.info(f"  Recipient: {recipient_email}")
        logger.info(f"  Query: {query[:100]}")
        logger.info(f"  Response: {response_text[:100]}")

        # Send email based on configured mode
        # Send email based on configured mode
        if sender_mode == "notify":
            if not all([api_key_name, secret_region, notify_template_id]):
                logger.error(
                    "Notify mode requires API_KEY_NAME, SECRET_REGION, and NOTIFY_TEMPLATE_ID environment variables"
                )
                return False

            return send_email_notify(
                recipient_email=recipient_email,
                query=query,
                response_text=response_text,
                api_key_name=api_key_name,
                template_id=notify_template_id,
                secret_region=secret_region,
            )
        else:  # Default to SES
            if not all([sender_email_address, email_subject]):
                logger.error(
                    "SES mode requires SENDER_EMAIL_ADDRESS and EMAIL_SUBJECT environment variables"
                )
                return False

            # Generate email content
            email_content = generate_email_template(
                query, response_text, email_support=followup_email_address
            )

            return send_email_ses(
                recipient_email=recipient_email,
                email_subject=email_subject,
                email_content=email_content,
                sender_email_address=sender_email_address,
            )

    except Exception as e:
        logger.error(f"Error processing parquet or sending email: {str(e)}")
        return False


def handler(event, context):
    try:
        bucket_name = event["detail"]["bucket"]["name"]
        parquet_key_llm_response = event["detail"]["object"]["key"]

        logger.info(f"LLM response file: {parquet_key_llm_response}")

        # Process and send email
        result = process_parquet_and_send_email(bucket_name, parquet_key_llm_response)

        return {
            "statusCode": 200 if result else 500,
            "body": json.dumps("Success" if result else "Failure"),
        }

    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps(f"Error: {str(e)}")}
