import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict

import awswrangler as wr
import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from src.llm_20250509 import LLMAgent

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def write_response_to_parquet(
    data: Dict[str, Any], bucket: str, responses_table_name: str
) -> str:
    try:
        # Convert datetime to PyArrow timestamp
        timestamp_val = pa.scalar(data["timestamp"], type=pa.timestamp("s"))

        # Create PyArrow table with the correct schema
        table = pa.Table.from_pydict(
            {
                "timestamp": [timestamp_val.as_py()],
                "unique_id": [data["unique_id"]],
                "user_email": [data["user_email"]],
                "email_content": [data["email_content"]],
                "llm_context": [data["llm_context"]],
                "llm_response": [data["llm_response"]],
            },
            schema=pa.schema(
                [
                    ("timestamp", pa.timestamp("s")),
                    ("unique_id", pa.string()),
                    ("user_email", pa.string()),
                    ("email_content", pa.string()),
                    ("llm_context", pa.string()),
                    ("llm_response", pa.string()),
                ]
            ),
        )

        # Write to buffer
        buffer = pa.BufferOutputStream()
        pq.write_table(table, buffer, compression="snappy", version="2.6")

        # Upload to S3
        s3 = boto3.client("s3")
        file_name = f"{responses_table_name}/{data['unique_id']}.parquet"

        logger.info(f"Writing response to {bucket}/{file_name}")
        s3.put_object(Bucket=bucket, Key=file_name, Body=buffer.getvalue().to_pybytes())
        return file_name
    except Exception as e:
        logger.error(f"Error writing response parquet file: {str(e)}")
        raise


def handler(event, context):
    """
    Lambda function to respond to queries with an LLM. Triggered by an uploaded query file,
    extracts username, unique_id, and query to respond back, pushes back into an athena table
    ready for it to be sent on via SES response.
    """
    logger.info(f"Event received: {json.dumps(event)}")

    # Retrieve environment variables
    llm_region = os.environ["LLM_REGION"]
    kb_region = os.environ["KB_REGION"]
    kb_id = os.environ["KB_ID"]
    data_region = os.environ["DATA_REGION"]
    athena_output_bucket = os.environ.get(
        "ATHENA_OUTPUT_BUCKET"
    )  # Where to store the output llm response data
    athena_database = os.environ.get("ATHENA_DATABASE")
    athena_queries_table = os.environ.get("ATHENA_QUERIES_TABLE")
    athena_responses_table = os.environ.get("ATHENA_RESPONSES_TABLE")
    athena_queries_bucket = os.environ.get(
        "ATHENA_QUERIES_BUCKET"
    )  # This is where awswrangler stores its results
    project = os.environ.get("PROJECT")

    logger.info("🔹 Environment Variables:")
    logger.info(f"PROJECT: {project}")
    logger.info(f"LLM_REGION: {llm_region}")
    logger.info(f"KB_REGION: {kb_region}")
    logger.info(f"DATA_REGION: {data_region}")
    logger.info(f"KB_ID: {kb_id}")
    logger.info(f"ATHENA_DATABASE: {athena_database}")
    logger.info(f"ATHENA_QUERIES_TABLE: {athena_queries_table}")
    logger.info(f"ATHENA_RESPONSES_TABLE: {athena_responses_table}")
    logger.info(f"ATHENA_QUERIES_BUCKET: {athena_queries_bucket}")
    logger.info(f"ATHENA_OUTPUT_BUCKET: {athena_output_bucket}")

    logger.info("Starting response generation for EZComms")
    snapshot_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    logger.info("Sleeping for 15 seconds to ensure Athena is updated with new query...")
    time.sleep(15)
    logger.info("Sleep complete, continuing with processing...")

    logger.info(f"📅 Timestamp: {snapshot_timestamp}")

    # Setup llm call
    try:
        unique_id = None
        session_data = boto3.Session(region_name=data_region)

        if "detail" in event and "object" in event["detail"]:
            file_key = event["detail"]["object"]["key"]
            unique_id = file_key.split("/")[-1].split(".")[
                0
            ]  # We just want the filename which is also the unique id from the email
            logger.info(f"Extracted unique_id from EventBridge S3 event: {unique_id}")

        athena_query = f"""
        SELECT user_email, email_content
        FROM "{athena_database}"."{athena_queries_table}"
        WHERE unique_id = '{unique_id}'
        """
        logger.info(f"Executing Athena query: {athena_query}")

        df = wr.athena.read_sql_query(
            sql=athena_query,
            database=athena_database,
            ctas_approach=False,
            workgroup="primary",
            s3_output=f"s3://{athena_queries_bucket}/{project}_processing/",
            boto3_session=session_data,
        )

        if df.empty:
            error_msg = f"No data found for unique_id: {unique_id}"
            logger.error(error_msg)
            return {"statusCode": 404, "body": json.dumps({"error": error_msg})}

        row = df.iloc[0]
        user_email = row.get("user_email", "")
        query = row.get("email_content", "")
        logger.info(f"User email: {user_email}")
        logger.info(f"User query: {query}")

        logger.info("Initializing Agent...")
        agent = LLMAgent(llm_region=llm_region, kb_region=kb_region, kb_id=kb_id)

        logger.info(f"Generating RAG response with knowledge base ID: {kb_id}")
        response = agent.answer_with_rag(username=user_email, query=query, kb_id=kb_id)

        logger.info(f"Response generated. Source count: {len(response.sources)}")
        logger.info(f"Response length: {len(response.answer)} characters")
        logger.info(f"Response answer: {response.answer}")

        response_data = {
            "timestamp": datetime.now(),
            "unique_id": unique_id,
            "user_email": user_email,
            "email_content": query,
            "llm_context": ", ".join(response.sources),
            "llm_response": response.answer,
        }

        file_name = write_response_to_parquet(
            response_data, athena_output_bucket, athena_responses_table
        )
        logger.info(f"Successfully wrote response to {file_name}")

        logger.info(
            f"✅ Successfully processed query and generated response for {unique_id}"
        )
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "LLM response generated successfully",
                    "unique_id": unique_id,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error generating LLM response: {str(e)}", exc_info=True)
        raise e
